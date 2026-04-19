"""Tests for config/credentials_loader.py"""

import os

import pytest
from unittest.mock import patch

from config.credentials_loader import (
    CredentialsConfigInvalidError,
    CredentialsConfigNotFoundError,
    ProjectCredentialsNotFoundError,
    get_config_path,
    load,
    resolve,
)


class TestLoad:
    def test_load_returns_parsed_json(self, sample_credentials_config):
        with patch.dict(os.environ, {"CREDENTIALS_FILE": sample_credentials_config}):
            data = load()
            assert "course_a" in data
            assert data["course_a"]["github_token"] == "ghp_FAKETOKEN123"
            assert "TeamAlpha" in data["course_a"]["teams"]

    def test_load_file_not_found(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent.json")
        with patch.dict(os.environ, {"CREDENTIALS_FILE": bad_path}):
            with pytest.raises(CredentialsConfigNotFoundError, match="CREDENTIALS_FILE"):
                load()

    def test_load_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{invalid json")
        with patch.dict(os.environ, {"CREDENTIALS_FILE": str(p)}):
            with pytest.raises(CredentialsConfigInvalidError, match=str(p)):
                load()

    def test_get_config_path_resolves_relative_to_project_root(
        self, tmp_path, monkeypatch
    ):
        project_root = tmp_path / "repo"
        expected_path = project_root / "config_files" / "credentials_config.json"
        expected_path.parent.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        with patch("config.credentials_loader.PROJECT_ROOT", project_root):
            with patch.dict(
                os.environ,
                {"CREDENTIALS_FILE": "config_files/credentials_config.json"},
            ):
                assert get_config_path() == expected_path.resolve()


class TestResolve:
    def test_resolve_existing_project(self, sample_credentials_config):
        with patch.dict(os.environ, {"CREDENTIALS_FILE": sample_credentials_config}):
            token = resolve("TeamAlpha", "github_token")
            assert token == "ghp_FAKETOKEN123"

    def test_resolve_second_course(self, sample_credentials_config):
        with patch.dict(os.environ, {"CREDENTIALS_FILE": sample_credentials_config}):
            token = resolve("TeamGamma", "github_token")
            assert token == "ghp_FAKETOKEN456"

    def test_resolve_project_not_found(self, sample_credentials_config):
        with patch.dict(os.environ, {"CREDENTIALS_FILE": sample_credentials_config}):
            with pytest.raises(ProjectCredentialsNotFoundError, match="NonExistentProject"):
                resolve("NonExistentProject", "github_token")

    def test_resolve_field_missing_returns_none(self, sample_credentials_config):
        with patch.dict(os.environ, {"CREDENTIALS_FILE": sample_credentials_config}):
            result = resolve("TeamAlpha", "nonexistent_field")
            assert result is None

    def test_resolve_empty_string_field(self, sample_credentials_config):
        with patch.dict(os.environ, {"CREDENTIALS_FILE": sample_credentials_config}):
            result = resolve("TeamGamma", "taiga_user")
            assert result == ""
