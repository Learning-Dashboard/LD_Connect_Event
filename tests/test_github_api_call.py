"""Tests for datasources/requests/github_api_call.py"""

import pytest
from unittest.mock import patch, MagicMock

from config.credentials_loader import (
    ProjectCredentialsNotFoundError,
    SubjectCredentialsError,
)


class TestFetchCommitStats:
    @patch("datasources.requests.github_api_call.get_github_token", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call._session.get")
    def test_successful_fetch(self, mock_get, mock_token):
        from datasources.requests.github_api_call import fetch_commit_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "stats": {"total": 50, "additions": 30, "deletions": 20},
            "parents": [{"sha": "parent1"}],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_commit_stats("Org/repo", "sha123", "TestPrj")
        assert result == {"total": 50, "additions": 30, "deletions": 20, "is_merge": False}
        mock_token.assert_called_once_with("TestPrj")

    @patch("datasources.requests.github_api_call.get_github_token", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call._session.get")
    def test_missing_stats_key(self, mock_get, mock_token):
        from datasources.requests.github_api_call import fetch_commit_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}  # No "stats" key, no "parents" key
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_commit_stats("Org/repo", "sha123", "P")
        assert result == {"total": 0, "additions": 0, "deletions": 0, "is_merge": False}

    @patch("datasources.requests.github_api_call.get_github_token", return_value="ghp_TOKEN")
    @patch(
        "datasources.requests.github_api_call._session.get",
        side_effect=Exception("Network error"),
    )
    def test_network_error_returns_zeros(self, mock_get, mock_token):
        from datasources.requests.github_api_call import fetch_commit_stats

        result = fetch_commit_stats("Org/repo", "sha123", "P")
        assert result == {"total": 0, "additions": 0, "deletions": 0, "is_merge": False}

    @patch("datasources.requests.github_api_call.get_github_token", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call._session.get")
    def test_uses_correct_url(self, mock_get, mock_token):
        from datasources.requests.github_api_call import fetch_commit_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"stats": {}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        fetch_commit_stats("MyOrg/my-repo", "abc123", "P")
        called_url = mock_get.call_args[0][0]
        assert "MyOrg/my-repo" in called_url
        assert "abc123" in called_url

    @patch("datasources.requests.github_api_call.get_github_token", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call._session.get")
    def test_headers_include_token(self, mock_get, mock_token):
        from datasources.requests.github_api_call import fetch_commit_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"stats": {}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        fetch_commit_stats("Org/repo", "sha", "P")
        headers = mock_get.call_args[1]["headers"]
        assert headers["Authorization"] == "token ghp_TOKEN"

    @patch("datasources.requests.github_api_call.get_github_token", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call._session.get")
    def test_merge_commit_detected_by_two_parents(self, mock_get, mock_token):
        from datasources.requests.github_api_call import fetch_commit_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "stats": {"total": 381, "additions": 379, "deletions": 2},
            "parents": [{"sha": "parent1"}, {"sha": "parent2"}],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_commit_stats("Org/repo", "mergesha", "P")
        assert result["is_merge"] is True
        assert result["total"] == 381

    @patch("datasources.requests.github_api_call.get_github_token", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call._session.get")
    def test_regular_commit_not_detected_as_merge(self, mock_get, mock_token):
        from datasources.requests.github_api_call import fetch_commit_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "stats": {"total": 42, "additions": 40, "deletions": 2},
            "parents": [{"sha": "parent1"}],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_commit_stats("Org/repo", "regularsha", "P")
        assert result["is_merge"] is False

    @patch("datasources.requests.github_api_call.get_github_token", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call._session.get")
    def test_missing_parents_key_not_merge(self, mock_get, mock_token):
        from datasources.requests.github_api_call import fetch_commit_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"stats": {"total": 10, "additions": 10, "deletions": 0}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_commit_stats("Org/repo", "sha", "P")
        assert result["is_merge"] is False


@pytest.mark.usefixtures("sample_credentials_config")
class TestFetchCommitStatsCredentials:
    """The token is the one of the subject the team belongs to (credentials config)."""

    @pytest.mark.parametrize(
        "team, token",
        [("TeamAlpha", "ghp_FAKETOKEN123"), ("TeamGamma", "ghp_FAKETOKEN456")],
    )
    @patch("datasources.requests.github_api_call._session.get")
    def test_token_of_the_team_subject(self, mock_get, team, token):
        from datasources.requests.github_api_call import fetch_commit_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"stats": {}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        fetch_commit_stats("Org/repo", "sha", team)
        assert mock_get.call_args[1]["headers"]["Authorization"] == f"token {token}"

    @patch("datasources.requests.github_api_call._session.get")
    def test_unknown_team_raises_without_request(self, mock_get):
        from datasources.requests.github_api_call import fetch_commit_stats

        with pytest.raises(ProjectCredentialsNotFoundError):
            fetch_commit_stats("Org/repo", "sha", "UnknownTeam")
        mock_get.assert_not_called()

    @patch("datasources.requests.github_api_call._session.get")
    def test_subject_without_token_raises_without_request(
        self, mock_get, write_credentials
    ):
        from datasources.requests.github_api_call import fetch_commit_stats

        write_credentials({"subject": {"github_token": "", "teams": ["Team"]}})

        with pytest.raises(SubjectCredentialsError):
            fetch_commit_stats("Org/repo", "sha", "Team")
        mock_get.assert_not_called()
