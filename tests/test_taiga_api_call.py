"""Tests for datasources/requests/taiga_api_call.py"""

import pytest
import requests
from unittest.mock import patch, MagicMock

from tests.conftest import (
    FALLBACK_TAIGA_API_URL,
    FALLBACK_TAIGA_AUTH_URL,
    OWN_TAIGA_API_URL,
)

# Teams of tests/conftest.py::sample_credentials_config
OWN_SERVER_TEAM = "TeamAlpha"  # subject with its own Taiga and a static token
FALLBACK_TEAM = "TeamGamma"  # subject on the fallback Taiga (login)

STATS = {
    "total_points": {"UX": 5, "Backend": 10},
    "completed_points": [3, 7],
    "total_userstories": 4,
    "completed_userstories": 2,
    "total_tasks": 10,
    "completed_tasks": 6,
}


def _response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear every cache before each test."""
    import datasources.requests.taiga_api_call as mod
    import utils.taiga_token.taiga_auth as auth_mod

    caches = (
        mod._CACHE,
        mod._DETAILS_CACHE,
        mod._USERSTORY_CACHE,
        mod._US_CUSTOM_ATTR_NAMES_CACHE,
        mod._TASK_CUSTOM_ATTR_NAMES_CACHE,
        auth_mod._TOKENS,
    )
    for cache in caches:
        cache.clear()
    yield
    for cache in caches:
        cache.clear()


@pytest.fixture
def mock_get():
    with patch("datasources.requests.taiga_api_call._session.get") as mocked:
        yield mocked


@pytest.fixture
def mock_login():
    """Login endpoint of any Taiga server; returns the token "login_tok"."""
    with patch("utils.taiga_token.taiga_auth.requests.post") as mocked:
        mocked.return_value = _response({"auth_token": "login_tok"})
        yield mocked


@pytest.mark.usefixtures("sample_credentials_config")
class TestMilestoneStats:
    def test_successful_fetch(self, mock_get):
        from datasources.requests.taiga_api_call import milestone_stats

        mock_get.return_value = _response(STATS)

        result = milestone_stats("proj1", "mile1", OWN_SERVER_TEAM)
        assert result["milestone_total_points"] == 15  # 5 + 10
        assert result["milestone_closed_points"] == 10  # 3 + 7
        assert result["milestone_total_userstories"] == 4
        assert result["milestone_completed_userstories"] == 2
        assert result["milestone_total_tasks"] == 10
        assert result["milestone_completed_tasks"] == 6

    def test_empty_project_id(self):
        from datasources.requests.taiga_api_call import milestone_stats

        result = milestone_stats("", "mile1", OWN_SERVER_TEAM)
        assert result == {}

    def test_empty_milestone_id(self):
        from datasources.requests.taiga_api_call import milestone_stats

        result = milestone_stats("proj1", "", OWN_SERVER_TEAM)
        assert result == {}

    def test_caching(self, mock_get):
        from datasources.requests.taiga_api_call import milestone_stats

        mock_get.return_value = _response(STATS)

        # First call
        milestone_stats("p1", "m1", OWN_SERVER_TEAM)
        # Second call — should use cache
        milestone_stats("p1", "m1", OWN_SERVER_TEAM)
        assert mock_get.call_count == 1  # Only called once due to caching

    def test_own_server_uses_subject_url_and_token(self, mock_get, mock_login):
        from datasources.requests.taiga_api_call import milestone_stats

        mock_get.return_value = _response(STATS)

        milestone_stats("p1", "m1", OWN_SERVER_TEAM)

        assert mock_get.call_args.args[0] == f"{OWN_TAIGA_API_URL}/milestones/m1/stats"
        assert mock_get.call_args.kwargs["params"] == {"project": "p1"}
        assert mock_get.call_args.kwargs["headers"] == {
            "Authorization": "Application app:token:hash"
        }
        mock_login.assert_not_called()

    def test_fallback_server_logs_in_with_fallback_credentials(self, mock_get, mock_login):
        from datasources.requests.taiga_api_call import milestone_stats

        mock_get.return_value = _response(STATS)

        milestone_stats("p1", "m1", FALLBACK_TEAM)

        assert mock_login.call_args.args[0] == FALLBACK_TAIGA_AUTH_URL
        assert mock_login.call_args.kwargs["json"] == {
            "type": "normal",
            "username": "fallback_user",
            "password": "fallback_pass",
        }
        assert mock_get.call_args.args[0] == f"{FALLBACK_TAIGA_API_URL}/milestones/m1/stats"
        assert mock_get.call_args.kwargs["headers"] == {"Authorization": "Bearer login_tok"}

    def test_same_ids_on_two_servers_do_not_share_cache(self, mock_get, mock_login):
        """Ids are only unique within one Taiga server."""
        from datasources.requests.taiga_api_call import milestone_stats

        other_stats = {**STATS, "total_userstories": 99}
        mock_get.side_effect = [_response(STATS), _response(other_stats)]

        own = milestone_stats("p1", "m1", OWN_SERVER_TEAM)
        fallback = milestone_stats("p1", "m1", FALLBACK_TEAM)

        assert own["milestone_total_userstories"] == 4
        assert fallback["milestone_total_userstories"] == 99
        assert [c.args[0] for c in mock_get.call_args_list] == [
            f"{OWN_TAIGA_API_URL}/milestones/m1/stats",
            f"{FALLBACK_TAIGA_API_URL}/milestones/m1/stats",
        ]
        # Both entries stay cached independently
        assert milestone_stats("p1", "m1", OWN_SERVER_TEAM) == own
        assert milestone_stats("p1", "m1", FALLBACK_TEAM) == fallback
        assert mock_get.call_count == 2

    def test_teams_of_one_subject_share_cache(self, mock_get):
        from datasources.requests.taiga_api_call import milestone_stats

        mock_get.return_value = _response(STATS)

        milestone_stats("p1", "m1", "TeamAlpha")
        milestone_stats("p1", "m1", "TeamBeta")
        assert mock_get.call_count == 1

    def test_http_error_returns_zeros(self, mock_get):
        from datasources.requests.taiga_api_call import milestone_stats

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "Forbidden"
        )
        mock_get.return_value = mock_resp

        result = milestone_stats("p1", "m1", OWN_SERVER_TEAM)
        assert result["milestone_total_points"] == 0
        assert result["milestone_closed_points"] == 0

    def test_login_timeout_returns_zeros(self, mock_get, mock_login):
        from datasources.requests.taiga_api_call import milestone_stats

        mock_login.side_effect = requests.exceptions.ReadTimeout("timeout")

        result = milestone_stats("p1", "m1", FALLBACK_TEAM)
        assert result["milestone_total_points"] == 0
        assert result["milestone_closed_points"] == 0
        assert result["milestone_total_userstories"] == 0
        # No anonymous request when the login fails
        mock_get.assert_not_called()

    def test_stats_timeout_returns_zeros(self, mock_get):
        from datasources.requests.taiga_api_call import milestone_stats

        mock_get.side_effect = requests.exceptions.ReadTimeout("timeout")

        result = milestone_stats("p1", "m1", OWN_SERVER_TEAM)
        assert result["milestone_total_points"] == 0
        assert result["milestone_closed_points"] == 0
        assert result["milestone_total_userstories"] == 0

    def test_unknown_team_returns_zeros_without_request(self, mock_get, mock_login):
        from datasources.requests.taiga_api_call import milestone_stats

        result = milestone_stats("p1", "m1", "UnknownTeam")
        assert result["milestone_total_points"] == 0
        assert result["milestone_total_tasks"] == 0
        mock_get.assert_not_called()
        mock_login.assert_not_called()

    def test_broken_subject_returns_zeros_without_request(
        self, mock_get, mock_login, monkeypatch
    ):
        from datasources.requests.taiga_api_call import milestone_stats

        monkeypatch.setattr("config.settings.TAIGA_FALLBACK_API_URL", "")

        result = milestone_stats("p1", "m1", FALLBACK_TEAM)
        assert result["milestone_total_points"] == 0
        mock_get.assert_not_called()
        mock_login.assert_not_called()


@pytest.mark.usefixtures("sample_credentials_config")
class TestDetails:
    def test_milestone_details(self, mock_get):
        from datasources.requests.taiga_api_call import milestone_details

        mock_get.return_value = _response(
            {
                "created_date": "2025-05-01T00:00:00Z",
                "modified_date": "2025-06-01T00:00:00Z",
                "name": "Sprint 1",
                "estimated_start": "2025-05-01",
                "estimated_finish": "2025-06-01",
                "closed": True,
            }
        )

        details = milestone_details("p1", "m1", OWN_SERVER_TEAM)

        assert details["milestone_name"] == "Sprint 1"
        assert details["milestone_closed"] is True
        assert mock_get.call_args.args[0] == f"{OWN_TAIGA_API_URL}/milestones/m1"

    def test_milestone_details_not_shared_between_servers(self, mock_get, mock_login):
        from datasources.requests.taiga_api_call import milestone_details

        mock_get.side_effect = [_response({"name": "Own"}), _response({"name": "Fallback"})]

        assert milestone_details("p1", "m1", OWN_SERVER_TEAM)["milestone_name"] == "Own"
        assert milestone_details("p1", "m1", FALLBACK_TEAM)["milestone_name"] == "Fallback"

    def test_userstory_details_not_shared_between_servers(self, mock_get, mock_login):
        from datasources.requests.taiga_api_call import userstory_details

        mock_get.side_effect = [
            _response(
                {
                    "status_extra_info": {"is_closed": True},
                    "custom_attributes_values": {"Priority": "High"},
                    "description": "own",
                }
            ),
            _response(
                {
                    "status_extra_info": {"is_closed": False},
                    "custom_attributes_values": {"Priority": "Low"},
                    "description": "fallback",
                }
            ),
        ]

        own = userstory_details("p1", "us1", OWN_SERVER_TEAM)
        fallback = userstory_details("p1", "us1", FALLBACK_TEAM)

        assert own["description"] == "own"
        assert own["userstory_is_closed"] is True
        assert fallback["description"] == "fallback"
        assert fallback["userstory_is_closed"] is False
        assert [c.args[0] for c in mock_get.call_args_list] == [
            f"{OWN_TAIGA_API_URL}/userstories/us1",
            f"{FALLBACK_TAIGA_API_URL}/userstories/us1",
        ]

    def test_task_custom_values_resolved_on_the_subject_server(self, mock_get):
        from datasources.requests.taiga_api_call import task_details

        mock_get.side_effect = [
            _response({"custom_attributes_values": {}}),
            _response({"attributes_values": {"7": "5"}}),
            _response([{"id": 7, "name": "Estimated effort"}]),
        ]

        details = task_details("p1", "t1", OWN_SERVER_TEAM)

        assert details == {"custom_attributes_values": {"Estimated effort": "5"}}
        assert [c.args[0] for c in mock_get.call_args_list] == [
            f"{OWN_TAIGA_API_URL}/tasks/t1",
            f"{OWN_TAIGA_API_URL}/tasks/custom-attributes-values/t1",
            f"{OWN_TAIGA_API_URL}/task-custom-attributes",
        ]

    @pytest.mark.parametrize(
        "function_name", ["milestone_details", "userstory_details", "task_details"]
    )
    def test_unknown_team_returns_empty_without_request(self, mock_get, function_name):
        import datasources.requests.taiga_api_call as mod

        assert getattr(mod, function_name)("p1", "x1", "UnknownTeam") == {}
        mock_get.assert_not_called()
