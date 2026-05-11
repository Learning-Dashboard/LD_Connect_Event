"""Tests for datasources/requests/github_api_call.py"""

from unittest.mock import patch, MagicMock


class TestFetchCommitStats:
    @patch("datasources.requests.github_api_call.resolve", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call.requests.get")
    def test_successful_fetch(self, mock_get, mock_resolve):
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
        mock_resolve.assert_called_once_with("TestPrj", "github_token")

    @patch("datasources.requests.github_api_call.resolve", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call.requests.get")
    def test_missing_stats_key(self, mock_get, mock_resolve):
        from datasources.requests.github_api_call import fetch_commit_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}  # No "stats" key, no "parents" key
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_commit_stats("Org/repo", "sha123", "P")
        assert result == {"total": 0, "additions": 0, "deletions": 0, "is_merge": False}

    @patch("datasources.requests.github_api_call.resolve", return_value="ghp_TOKEN")
    @patch(
        "datasources.requests.github_api_call.requests.get",
        side_effect=Exception("Network error"),
    )
    def test_network_error_returns_zeros(self, mock_get, mock_resolve):
        from datasources.requests.github_api_call import fetch_commit_stats

        result = fetch_commit_stats("Org/repo", "sha123", "P")
        assert result == {"total": 0, "additions": 0, "deletions": 0, "is_merge": False}

    @patch("datasources.requests.github_api_call.resolve", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call.requests.get")
    def test_uses_correct_url(self, mock_get, mock_resolve):
        from datasources.requests.github_api_call import fetch_commit_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"stats": {}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        fetch_commit_stats("MyOrg/my-repo", "abc123", "P")
        called_url = mock_get.call_args[0][0]
        assert "MyOrg/my-repo" in called_url
        assert "abc123" in called_url

    @patch("datasources.requests.github_api_call.resolve", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call.requests.get")
    def test_headers_include_token(self, mock_get, mock_resolve):
        from datasources.requests.github_api_call import fetch_commit_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"stats": {}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        fetch_commit_stats("Org/repo", "sha", "P")
        headers = mock_get.call_args[1]["headers"]
        assert headers["Authorization"] == "token ghp_TOKEN"

    @patch("datasources.requests.github_api_call.resolve", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call.requests.get")
    def test_merge_commit_detected_by_two_parents(self, mock_get, mock_resolve):
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

    @patch("datasources.requests.github_api_call.resolve", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call.requests.get")
    def test_regular_commit_not_detected_as_merge(self, mock_get, mock_resolve):
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

    @patch("datasources.requests.github_api_call.resolve", return_value="ghp_TOKEN")
    @patch("datasources.requests.github_api_call.requests.get")
    def test_missing_parents_key_not_merge(self, mock_get, mock_resolve):
        from datasources.requests.github_api_call import fetch_commit_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"stats": {"total": 10, "additions": 10, "deletions": 0}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_commit_stats("Org/repo", "sha", "P")
        assert result["is_merge"] is False
