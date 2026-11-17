"""Tests for routes/recovery_routes.py"""

import json
import pytest
from unittest.mock import patch


# ── Fixture: run background tasks synchronously ───────────────────────────────

@pytest.fixture(autouse=False)
def sync_executor(monkeypatch):
    """Replace the async executor so background tasks run synchronously in tests."""
    class _SyncExecutor:
        def submit(self, fn, *args, **kwargs):
            fn(*args, **kwargs)

    monkeypatch.setattr("routes.recovery_routes._recovery_executor", _SyncExecutor())


def _start_and_get_status(client, url, payload):
    """POST to a recovery endpoint, then GET the status. Returns the final job dict."""
    resp = client.post(url, data=json.dumps(payload), content_type="application/json")
    assert resp.status_code == 202
    job_id = resp.get_json()["job_id"]
    status_resp = client.get(f"/admin/recovery/status/{job_id}")
    assert status_resp.status_code == 200
    return status_resp.get_json()


# ── URL / slug parsing (unchanged, synchronous helpers) ──────────────────────

class TestParseGithubUrl:
    def test_full_https_url(self):
        from routes.recovery_routes import _parse_github_url
        org, repo = _parse_github_url("https://github.com/myorg/myrepo")
        assert org == "myorg"
        assert repo == "myrepo"

    def test_url_with_git_suffix(self):
        from routes.recovery_routes import _parse_github_url
        org, repo = _parse_github_url("https://github.com/myorg/myrepo.git")
        assert org == "myorg"
        assert repo == "myrepo"

    def test_org_only_url(self):
        from routes.recovery_routes import _parse_github_url
        org, repo = _parse_github_url("https://github.com/myorg")
        assert org == "myorg"
        assert repo is None

    def test_short_org_slash_repo(self):
        from routes.recovery_routes import _parse_github_url
        org, repo = _parse_github_url("myorg/myrepo")
        assert org == "myorg"
        assert repo == "myrepo"

    def test_short_org_only(self):
        from routes.recovery_routes import _parse_github_url
        org, repo = _parse_github_url("myorg")
        assert org == "myorg"
        assert repo is None

    def test_api_repos_style(self):
        from routes.recovery_routes import _parse_github_url
        org, repo = _parse_github_url("https://github.com/repos/myorg/myrepo")
        assert org == "myorg"
        assert repo == "myrepo"

    def test_empty_raises(self):
        from routes.recovery_routes import _parse_github_url
        with pytest.raises(ValueError):
            _parse_github_url("")


class TestParseTaigaSlug:
    def test_full_url(self):
        from routes.recovery_routes import _parse_taiga_slug
        assert _parse_taiga_slug("https://taiga.io/project/my-project/") == "my-project"

    def test_plain_slug(self):
        from routes.recovery_routes import _parse_taiga_slug
        assert _parse_taiga_slug("my-project") == "my-project"

    def test_slug_with_slashes(self):
        from routes.recovery_routes import _parse_taiga_slug
        assert _parse_taiga_slug("/my-project/") == "my-project"

    def test_url_no_project_keyword(self):
        from routes.recovery_routes import _parse_taiga_slug
        assert _parse_taiga_slug("https://taiga.io/my-project") == "my-project"

    def test_empty_raises(self):
        from routes.recovery_routes import _parse_taiga_slug
        with pytest.raises(ValueError):
            _parse_taiga_slug("")


class TestToIsoUtc:
    def test_none_returns_none(self):
        from routes.recovery_routes import _to_iso_utc
        assert _to_iso_utc(None) is None

    def test_empty_returns_none(self):
        from routes.recovery_routes import _to_iso_utc
        assert _to_iso_utc("") is None

    def test_date_converted(self):
        from routes.recovery_routes import _to_iso_utc
        result = _to_iso_utc("2025-01-15")
        assert result is not None
        assert result.endswith("Z")
        assert "T" in result


# ── Team recovery ─────────────────────────────────────────────────────────────

# Teams of tests/conftest.py::sample_credentials_config
TEAM = "TeamAlpha"  # subject course_a, GitHub token ghp_FAKETOKEN123
OTHER_SUBJECT_TEAM = "TeamGamma"  # subject course_b, GitHub token ghp_FAKETOKEN456


