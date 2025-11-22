"""
Simple CLI runner for the Data Recoverer.

Allows one-off executions via `python -m data_recoverer.runner`.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

from zoneinfo import ZoneInfo

from data_recoverer.DR_recovery import DataRecoverer

MADRID_TZ = ZoneInfo("Europe/Madrid")
LOGGER = logging.getLogger("data_recoverer.runner")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Data Recoverer once.")
    default_cfg = Path("data_recoverer/config.yaml")
    parser.add_argument(
        "--config",
        type=Path,
        default=default_cfg,
        help="Path to data_recoverer config file (default: %(default)s).",
    )
    parser.add_argument(
        "--since-hours",
        type=float,
        default=None,
        help="Optional look-back window (in hours) to limit inactivity intervals.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of intervals to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and log batches without writing to MongoDB.",
    )
    return parser.parse_args()


def _resolve_since(hours: float | None) -> datetime | None:
    if hours is None:
        return None
    now = datetime.now(MADRID_TZ)
    return now - timedelta(hours=hours)


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    LOGGER.info(
        "Starting data recoverer (config=%s, since_hours=%s, limit=%s, dry_run=%s)",
        args.config,
        args.since_hours,
        args.limit,
        args.dry_run,
    )
    recoverer = DataRecoverer.from_file(args.config)
    since = _resolve_since(args.since_hours)
    summary = recoverer.run_once(since=since, limit=args.limit, dry_run=args.dry_run)
    LOGGER.info("Data recovery run finished: %s", summary)
    print(summary)


if __name__ == "__main__":
    main()
