"""
Entry point for running the inactivity detector as a dedicated worker
process. Keeps heartbeats/logs monitored even if the Flask app is down.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
from pathlib import Path
from typing import Optional

from config.logger_config import setup_logging
from inactivity_detector.runner import InactivityDetectorRunner

LOGGER = logging.getLogger("inactivity_detector.runner.main")


def _parse_interval(env_value: Optional[str], cli_value: Optional[int]) -> Optional[int]:
    if cli_value is not None:
        return max(1, cli_value)
    if not env_value:
        return None
    try:
        return max(1, int(env_value))
    except ValueError:
        LOGGER.warning(
            "Invalid INACTIVITY_DETECTOR_INTERVAL_SECONDS value '%s'; falling back to config interval.",
            env_value,
        )
        return None


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the inactivity detector continuously as a foreground worker."
    )
    default_config = os.getenv("INACTIVITY_DETECTOR_CONFIG", "inactivity_detector/config.yaml")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(default_config),
        help="Path to the detector configuration file (default: %(default)s).",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=None,
        help="Override run cadence in seconds (default: heartbeat interval from config).",
    )
    return parser


def main() -> None:
    setup_logging()
    args = _build_arg_parser().parse_args()
    interval_override = _parse_interval(
        os.getenv("INACTIVITY_DETECTOR_INTERVAL_SECONDS"), args.interval_seconds
    )
    runner = InactivityDetectorRunner(
        config_path=args.config,
        interval_seconds=interval_override,
    )

    def _handle_signal(signum, _frame) -> None:
        LOGGER.info("Received signal %s; requesting detector shutdown.", signum)
        runner.request_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)

    LOGGER.info(
        "Starting inactivity detector worker (config=%s, interval_override=%s).",
        args.config,
        interval_override,
    )
    runner.serve_forever()


if __name__ == "__main__":
    main()