@pytest.mark.usefixtures("sample_credentials_config")
class TestRunTeamRecovery:
    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.collect_github")
    def test_successful_recovery(self, mock_github, mock_taiga, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": TEAM,
            "github_url": "https://github.com/org/repo",
            "taiga_url": "my-project",
        })
        assert job["status"] == "done"
        assert [(s["source"], s["status"]) for s in job["steps"]] == [
            ("github", "ok"),
            ("taiga", "ok"),
        ]

    @pytest.mark.parametrize(
        "team, token",
        [(TEAM, "ghp_FAKETOKEN123"), (OTHER_SUBJECT_TEAM, "ghp_FAKETOKEN456")],
    )
    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.collect_github")
    def test_uses_the_github_token_of_the_team_subject(
        self, mock_github, mock_taiga, client, sync_executor, team, token
    ):
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": team,
            "github_url": "org/repo",
            "taiga_url": "slug",
        })
        assert job["status"] == "done"
        assert mock_github.call_args.kwargs["github_token"] == token
        assert mock_github.call_args.kwargs["prj"] == team

    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.collect_github")
    def test_tokens_in_the_payload_are_ignored(
        self, mock_github, mock_taiga, client, sync_executor
    ):
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": TEAM,
            "github_url": "org/repo",
            "taiga_url": "slug",
            "taiga_token": "my-token",
            "github_token": "gh-token",
        })
        assert job["status"] == "done"
        assert mock_github.call_args.kwargs["github_token"] == "ghp_FAKETOKEN123"
        taiga_args = mock_taiga.call_args[0][0]
        assert "--taiga-token" not in taiga_args
        assert "my-token" not in taiga_args

    def test_missing_prj_returns_400(self, client):
        resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({"github_url": "org/repo", "taiga_url": "slug"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "prj" in resp.get_json()["error"]

    def test_missing_github_url_returns_400(self, client):
        resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({"prj": TEAM, "taiga_url": "slug"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "github_url" in resp.get_json()["error"]

    def test_missing_taiga_url_returns_400(self, client):
        resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({"prj": TEAM, "github_url": "org/repo"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "taiga_url" in resp.get_json()["error"]

    def test_invalid_github_url_returns_400(self, client):
        resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({"prj": TEAM, "github_url": "", "taiga_url": "slug"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    @patch("routes.recovery_routes.collect_github", side_effect=Exception("github down"))
    @patch("routes.recovery_routes.taiga_recovery_main")
    def test_github_failure_continues_to_taiga(self, mock_taiga, mock_github, client, sync_executor):
        """When GitHub fails the job continues with Taiga and ends as error."""
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": TEAM,
            "github_url": "org/repo",
            "taiga_url": "slug",
        })
        assert job["status"] == "error"
        assert any(s["source"] == "github" and s["status"] == "error" for s in job["steps"])
        assert any(s["source"] == "taiga" and s["status"] == "ok" for s in job["steps"])

    @patch("routes.recovery_routes.taiga_recovery_main", side_effect=Exception("taiga down"))
    @patch("routes.recovery_routes.collect_github")
    def test_taiga_failure_marks_job_error(self, mock_github, mock_taiga, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": TEAM,
            "github_url": "org/repo",
            "taiga_url": "slug",
        })
        assert job["status"] == "error"
        assert any(s["source"] == "taiga" and s["status"] == "error" for s in job["steps"])

    @patch("routes.recovery_routes.taiga_recovery_main", side_effect=SystemExit("1"))
    @patch("routes.recovery_routes.collect_github")
    def test_taiga_systemexit_marks_job_error(self, mock_github, mock_taiga, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": TEAM,
            "github_url": "org/repo",
            "taiga_url": "slug",
        })
        assert job["status"] == "error"
        assert any(s["source"] == "taiga" and s["status"] == "error" for s in job["steps"])

    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.collect_github")
    def test_with_dates(self, mock_github, mock_taiga, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": TEAM,
            "github_url": "org/repo",
            "taiga_url": "slug",
            "from_date": "2025-01-01",
            "to_date": "2025-12-31",
        })
        assert job["status"] == "done"
        taiga_args = mock_taiga.call_args[0][0]
        assert taiga_args[taiga_args.index("--prj") + 1] == TEAM
        assert taiga_args[taiga_args.index("--slug") + 1] == "slug"
        assert taiga_args[taiga_args.index("--from-date") + 1] == "2025-01-01"
        assert taiga_args[taiga_args.index("--to-date") + 1] == "2025-12-31"
        assert mock_github.call_args.kwargs["since"] is not None
        assert mock_github.call_args.kwargs["until"] is not None

    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.get_organization_repos", return_value=["repo1", "repo2"])
    @patch("routes.recovery_routes.collect_github")
    def test_org_only_recovers_all_repos(self, mock_github, mock_get_repos, mock_taiga, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": TEAM,
            "github_url": "https://github.com/myorg",
            "taiga_url": "slug",
        })
        assert job["status"] == "done"
        assert mock_github.call_count == 2
        # The repositories of the organization are listed with the subject's token
        org, headers = mock_get_repos.call_args.args
        assert org == "myorg"
        assert headers["Authorization"] == "Bearer ghp_FAKETOKEN123"

    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.get_organization_repos", return_value=[])
    @patch("routes.recovery_routes.collect_github")
    def test_no_repos_found_marks_job_error(self, mock_github, mock_get_repos, mock_taiga, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": TEAM,
            "github_url": "https://github.com/myorg",
            "taiga_url": "slug",
        })
        assert job["status"] == "error"
        assert any(s["source"] == "github" and s["status"] == "error" for s in job["steps"])


# ── Single-source recovery ────────────────────────────────────────────────────

@pytest.mark.usefixtures("sample_credentials_config")
class TestRunGithubRecovery:
    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.collect_github")
    def test_runs_only_github(self, mock_github, mock_taiga, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/github", {
            "prj": OTHER_SUBJECT_TEAM,
            "github_url": "org/repo",
        })
        assert job["status"] == "done"
        assert [(s["source"], s["status"]) for s in job["steps"]] == [("github", "ok")]
        assert mock_github.call_args.kwargs["github_token"] == "ghp_FAKETOKEN456"
        mock_taiga.assert_not_called()

    @patch("routes.recovery_routes.collect_github", side_effect=Exception("github down"))
    def test_failure_marks_job_error(self, mock_github, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/github", {
            "prj": TEAM,
            "github_url": "org/repo",
        })
        assert job["status"] == "error"
        assert job["steps"] == [
            {"source": "github", "status": "error", "error": "github down"}
        ]

    def test_missing_github_url_returns_400(self, client):
        resp = client.post(
            "/admin/recovery/github",
            data=json.dumps({"prj": TEAM}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "github_url" in resp.get_json()["error"]

    @patch("routes.recovery_routes.collect_github")
    def test_does_not_need_taiga_credentials(
        self, mock_github, client, sync_executor, write_credentials
    ):
        """A subject with a broken Taiga entry can still recover GitHub."""
        write_credentials(
            {
                "subject": {
                    "github_token": "ghp_x",
                    "taiga_api_url": "https://taiga.example/api/v1",
                    "teams": ["Team"],
                }
            }
        )
        job = _start_and_get_status(client, "/admin/recovery/github", {
            "prj": "Team",
            "github_url": "org/repo",
        })
        assert job["status"] == "done"


@pytest.mark.usefixtures("sample_credentials_config")
class TestRunTaigaRecovery:
    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.collect_github")
    def test_runs_only_taiga(self, mock_github, mock_taiga, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/taiga", {
            "prj": OTHER_SUBJECT_TEAM,
            "taiga_url": "https://tree.taiga.io/project/my-project/",
            "taiga_events": ["task", "epic"],
        })
        assert job["status"] == "done"
        assert [(s["source"], s["status"]) for s in job["steps"]] == [("taiga", "ok")]
        assert mock_taiga.call_args[0][0] == [
            "--slug", "my-project", "--prj", OTHER_SUBJECT_TEAM,
            "--events", "task,epic",
            "--quality-model", "default",
        ]
        mock_github.assert_not_called()

    def test_missing_taiga_url_returns_400(self, client):
        resp = client.post(
            "/admin/recovery/taiga",
            data=json.dumps({"prj": TEAM}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "taiga_url" in resp.get_json()["error"]

    @patch("routes.recovery_routes.taiga_recovery_main")
    def test_does_not_need_a_github_token(
        self, mock_taiga, client, sync_executor, write_credentials
    ):
        write_credentials({"subject": {"taiga_token": "tok", "teams": ["Team"]}})
        job = _start_and_get_status(client, "/admin/recovery/taiga", {
            "prj": "Team",
            "taiga_url": "slug",
        })
        assert job["status"] == "done"


# ── Credentials are resolved before the job is queued ─────────────────────────

RECOVERY_REQUESTS = [
    ("/admin/recovery/team", {"github_url": "org/repo", "taiga_url": "slug"}),
    ("/admin/recovery/github", {"github_url": "org/repo"}),
    ("/admin/recovery/taiga", {"taiga_url": "slug"}),
]


@pytest.mark.parametrize("url, body", RECOVERY_REQUESTS)
class TestRecoveryCredentials:
    @patch("routes.recovery_routes.create_job")
    def test_unknown_team_returns_400_without_job(
        self, mock_create_job, client, sample_credentials_config, url, body
    ):
        resp = client.post(
            url,
            data=json.dumps({"prj": "UnknownTeam", **body}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Unknown project credentials"
        mock_create_job.assert_not_called()

    @patch("routes.recovery_routes.create_job")
    def test_broken_subject_returns_500_without_job(
        self, mock_create_job, client, write_credentials, url, body
    ):
        # No GitHub token, and its own Taiga server without credentials
        write_credentials(
            {
                "subject": {
                    "github_token": "",
                    "taiga_api_url": "https://taiga.example/api/v1",
                    "taiga_auth_url": "https://taiga.example/api/v1/auth",
                    "teams": ["Team"],
                }
            }
        )
        resp = client.post(
            url,
            data=json.dumps({"prj": "Team", **body}),
            content_type="application/json",
        )
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "Credentials configuration error"
        mock_create_job.assert_not_called()


# ── Status endpoint ───────────────────────────────────────────────────────────

class TestGetRecoveryStatus:
    def test_unknown_job_returns_404(self, client):
        resp = client.get("/admin/recovery/status/nonexistent-id")
        assert resp.status_code == 404

    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.collect_github")
    def test_status_reflects_done(
        self, mock_github, mock_taiga, client, sync_executor, sample_credentials_config
    ):
        post_resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({"prj": TEAM, "github_url": "org/repo", "taiga_url": "slug"}),
            content_type="application/json",
        )
        job_id = post_resp.get_json()["job_id"]
        status = client.get(f"/admin/recovery/status/{job_id}").get_json()
        assert status["status"] == "done"
        assert "steps" in status
        assert "created_at" in status
