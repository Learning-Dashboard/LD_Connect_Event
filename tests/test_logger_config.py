"""Tests for config/logger_config.py"""

import logging, os, pytest
from unittest.mock import patch


class TestSetupLogging:
    def test_setup_logging_default_level(self):
        # Clear handlers to allow re-configuration
        root = logging.getLogger()
        root.handlers.clear()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOG_LEVEL", None)
            from config.logger_config import setup_logging

            setup_logging()
            assert root.level == logging.INFO

    def test_setup_logging_custom_level(self):
        root = logging.getLogger()
        root.handlers.clear()
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            from config.logger_config import setup_logging

            setup_logging()
            assert root.level == logging.DEBUG

    def test_setup_logging_idempotent(self):
        """If handlers already exist, setup_logging should not add more."""
        root = logging.getLogger()
        root.handlers.clear()
        from config.logger_config import setup_logging

        setup_logging()
        count_after_first = len(root.handlers)
        setup_logging()
        assert len(root.handlers) == count_after_first

    def test_setup_logging_invalid_level_falls_back(self):
        root = logging.getLogger()
        root.handlers.clear()
        with patch.dict(os.environ, {"LOG_LEVEL": "INVALID_LEVEL"}):
            from config.logger_config import setup_logging

            setup_logging()
            # Should fall back to INFO
            assert root.level == logging.INFO
