"""Tests for config/credentials_loader.py"""

import json
import os

import pytest
from unittest.mock import patch

from config.credentials_loader import (
    CredentialsConfigInvalidError,
    CredentialsConfigNotFoundError,
    ProjectCredentialsNotFoundError,
    SubjectCredentialsError,
    TaigaContext,
    get_config_path,
    get_github_token,
    get_subject,
    get_taiga_context,
    load,
    validate_config,
)
from tests.conftest import (
    FALLBACK_TAIGA_API_URL,
    FALLBACK_TAIGA_AUTH_URL,
    OWN_TAIGA_API_URL,
    OWN_TAIGA_AUTH_URL,
)


def _subject(**overrides) -> dict:
    """One subject entry with a team called "Team"; overrides replace its fields."""
    props = {"github_token": "ghp_x", "teams": ["Team"]}
    props.update(overrides)
    return {"subject": props}


class TestLoad:
    def test_load_returns_parsed_json(self, sample_credentials_config):
        data = load()
        assert "course_a" in data
        assert data["course_a"]["github_token"] == "ghp_FAKETOKEN123"
        assert "TeamAlpha" in data["course_a"]["teams"]

    def test_load_file_not_found(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent.json")
        with patch.dict(os.environ, {"CREDENTIALS_FILE": bad_path}):
            with pytest.raises(CredentialsConfigNotFoundError, match="CREDENTIALS_FILE"):
                load()

    def test_load_invalid_json(self, write_credentials):
        path = write_credentials("{invalid json")
        with pytest.raises(CredentialsConfigInvalidError, match=path):
            load()

    def test_load_rejects_non_object(self, write_credentials):
        write_credentials(["not", "an", "object"])
        with pytest.raises(CredentialsConfigInvalidError, match="JSON object"):
            load()

    def test_load_does_not_reread_unchanged_file(self, sample_credentials_config):
        first = load()
        with patch("config.credentials_loader.json.load") as mock_json_load:
            assert load() is first
        mock_json_load.assert_not_called()

    def test_load_rereads_file_when_it_changes(self, sample_credentials_config):
        assert get_github_token("TeamAlpha") == "ghp_FAKETOKEN123"

        stat = os.stat(sample_credentials_config)
        with open(sample_credentials_config, "w", encoding="utf-8") as fh:
            json.dump(_subject(github_token="ghp_ROTATED", teams=["TeamAlpha"]), fh)
        # Same-size rewrites within the timestamp resolution must be detected too
        os.utime(
            sample_credentials_config,
            ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000),
        )

        assert get_github_token("TeamAlpha") == "ghp_ROTATED"

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


class TestSubjectLookup:
    def test_get_subject(self, sample_credentials_config):
        assert get_subject("TeamAlpha") == "course_a"
        assert get_subject("TeamBeta") == "course_a"
        assert get_subject("TeamGamma") == "course_b"

    def test_unknown_team(self, sample_credentials_config):
        with pytest.raises(ProjectCredentialsNotFoundError, match="NonExistentProject"):
            get_subject("NonExistentProject")

    def test_subject_without_teams_list_is_ignored(self, write_credentials):
        write_credentials({"broken": {"github_token": "ghp_x"}, "not_an_object": "x"})
        with pytest.raises(ProjectCredentialsNotFoundError):
            get_subject("Team")


class TestGithubToken:
    def test_token_of_each_subject(self, sample_credentials_config):
        assert get_github_token("TeamAlpha") == "ghp_FAKETOKEN123"
        assert get_github_token("TeamGamma") == "ghp_FAKETOKEN456"

    def test_token_is_stripped(self, write_credentials):
        write_credentials(_subject(github_token="  ghp_x \n"))
        assert get_github_token("Team") == "ghp_x"

    def test_unknown_team(self, sample_credentials_config):
        with pytest.raises(ProjectCredentialsNotFoundError, match="Nope"):
            get_github_token("Nope")

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_missing_token_is_a_config_error(self, write_credentials, value):
        write_credentials(_subject(github_token=value))
        with pytest.raises(SubjectCredentialsError, match="github_token"):
            get_github_token("Team")


