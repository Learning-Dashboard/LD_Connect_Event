"""Tests for datasources/requests/taiga_api_call.py"""

import requests
from unittest.mock import patch, MagicMock


class TestMilestoneStats:
    def setup_method(self):
        """Clear the cache before each test."""
        import datasources.requests.taiga_api_call as mod

        mod._CACHE.clear()

    @patch(
        "datasources.requests.taiga_api_call.resolve",
        side_effect=lambda prj, f: {"taiga_user": "u", "taiga_password": "p"}.get(
            f, ""
        ),
    )
    @patch(
        "datasources.requests.taiga_api_call.get_taiga_token", return_value="fake_token"
    )
    @patch("datasources.requests.taiga_api_call.requests.get")
    def test_successful_fetch(self, mock_get, mock_token, mock_resolve):
        from datasources.requests.taiga_api_call import milestone_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "total_points": {"UX": 5, "Backend": 10},
            "completed_points": [3, 7],
            "total_userstories": 4,
            "completed_userstories": 2,
            "total_tasks": 10,
            "completed_tasks": 6,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = milestone_stats("proj1", "mile1", "TestPrj")
        assert result["milestone_total_points"] == 15  # 5 + 10
        assert result["milestone_closed_points"] == 10  # 3 + 7
        assert result["milestone_total_userstories"] == 4
        assert result["milestone_completed_userstories"] == 2
        assert result["milestone_total_tasks"] == 10
        assert result["milestone_completed_tasks"] == 6

    def test_empty_project_id(self):
        from datasources.requests.taiga_api_call import milestone_stats

        result = milestone_stats("", "mile1", "P")
        assert result == {}

    def test_empty_milestone_id(self):
        from datasources.requests.taiga_api_call import milestone_stats

        result = milestone_stats("proj1", "", "P")
        assert result == {}

    @patch(
        "datasources.requests.taiga_api_call.resolve",
        side_effect=lambda prj, f: {"taiga_user": "u", "taiga_password": "p"}.get(
            f, ""
        ),
    )
    @patch(
        "datasources.requests.taiga_api_call.get_taiga_token", return_value="fake_token"
    )
    @patch("datasources.requests.taiga_api_call.requests.get")
    def test_caching(self, mock_get, mock_token, mock_resolve):
        from datasources.requests.taiga_api_call import milestone_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "total_points": {"a": 1},
            "completed_points": [1],
            "total_userstories": 1,
            "completed_userstories": 0,
            "total_tasks": 1,
            "completed_tasks": 0,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        # First call
        milestone_stats("p1", "m1", "P")
        # Second call — should use cache
        milestone_stats("p1", "m1", "P")
        assert mock_get.call_count == 1  # Only called once due to caching

    @patch(
        "datasources.requests.taiga_api_call.resolve",
        side_effect=lambda prj, f: {"taiga_user": "", "taiga_password": ""}.get(f, ""),
    )
    @patch("datasources.requests.taiga_api_call.requests.get")
    def test_no_credentials_no_auth_header(self, mock_get, mock_resolve):
        from datasources.requests.taiga_api_call import milestone_stats

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "total_points": {},
            "completed_points": [],
            "total_userstories": 0,
            "completed_userstories": 0,
            "total_tasks": 0,
            "completed_tasks": 0,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        milestone_stats("p1", "m1", "P")
        headers = mock_get.call_args[1]["headers"]
        assert "Authorization" not in headers

    @patch(
        "datasources.requests.taiga_api_call.resolve",
        side_effect=lambda prj, f: {"taiga_user": "u", "taiga_password": "p"}.get(
            f, ""
        ),
    )
    @patch("datasources.requests.taiga_api_call.get_taiga_token", return_value="tok")
    @patch("datasources.requests.taiga_api_call.requests.get")
    def test_http_error_returns_zeros(self, mock_get, mock_token, mock_resolve):
        from datasources.requests.taiga_api_call import milestone_stats

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "Forbidden"
        )
        mock_get.return_value = mock_resp

        result = milestone_stats("p1", "m1", "P")
        assert result["milestone_total_points"] == 0
        assert result["milestone_closed_points"] == 0

    @patch(
        "datasources.requests.taiga_api_call.resolve",
        side_effect=lambda prj, f: {"taiga_user": "u", "taiga_password": "p"}.get(
            f, ""
        ),
    )
    @patch(
        "datasources.requests.taiga_api_call.get_taiga_token",
        side_effect=requests.exceptions.ReadTimeout("timeout"),
    )
    def test_token_timeout_returns_zeros(self, mock_token, mock_resolve):
        from datasources.requests.taiga_api_call import milestone_stats

        result = milestone_stats("p1", "m1", "P")
        assert result["milestone_total_points"] == 0
        assert result["milestone_closed_points"] == 0
        assert result["milestone_total_userstories"] == 0

    @patch(
        "datasources.requests.taiga_api_call.resolve",
        side_effect=lambda prj, f: {"taiga_user": "u", "taiga_password": "p"}.get(
            f, ""
        ),
    )
    @patch(
        "datasources.requests.taiga_api_call.get_taiga_token", return_value="fake_token"
    )
    @patch(
        "datasources.requests.taiga_api_call.requests.get",
        side_effect=requests.exceptions.ReadTimeout("timeout"),
    )
    def test_stats_timeout_returns_zeros(self, mock_get, mock_token, mock_resolve):
        from datasources.requests.taiga_api_call import milestone_stats

        result = milestone_stats("p1", "m1", "P")
        assert result["milestone_total_points"] == 0
        assert result["milestone_closed_points"] == 0
        assert result["milestone_total_userstories"] == 0
