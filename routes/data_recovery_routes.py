import logging
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request

from config.logger_config import setup_logging
from data_recoverer import DataRecoverer
from data_recoverer.DR_recovery import MADRID_TZ

setup_logging()
logger = logging.getLogger(__name__)

data_recovery_bp = Blueprint("data_recovery_bp", __name__)

_DEFAULT_CONFIG = Path(os.getenv("DATA_RECOVERY_CONFIG", "data_recoverer/config.yaml"))
_run_lock = threading.Lock()
_run_inflight = threading.Event()


def _parse_since(payload: Dict[str, Any]) -> Optional[datetime]:
    """
    Resolve the window start. Prefer an explicit ISO timestamp; fall back to a
    hours-based look-back. Returns a tz-aware datetime in Madrid time.
    """
    if "since" in payload and payload["since"] is not None:
        try:
            cleaned = str(payload["since"]).strip().replace("Z", "+00:00")
            parsed = datetime.fromisoformat(cleaned)
        except Exception as exc:
            raise ValueError("Invalid 'since' timestamp; expected ISO-8601 string.") from exc
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=MADRID_TZ)

    if "since_hours" in payload and payload["since_hours"] is not None:
        try:
            hours = float(payload["since_hours"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid 'since_hours'; expected a number.") from exc
        return datetime.now(MADRID_TZ) - timedelta(hours=hours)

    return None


def _parse_limit(payload: Dict[str, Any]) -> Optional[int]:
    if "limit" not in payload or payload["limit"] is None:
        return None
    try:
        return int(payload["limit"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid 'limit'; expected an integer.") from exc


def _run_recovery(config_path: Path, *, since: Optional[datetime], limit: Optional[int], dry_run: bool) -> Dict[str, Any]:
    """
    Execute the recovery once while holding the global run lock to avoid
    overlapping runs.
    """
    with _run_lock:
        _run_inflight.set()
        try:
            recoverer = DataRecoverer.from_file(config_path)
            started_at = datetime.now(MADRID_TZ)
            summary = recoverer.run_once(since=since, limit=limit, dry_run=dry_run)
            finished_at = datetime.now(MADRID_TZ)
            logger.info("Data recovery run finished via API: %s", summary)
            return {
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "summary": summary,
            }
        finally:
            _run_inflight.clear()


@data_recovery_bp.route("/data-recovery/run", methods=["POST"])
def run_data_recovery():
    """
    Trigger a one-off data recovery. Accepts an optional JSON body:
    {
        "since": "<ISO timestamp>",
        "since_hours": <float>,   # used when "since" is not provided
        "limit": <int>,
        "dry_run": <bool>,
        "config_path": "<path to config>",
        "run_async": <bool>       # if true, start in background and return 202
    }
    """
    payload = request.get_json(silent=True) or {}
    dry_run = bool(payload.get("dry_run", False))
    run_async = bool(payload.get("run_async", False))

    try:
        since = _parse_since(payload)
        limit = _parse_limit(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    config_path = Path(payload.get("config_path") or _DEFAULT_CONFIG)
    if not config_path.exists():
        return jsonify({"error": f"Config file not found at {config_path}"}), 404

    if _run_inflight.is_set() or _run_lock.locked():
        return jsonify({"status": "busy", "message": "Data recovery is already running."}), 409

    params = {
        "config_path": str(config_path),
        "since": since.isoformat() if since else None,
        "limit": limit,
        "dry_run": dry_run,
    }

    if run_async:
        _run_inflight.set()
        def _background_job() -> None:
            try:
                result = _run_recovery(config_path, since=since, limit=limit, dry_run=dry_run)
                logger.info("Async data recovery completed: %s", result)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Async data recovery run failed.")

        threading.Thread(target=_background_job, name="DataRecoveryAPI", daemon=True).start()
        return (
            jsonify(
                {
                    "status": "accepted",
                    "message": "Data recovery started in background.",
                    "params": params,
                }
            ),
            202,
        )

    try:
        result = _run_recovery(config_path, since=since, limit=limit, dry_run=dry_run)
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Data recovery run failed.")
        return jsonify({"status": "error", "message": "Data recovery run failed; check logs for details."}), 500

    return jsonify({"status": "completed", "params": params, **result}), 200