class TestTaigaContext:
    """Resolution rule: own server or fallback server, then token, user/password or fallback login."""

    def test_own_server_with_token(self, write_credentials):
        write_credentials(
            _subject(
                taiga_api_url=OWN_TAIGA_API_URL,
                taiga_auth_url=OWN_TAIGA_AUTH_URL,
                taiga_token="app:token",
            )
        )
        assert get_taiga_context("Team") == TaigaContext(
            api_url=OWN_TAIGA_API_URL, auth_url=OWN_TAIGA_AUTH_URL, token="app:token"
        )

    def test_own_server_with_user_and_password(self, write_credentials):
        write_credentials(
            _subject(
                taiga_api_url=OWN_TAIGA_API_URL,
                taiga_auth_url=OWN_TAIGA_AUTH_URL,
                taiga_user="user",
                taiga_password="pass",
            )
        )
        assert get_taiga_context("Team") == TaigaContext(
            api_url=OWN_TAIGA_API_URL,
            auth_url=OWN_TAIGA_AUTH_URL,
            username="user",
            password="pass",
        )

    def test_token_wins_over_user_and_password(self, write_credentials):
        write_credentials(
            _subject(
                taiga_api_url=OWN_TAIGA_API_URL,
                taiga_auth_url=OWN_TAIGA_AUTH_URL,
                taiga_token="tok",
                taiga_user="user",
                taiga_password="pass",
            )
        )
        ctx = get_taiga_context("Team")
        assert ctx.token == "tok"
        assert ctx.username == ""
        assert ctx.password == ""

    def test_own_server_never_uses_fallback_credentials(self, write_credentials):
        write_credentials(
            _subject(taiga_api_url=OWN_TAIGA_API_URL, taiga_auth_url=OWN_TAIGA_AUTH_URL)
        )
        with pytest.raises(SubjectCredentialsError, match="neither taiga_token"):
            get_taiga_context("Team")

    @pytest.mark.parametrize(
        "urls",
        [
            {"taiga_api_url": OWN_TAIGA_API_URL, "taiga_auth_url": ""},
            {"taiga_api_url": "", "taiga_auth_url": OWN_TAIGA_AUTH_URL},
            {"taiga_api_url": OWN_TAIGA_API_URL},
        ],
    )
    def test_only_one_url_is_a_config_error(self, write_credentials, urls):
        write_credentials(_subject(taiga_token="tok", **urls))
        with pytest.raises(SubjectCredentialsError, match="both taiga_api_url"):
            get_taiga_context("Team")

    def test_urls_are_normalised(self, write_credentials):
        write_credentials(
            _subject(
                taiga_api_url=f"  {OWN_TAIGA_API_URL}/ ",
                taiga_auth_url=f"{OWN_TAIGA_AUTH_URL}/",
                taiga_token="tok",
            )
        )
        ctx = get_taiga_context("Team")
        assert ctx.api_url == OWN_TAIGA_API_URL
        assert ctx.auth_url == OWN_TAIGA_AUTH_URL

    @pytest.mark.parametrize(
        "urls", [{}, {"taiga_api_url": "", "taiga_auth_url": ""}, {"taiga_api_url": None}]
    )
    def test_fallback_server_with_fallback_credentials(self, write_credentials, urls):
        write_credentials(_subject(**urls))
        assert get_taiga_context("Team") == TaigaContext(
            api_url=FALLBACK_TAIGA_API_URL,
            auth_url=FALLBACK_TAIGA_AUTH_URL,
            username="fallback_user",
            password="fallback_pass",
        )

    def test_fallback_server_with_subject_user_and_password(self, write_credentials):
        write_credentials(_subject(taiga_user="user", taiga_password="pass"))
        assert get_taiga_context("Team") == TaigaContext(
            api_url=FALLBACK_TAIGA_API_URL,
            auth_url=FALLBACK_TAIGA_AUTH_URL,
            username="user",
            password="pass",
        )

    def test_fallback_server_with_subject_token(self, write_credentials):
        write_credentials(_subject(taiga_token="tok"))
        assert get_taiga_context("Team") == TaigaContext(
            api_url=FALLBACK_TAIGA_API_URL, auth_url=FALLBACK_TAIGA_AUTH_URL, token="tok"
        )

    def test_incomplete_subject_login_uses_fallback_credentials(self, write_credentials):
        write_credentials(_subject(taiga_user="user", taiga_password=""))
        ctx = get_taiga_context("Team")
        assert (ctx.username, ctx.password) == ("fallback_user", "fallback_pass")

    @pytest.mark.parametrize(
        "setting", ["TAIGA_FALLBACK_API_URL", "TAIGA_FALLBACK_AUTH_URL"]
    )
    def test_fallback_server_not_configured(self, write_credentials, monkeypatch, setting):
        write_credentials(_subject(taiga_token="tok"))
        monkeypatch.setattr(f"config.settings.{setting}", "")
        with pytest.raises(SubjectCredentialsError, match="TAIGA_FALLBACK_API_URL"):
            get_taiga_context("Team")

    @pytest.mark.parametrize(
        "setting", ["TAIGA_FALLBACK_USERNAME", "TAIGA_FALLBACK_PASSWORD"]
    )
    def test_fallback_credentials_not_configured(
        self, write_credentials, monkeypatch, setting
    ):
        write_credentials(_subject())
        monkeypatch.setattr(f"config.settings.{setting}", "")
        with pytest.raises(SubjectCredentialsError, match="TAIGA_FALLBACK_USERNAME"):
            get_taiga_context("Team")

    def test_unknown_team(self, sample_credentials_config):
        with pytest.raises(ProjectCredentialsNotFoundError, match="Nope"):
            get_taiga_context("Nope")

    def test_repr_hides_secrets(self):
        ctx = TaigaContext(
            api_url="a", auth_url="b", token="s3cret-token", username="u", password="s3cret-pass"
        )
        assert "s3cret" not in repr(ctx)


