"""Tests for config/credentials_loader.py"""
import json, os, pytest
from unittest.mock import patch


class TestLoad:
    def test_load_returns_parsed_json(self, sample_credentials_config):
        with patch("config.credentials_loader.CONFIG_FILE", sample_credentials_config):
            from config.credentials_loader import load
            data = load()
            assert "course_a" in data
            assert data["course_a"]["github_token"] == "ghp_FAKETOKEN123"
            assert "TeamAlpha" in data["course_a"]["teams"]

    def test_load_file_not_found(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent.json")
        with patch("config.credentials_loader.CONFIG_FILE", bad_path):
            from config.credentials_loader import load
            with pytest.raises(FileNotFoundError):
                load()

    def test_load_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{invalid json")
        with patch("config.credentials_loader.CONFIG_FILE", str(p)):
            from config.credentials_loader import load
            with pytest.raises(json.JSONDecodeError):
                load()


class TestResolve:
    def test_resolve_existing_project(self, sample_credentials_config):
        with patch("config.credentials_loader.CONFIG_FILE", sample_credentials_config):
            from config.credentials_loader import resolve
            token = resolve("TeamAlpha", "github_token")
            assert token == "ghp_FAKETOKEN123"

    def test_resolve_second_course(self, sample_credentials_config):
        with patch("config.credentials_loader.CONFIG_FILE", sample_credentials_config):
            from config.credentials_loader import resolve
            token = resolve("TeamGamma", "github_token")
            assert token == "ghp_FAKETOKEN456"

    def test_resolve_project_not_found(self, sample_credentials_config):
        with patch("config.credentials_loader.CONFIG_FILE", sample_credentials_config):
            from config.credentials_loader import resolve
            with pytest.raises(KeyError, match="NonExistentProject"):
                resolve("NonExistentProject", "github_token")

    def test_resolve_field_missing_returns_none(self, sample_credentials_config):
        with patch("config.credentials_loader.CONFIG_FILE", sample_credentials_config):
            from config.credentials_loader import resolve
            result = resolve("TeamAlpha", "nonexistent_field")
            assert result is None

    def test_resolve_empty_string_field(self, sample_credentials_config):
        with patch("config.credentials_loader.CONFIG_FILE", sample_credentials_config):
            from config.credentials_loader import resolve
            result = resolve("TeamGamma", "taiga_user")
            assert result == ""
