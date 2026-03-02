"""Tests for config/settings.py"""

import os, importlib, pytest
from unittest.mock import patch

import config.settings as settings_mod


class TestSettings:
    def test_require_env_missing_raises(self):
        """_require_env should raise RuntimeError when variable is missing."""
        env = {
            "GITHUB_SIGNATURE_KEY": "x",
            "TAIGA_SIGNATURE_KEY": "x",
            "TAIGA_USERNAME": "x",
            "TAIGA_PASSWORD": "x",
            "HOME": os.environ.get("HOME", "/tmp"),
        }
        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
            with pytest.raises(RuntimeError, match="TAIGA_API_URL"):
                importlib.reload(settings_mod)
        # Restore module to working state
        importlib.reload(settings_mod)

    def test_mongo_uri_without_credentials(self):
        env = {
            "MONGO_HOST": "myhost",
            "MONGO_PORT": "27017",
            "MONGO_DB": "mydb",
            "MONGO_USER": "",
            "MONGO_PASS": "",
            "GITHUB_SIGNATURE_KEY": "gs",
            "TAIGA_API_URL": "https://t.io",
            "TAIGA_SIGNATURE_KEY": "ts",
            "TAIGA_USERNAME": "u",
            "TAIGA_PASSWORD": "p",
        }
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config.settings as settings_mod

            importlib.reload(settings_mod)
            assert settings_mod.MONGO_URI == "mongodb://myhost:27017/mydb"

    def test_mongo_uri_with_credentials(self):
        env = {
            "MONGO_HOST": "myhost",
            "MONGO_PORT": "27017",
            "MONGO_DB": "mydb",
            "MONGO_USER": "admin",
            "MONGO_PASS": "secret",
            "MONGO_AUTHSRC": "authdb",
            "GITHUB_SIGNATURE_KEY": "gs",
            "TAIGA_API_URL": "https://t.io",
            "TAIGA_SIGNATURE_KEY": "ts",
            "TAIGA_USERNAME": "u",
            "TAIGA_PASSWORD": "p",
        }
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config.settings as settings_mod

            importlib.reload(settings_mod)
            assert "admin:secret" in settings_mod.MONGO_URI
            assert "authSource=authdb" in settings_mod.MONGO_URI

    def test_default_values(self):
        env = {
            "GITHUB_SIGNATURE_KEY": "gs",
            "TAIGA_API_URL": "https://t.io",
            "TAIGA_SIGNATURE_KEY": "ts",
            "TAIGA_USERNAME": "u",
            "TAIGA_PASSWORD": "p",
        }
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config.settings as settings_mod

            importlib.reload(settings_mod)
            assert settings_mod.MONGO_HOST == "mongodb"
            assert settings_mod.MONGO_PORT == "27017"
            assert settings_mod.GITHUB_API_URL == "https://api.github.com"

    def test_taiga_auth_url_defaults_to_api_url(self):
        env = {
            "GITHUB_SIGNATURE_KEY": "gs",
            "TAIGA_API_URL": "https://custom.taiga.io/api/v1",
            "TAIGA_SIGNATURE_KEY": "ts",
            "TAIGA_USERNAME": "u",
            "TAIGA_PASSWORD": "p",
            "HOME": os.environ.get("HOME", "/tmp"),
        }
        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
            importlib.reload(settings_mod)
            assert settings_mod.TAIGA_AUTH_URL == "https://custom.taiga.io/api/v1"
