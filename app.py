import logging
import os
import threading
from pathlib import Path

from flask import Flask

from config.logger_config import setup_logging
from utils.heartbeat_emitter import HeartbeatEmitter
from routes.excel_routes import excel_bp
from routes.github_routes import github_bp
from routes.taiga_routes import taiga_bp

setup_logging()
logger = logging.getLogger(__name__)
_INACTIVITY_CONFIG = os.getenv(
    "INACTIVITY_DETECTOR_CONFIG", "inactivity_detector/config.yaml"
)
_HEARTBEAT_ENABLED = os.getenv("ENABLE_HEARTBEATS", "true").lower() not in {
    "0",
    "false",
    "no",
}
_HEARTBEAT_INTERVAL = os.getenv("HEARTBEAT_INTERVAL_SECONDS")

try:
    heartbeat_interval_override = int(_HEARTBEAT_INTERVAL) if _HEARTBEAT_INTERVAL else None
except ValueError:
    logger.warning(
        "Invalid HEARTBEAT_INTERVAL_SECONDS value '%s'; falling back to config interval.",
        _HEARTBEAT_INTERVAL,
    )
    heartbeat_interval_override = None

_heartbeat_emitter = HeartbeatEmitter(
    config_path=Path(_INACTIVITY_CONFIG), interval_override=heartbeat_interval_override
)
_background_lock = threading.Lock()
_background_started = False


def _ensure_heartbeat_emitter_running() -> None:
    if not _HEARTBEAT_ENABLED:
        logger.info("Heartbeat emitter disabled via ENABLE_HEARTBEATS.")
        return
    if not _heartbeat_emitter.is_running:
        logger.info("Starting heartbeat emitter for inactivity detector.")
        _heartbeat_emitter.start()


def _should_run_background_workers(debug_mode: bool) -> bool:
    """
    Only start background workers in the serving process. In debug mode the
    reloader spawns a parent (flag unset) and a child (flag == 'true'). We only
    start workers in the child. In production (no reloader) the flag is unset,
    so we allow startup.
    """
    flag = os.environ.get("WERKZEUG_RUN_MAIN")
    if flag == "true":
        return True
    if flag is None and not debug_mode:
        return True
    return False


def _start_background_workers() -> None:
    global _background_started
    with _background_lock:
        if _background_started:
            return
        _ensure_heartbeat_emitter_running()
        _background_started = True

def create_app():
    app = Flask(__name__)

    # Register blueprint routes
    app.register_blueprint(github_bp)
    app.register_blueprint(taiga_bp)
    app.register_blueprint(excel_bp)

    logger.info("Flask created and Blueprints registered successfully.")
    return app

if __name__ == "__main__":
    app = create_app()
    debug_mode = True
    app.debug = debug_mode
    if _should_run_background_workers(debug_mode):
        _start_background_workers()
    app.run(debug=debug_mode, host="127.0.0.1", port=5000)
