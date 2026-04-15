import logging
import os
import sys

_DEFAULT_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

def setup_logging() -> None:
    """
    Configure the logger.
    (DEBUG, INFO, WARNING, ERROR, CRITICAL).  Default = INFO.
    """
    # Read the log level from the environment variable LOG_LEVEL, default to INFO
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # If the logger is already configured, do not reconfigure it
    if logging.getLogger().handlers:
        return

    logging.basicConfig(
        level=level,
        format=_DEFAULT_FMT,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    logging.getLogger(__name__).info("Logging Initialized → level=%s", level_name)
