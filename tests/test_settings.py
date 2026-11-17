"""Tests for config/settings.py"""

import os
import importlib
import pytest
from pathlib import Path
from unittest.mock import patch

import config.settings as settings_mod

REQUIRED_ENV = {
    "GITHUB_SIGNATURE_KEY": "gs",
    "TAIGA_SIGNATURE_KEY": "ts",
}
REMOVED_SETTINGS = (
    "GITHUB_TOKEN",
    "TAIGA_API_URL",
    "TAIGA_AUTH_URL",
    "TAIGA_TOKEN",
    "TAIGA_USERNAME",
    "TAIGA_PASSWORD",
)


def _reload(env: dict):
    """Reload the settings module with exactly <env> as environment (no .env file)."""
    env = {"HOME": os.environ.get("HOME") or str(Path.home()), **env}
    with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
        importlib.reload(settings_mod)
    return settings_mod


@pytest.fixture(autouse=True)
def restore_settings():
    """Leave the settings module as the rest of the test suite expects it."""
    yield
    with patch("dotenv.load_dotenv"):
        importlib.reload(settings_mod)


class TestSettings:
    @pytest.mark.parametrize("missing", sorted(REQUIRED_ENV))
    def test_require_env_missing_raises(self, missing):
        """_require_env should raise RuntimeError when variable is missing."""
        env = {k: v for k, v in REQUIRED_ENV.items() if k != missing}
        with pytest.raises(RuntimeError, match=missing):
            _reload(env)

    def test_mongo_uri_without_credentials(self):
        settings = _reload(
            {
                **REQUIRED_ENV,
                "MONGO_HOST": "myhost",
                "MONGO_PORT": "27017",
                "MONGO_DB": "mydb",
                "MONGO_USER": "",
                "MONGO_PASS": "",
            }
        )
        assert settings.MONGO_URI == "mongodb://myhost:27017/mydb"

    def test_mongo_uri_with_credentials(self):
        settings = _reload(
            {
                **REQUIRED_ENV,
                "MONGO_HOST": "myhost",
                "MONGO_PORT": "27017",
                "MONGO_DB": "mydb",
                "MONGO_USER": "admin",
                "MONGO_PASS": "secret",
                "MONGO_AUTHSRC": "authdb",
            }
        )
        assert "admin:secret" in settings.MONGO_URI
        assert "authSource=authdb" in settings.MONGO_URI

    def test_default_values(self):
        settings = _reload(REQUIRED_ENV)
        assert settings.MONGO_HOST == "mongodb"
        assert settings.MONGO_PORT == "27017"
        assert settings.GITHUB_API_URL == "https://api.github.com"

    def test_taiga_fallback_is_optional(self):
        settings = _reload(REQUIRED_ENV)
        assert settings.TAIGA_FALLBACK_API_URL == ""
        assert settings.TAIGA_FALLBACK_AUTH_URL == ""
        assert settings.TAIGA_FALLBACK_USERNAME == ""
        assert settings.TAIGA_FALLBACK_PASSWORD == ""

    def test_taiga_fallback_read_from_environment(self):
        settings = _reload(
            {
                **REQUIRED_ENV,
                "TAIGA_FALLBACK_API_URL": "https://api.taiga.io/api/v1",
                "TAIGA_FALLBACK_AUTH_URL": "https://api.taiga.io/api/v1/auth",
                "TAIGA_FALLBACK_USERNAME": "user",
                "TAIGA_FALLBACK_PASSWORD": "pass",
            }
        )
        assert settings.TAIGA_FALLBACK_API_URL == "https://api.taiga.io/api/v1"
        assert settings.TAIGA_FALLBACK_AUTH_URL == "https://api.taiga.io/api/v1/auth"
        assert settings.TAIGA_FALLBACK_USERNAME == "user"
        assert settings.TAIGA_FALLBACK_PASSWORD == "pass"

    @pytest.mark.parametrize("name", REMOVED_SETTINGS)
    def test_global_taiga_and_github_credentials_are_gone(self, name):
        """Credentials are per subject (credentials config); the global ones are ignored."""
        settings = _reload({**REQUIRED_ENV, name: "ignored"})
        assert not hasattr(settings, name)