class TestValidateConfig:
    def test_valid_config_has_no_problems(self, sample_credentials_config):
        assert validate_config() == []

    def test_reports_every_problem(self, write_credentials):
        write_credentials(
            {
                "no_object": "x",
                "no_teams": {"github_token": "ghp_x", "taiga_token": "tok"},
                "no_github": {"taiga_token": "tok", "teams": ["A"]},
                "half_urls": {
                    "github_token": "ghp_x",
                    "taiga_api_url": OWN_TAIGA_API_URL,
                    "taiga_token": "tok",
                    "teams": ["B"],
                },
                "duplicate": {"github_token": "ghp_x", "taiga_token": "tok", "teams": ["A"]},
            }
        )
        problems = validate_config()

        assert len(problems) == 5
        text = "\n".join(problems)
        assert "'no_object' must be a JSON object" in text
        assert "'no_teams' must have a 'teams' list" in text
        assert "'no_github' has no github_token" in text
        assert "'half_urls' must set both taiga_api_url and taiga_auth_url" in text
        assert "Team 'A' is listed under subjects 'no_github' and 'duplicate'" in text

    def test_reports_missing_fallback_settings(self, write_credentials, monkeypatch):
        write_credentials(_subject())
        monkeypatch.setattr("config.settings.TAIGA_FALLBACK_API_URL", "")
        problems = validate_config()
        assert len(problems) == 1
        assert "TAIGA_FALLBACK_API_URL" in problems[0]

    def test_invalid_file_raises(self, write_credentials):
        write_credentials("{invalid json")
        with pytest.raises(CredentialsConfigInvalidError):
            validate_config()
