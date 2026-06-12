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

class TestRunTeamRecovery:
    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.collect_github")
    def test_successful_recovery(self, mock_github, mock_taiga, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": "TestPrj",
            "github_url": "https://github.com/org/repo",
            "taiga_url": "my-project",
        })
        assert job["status"] == "done"
        assert any(s["source"] == "github" and s["status"] == "ok" for s in job["steps"])
        assert any(s["source"] == "taiga" and s["status"] == "ok" for s in job["steps"])

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
            data=json.dumps({"prj": "P", "taiga_url": "slug"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "github_url" in resp.get_json()["error"]

    def test_missing_taiga_url_returns_400(self, client):
        resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({"prj": "P", "github_url": "org/repo"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "taiga_url" in resp.get_json()["error"]

    def test_invalid_github_url_returns_400(self, client):
        resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({"prj": "P", "github_url": "", "taiga_url": "slug"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    @patch("routes.recovery_routes.collect_github", side_effect=Exception("github down"))
    @patch("routes.recovery_routes.taiga_recovery_main")
    def test_github_failure_continues_to_taiga(self, mock_taiga, mock_github, client, sync_executor):
        """When GitHub fails the job continues with Taiga and ends as error."""
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": "P",
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
            "prj": "P",
            "github_url": "org/repo",
            "taiga_url": "slug",
        })
        assert job["status"] == "error"
        assert any(s["source"] == "taiga" and s["status"] == "error" for s in job["steps"])

    @patch("routes.recovery_routes.taiga_recovery_main", side_effect=SystemExit("1"))
    @patch("routes.recovery_routes.collect_github")
    def test_taiga_systemexit_marks_job_error(self, mock_github, mock_taiga, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": "P",
            "github_url": "org/repo",
            "taiga_url": "slug",
        })
        assert job["status"] == "error"
        assert any(s["source"] == "taiga" and s["status"] == "error" for s in job["steps"])

    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.collect_github")
    def test_with_dates_and_token(self, mock_github, mock_taiga, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": "P",
            "github_url": "org/repo",
            "taiga_url": "slug",
            "from_date": "2025-01-01",
            "to_date": "2025-12-31",
            "taiga_token": "my-token",
            "github_token": "gh-token",
        })
        assert job["status"] == "done"
        taiga_args = mock_taiga.call_args[0][0]
        assert "--from-date" in taiga_args
        assert "--to-date" in taiga_args
        assert "--taiga-token" in taiga_args

    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.get_organization_repos", return_value=["repo1", "repo2"])
    @patch("routes.recovery_routes.collect_github")
    def test_org_only_recovers_all_repos(self, mock_github, mock_get_repos, mock_taiga, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": "P",
            "github_url": "https://github.com/myorg",
            "taiga_url": "slug",
        })
        assert job["status"] == "done"
        assert mock_github.call_count == 2

    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.get_organization_repos", return_value=[])
    @patch("routes.recovery_routes.collect_github")
    def test_no_repos_found_marks_job_error(self, mock_github, mock_get_repos, mock_taiga, client, sync_executor):
        job = _start_and_get_status(client, "/admin/recovery/team", {
            "prj": "P",
            "github_url": "https://github.com/myorg",
            "taiga_url": "slug",
        })
        assert job["status"] == "error"
        assert any(s["source"] == "github" and s["status"] == "error" for s in job["steps"])


# ── Status endpoint ───────────────────────────────────────────────────────────

class TestGetRecoveryStatus:
    def test_unknown_job_returns_404(self, client):
        resp = client.get("/admin/recovery/status/nonexistent-id")
        assert resp.status_code == 404

    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.collect_github")
    def test_status_reflects_done(self, mock_github, mock_taiga, client, sync_executor):
        post_resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({"prj": "P", "github_url": "org/repo", "taiga_url": "slug"}),
            content_type="application/json",
        )
        job_id = post_resp.get_json()["job_id"]
        status = client.get(f"/admin/recovery/status/{job_id}").get_json()
        assert status["status"] == "done"
        assert "steps" in status
        assert "created_at" in status
