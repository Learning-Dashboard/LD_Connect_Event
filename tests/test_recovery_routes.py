"""Tests for routes/recovery_routes.py"""

import json
from unittest.mock import patch, MagicMock


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
        import pytest
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
        import pytest
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


class TestRunTeamRecovery:
    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.collect_github")
    def test_successful_recovery(self, mock_github, mock_taiga, client):
        resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({
                "prj": "TestPrj",
                "github_url": "https://github.com/org/repo",
                "taiga_url": "my-project",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert any(s["source"] == "github" and s["status"] == "ok" for s in data["steps"])
        assert any(s["source"] == "taiga" and s["status"] == "ok" for s in data["steps"])

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
    def test_github_failure_returns_500(self, mock_github, client):
        resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({
                "prj": "P",
                "github_url": "org/repo",
                "taiga_url": "slug",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["status"] == "error"
        assert data["steps"][0]["source"] == "github"

    @patch("routes.recovery_routes.taiga_recovery_main", side_effect=Exception("taiga down"))
    @patch("routes.recovery_routes.collect_github")
    def test_taiga_failure_returns_500(self, mock_github, mock_taiga, client):
        resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({
                "prj": "P",
                "github_url": "org/repo",
                "taiga_url": "slug",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["status"] == "error"
        assert data["steps"][-1]["source"] == "taiga"

    @patch("routes.recovery_routes.taiga_recovery_main", side_effect=SystemExit("1"))
    @patch("routes.recovery_routes.collect_github")
    def test_taiga_systemexit_returns_500(self, mock_github, mock_taiga, client):
        resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({
                "prj": "P",
                "github_url": "org/repo",
                "taiga_url": "slug",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 500

    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.collect_github")
    def test_with_dates_and_token(self, mock_github, mock_taiga, client):
        resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({
                "prj": "P",
                "github_url": "org/repo",
                "taiga_url": "slug",
                "from_date": "2025-01-01",
                "to_date": "2025-12-31",
                "taiga_token": "my-token",
                "github_token": "gh-token",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        taiga_args = mock_taiga.call_args[0][0]
        assert "--from-date" in taiga_args
        assert "--to-date" in taiga_args
        assert "--taiga-token" in taiga_args

    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.get_organization_repos", return_value=["repo1", "repo2"])
    @patch("routes.recovery_routes.collect_github")
    def test_org_only_recovers_all_repos(self, mock_github, mock_get_repos, mock_taiga, client):
        resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({
                "prj": "P",
                "github_url": "https://github.com/myorg",
                "taiga_url": "slug",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert mock_github.call_count == 2

    @patch("routes.recovery_routes.taiga_recovery_main")
    @patch("routes.recovery_routes.get_organization_repos", return_value=[])
    @patch("routes.recovery_routes.collect_github")
    def test_no_repos_found_returns_500(self, mock_github, mock_get_repos, mock_taiga, client):
        resp = client.post(
            "/admin/recovery/team",
            data=json.dumps({
                "prj": "P",
                "github_url": "https://github.com/myorg",
                "taiga_url": "slug",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 500
