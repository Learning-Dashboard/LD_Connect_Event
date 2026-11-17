"""Tests for utils/recovery/taiga_recovery.py"""

import pytest
from unittest.mock import patch, MagicMock

from config.credentials_loader import (
    ProjectCredentialsNotFoundError,
    TaigaContext,
    get_taiga_context,
)

API_URL = "https://taiga.example/api/v1"
CTX = TaigaContext(api_url=API_URL, auth_url=f"{API_URL}/auth", token="app:hash")
AUTH_HEADER = {"Authorization": "Application app:hash"}


class TestParseDt:
    def test_date_only(self):
        from utils.recovery.taiga_recovery import parse_dt

        result = parse_dt("2025-06-15")
        assert result.year == 2025
        assert result.month == 6
        assert result.tzinfo is not None

    def test_datetime_with_time(self):
        from utils.recovery.taiga_recovery import parse_dt

        result = parse_dt("2025-06-15T14:30")
        assert result.hour == 14
        assert result.minute == 30


class TestGetProjectIdBySlug:
    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_success(self, mock_get):
        from utils.recovery.taiga_recovery import get_project_id_by_slug

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 42}
        mock_get.return_value = mock_resp

        pid = get_project_id_by_slug("my-slug", CTX)
        assert pid == 42
        # The slug is resolved on the Taiga server of the subject
        assert mock_get.call_args.args[0] == f"{API_URL}/projects/by_slug"
        assert mock_get.call_args.kwargs["params"] == {"slug": "my-slug"}
        assert mock_get.call_args.kwargs["headers"] == AUTH_HEADER

    @pytest.mark.parametrize("status_code", [401, 403])
    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_inaccessible_project_exits(self, mock_get, status_code):
        from utils.recovery.taiga_recovery import get_project_id_by_slug

        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_get.return_value = mock_resp

        with pytest.raises(SystemExit, match="not accessible"):
            get_project_id_by_slug("private-slug", CTX)

    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_not_found_exits(self, mock_get):
        from utils.recovery.taiga_recovery import get_project_id_by_slug

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        with pytest.raises(SystemExit, match="not found"):
            get_project_id_by_slug("non-existent", CTX)

    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_other_error_raises(self, mock_get):
        import requests
        from utils.recovery.taiga_recovery import get_project_id_by_slug

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_get.return_value = mock_resp

        with pytest.raises(requests.HTTPError):
            get_project_id_by_slug("err-slug", CTX)

    @patch("utils.taiga_token.taiga_auth.requests.post")
    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_login_failure_raises_without_anonymous_request(self, mock_get, mock_post):
        import requests
        import utils.taiga_token.taiga_auth as auth_mod
        from utils.recovery.taiga_recovery import get_project_id_by_slug

        auth_mod._TOKENS.clear()
        mock_post.side_effect = requests.ConnectionError("unreachable")
        login_ctx = TaigaContext(
            api_url=API_URL, auth_url=f"{API_URL}/auth", username="u", password="p"
        )

        with pytest.raises(requests.ConnectionError):
            get_project_id_by_slug("my-slug", login_ctx)
        mock_get.assert_not_called()


class TestFetchEntities:
    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_fetch_tasks(self, mock_get):
        from utils.recovery.taiga_recovery import fetch_entities

        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": 1}, {"id": 2}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_entities("task", 42, CTX)
        assert len(result) == 2
        assert mock_get.call_args.args[0] == f"{API_URL}/tasks"
        assert mock_get.call_args.kwargs["params"] == {"project": 42}
        assert mock_get.call_args.kwargs["headers"] == {
            "x-disable-pagination": "True",
            **AUTH_HEADER,
        }

    def test_unsupported_entity_raises(self):
        from utils.recovery.taiga_recovery import fetch_entities

        with pytest.raises(ValueError, match="Not supported"):
            fetch_entities("wiki", 42, CTX)

    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_fetch_with_date_filters(self, mock_get):
        from utils.recovery.taiga_recovery import fetch_entities, parse_dt

        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        start = parse_dt("2025-01-01")
        end = parse_dt("2025-12-31")
        fetch_entities("task", 42, CTX, start, end)

        call_params = mock_get.call_args[1]["params"]
        assert "modified_date__gte" in call_params
        assert "modified_date__lte" in call_params


class TestUpsert:
    def test_empty(self):
        from utils.recovery.taiga_recovery import upsert

        result = upsert(MagicMock(), [], "id")
        assert result == 0

    def test_with_docs(self):
        from utils.recovery.taiga_recovery import upsert

        mock_coll = MagicMock()
        mock_result = MagicMock()
        mock_result.matched_count = 2
        mock_result.upserted_ids = {0: "a"}
        mock_coll.bulk_write.return_value = mock_result

        result = upsert(mock_coll, [{"id": 1}], "id")
        assert result == 3


class TestConverters:
    def test_task_from_api(self):
        from utils.recovery.taiga_recovery import task_from_api

        j = {
            "id": 100,
            "subject": "Task A",
            "created_date": "2025-06-01",
            "modified_date": "2025-06-10",
            "finished_date": None,
            "ref": 42,
            "milestone": None,
            "milestone_extra_info": None,
            "user_story": 50,
            "user_story_extra_info": {"is_closed": False},
            "status_extra_info": {"is_closed": False, "name": "New"},
            "assigned_to_extra_info": {"username": "dev1"},
            "custom_attributes_values": {"sp": 5},
            "project_extra_info": {"name": "TestProject", "id": 1},
        }
        doc = task_from_api(j, "TestPrj")
        assert doc["task_id"] == 100
        assert doc["subject"] == "Task A"
        assert doc["prj"] == "TestPrj"
        assert doc["status"] == "New"
        assert doc["assigned_to"] == "dev1"

    def test_issue_from_api(self):
        from utils.recovery.taiga_recovery import issue_from_api

        j = {
            "id": 200,
            "subject": "Bug",
            "description": "desc",
            "due_date": None,
            "created_date": "2025-06-01",
            "modified_date": "2025-06-10",
            "finished_date": None,
            "status_extra_info": {"is_closed": False, "name": "New"},
            "priority_extra_info": {"name": "High"},
            "severity_extra_info": {"name": "Normal"},
            "type_extra_info": {"name": "Bug"},
            "assigned_to_extra_info": None,
            "project_extra_info": {"name": "TestProject"},
        }
        doc = issue_from_api(j, "TestPrj")
        assert doc["issue_id"] == 200
        assert doc["assigned_to"] is None
        assert doc["status"] == "New"

    def test_epic_from_api(self):
        from utils.recovery.taiga_recovery import epic_from_api

        j = {
            "id": 300,
            "subject": "Epic",
            "created_date": "2025-06-01",
            "modified_date": "2025-06-10",
            "status_extra_info": {"is_closed": False, "name": "New"},
            "project_extra_info": {"name": "TestProject", "id": 1},
        }
        doc = epic_from_api(j, "TestPrj")
        assert doc["epic_id"] == 300
        assert doc["project_id"] == 1

    def test_userstory_from_api(self):
        from utils.recovery.taiga_recovery import userstory_from_api

        j = {
            "id": 400,
            "subject": "User login",
            "description": "As a user I want to login so that I can access the app",
            "created_date": "2025-06-01",
            "modified_date": "2025-06-10",
            "status_extra_info": {"is_closed": False, "name": "New"},
            "milestone": 10,
            "milestone_extra_info": {
                "name": "Sprint 1",
                "closed": False,
                "created_date": "2025-05-01",
                "modified_date": "2025-06-01",
                "estimated_start": "2025-05-01",
                "estimated_finish": "2025-06-01",
            },
            "custom_attributes_values": {"Priority": "High"},
            "points": [{"value": 3}, {"value": 5}],
            "project_extra_info": {"name": "TestProject"},
        }
        doc = userstory_from_api(j, "TestPrj")
        assert doc["userstory_id"] == 400
        assert doc["pattern"] is True
        assert doc["total_points"] == 8
        assert doc["priority"] == "High"

    def test_userstory_no_pattern(self):
        from utils.recovery.taiga_recovery import userstory_from_api

        j = {
            "id": 401,
            "subject": "S",
            "description": "just a description",
            "created_date": "2025-06-01",
            "modified_date": "2025-06-10",
            "status_extra_info": {"is_closed": False, "name": "New"},
            "milestone": None,
            "milestone_extra_info": None,
            "custom_attributes_values": None,
            "points": "",
            "project_extra_info": {"name": "P"},
        }
        doc = userstory_from_api(j, "P")
        assert doc["pattern"] is False
        assert doc["total_points"] == 0
        assert doc["custom_attributes"] == {}


class TestSyncDeletedEntities:
    @patch("utils.recovery.taiga_recovery.get_collection")
    def test_no_deletions_when_all_present(self, mock_get_coll):
        from utils.recovery.taiga_recovery import sync_deleted_entities

        mock_coll = MagicMock()
        mock_coll.find.return_value = [{"userstory_id": 1}, {"userstory_id": 2}]
        mock_get_coll.return_value = mock_coll

        raw_api = [{"id": 1}, {"id": 2}]
        deleted = sync_deleted_entities("userstory", "TestPrj", 42, CTX, raw_api=raw_api)
        assert deleted == 0
        mock_coll.delete_many.assert_not_called()

    @patch("utils.recovery.taiga_recovery.get_collection")
    def test_deletes_orphaned_userstory(self, mock_get_coll):
        from utils.recovery.taiga_recovery import sync_deleted_entities

        us_coll = MagicMock()
        us_coll.find.return_value = [{"userstory_id": 1}, {"userstory_id": 99}]
        delete_result = MagicMock()
        delete_result.deleted_count = 1
        us_coll.delete_many.return_value = delete_result

        tasks_coll = MagicMock()
        task_delete_result = MagicMock()
        task_delete_result.deleted_count = 2
        tasks_coll.delete_many.return_value = task_delete_result

        mock_get_coll.side_effect = [us_coll, tasks_coll]

        raw_api = [{"id": 1}]
        deleted = sync_deleted_entities("userstory", "TestPrj", 42, CTX, raw_api=raw_api)

        assert deleted == 1
        us_coll.delete_many.assert_called_once_with({"userstory_id": {"$in": [99]}})
        tasks_coll.delete_many.assert_called_once_with({"userstory_id": {"$in": [99]}})

    @patch("utils.recovery.taiga_recovery.get_collection")
    def test_task_deletion_does_not_cascade(self, mock_get_coll):
        from utils.recovery.taiga_recovery import sync_deleted_entities

        task_coll = MagicMock()
        task_coll.find.return_value = [{"task_id": 10}, {"task_id": 99}]
        delete_result = MagicMock()
        delete_result.deleted_count = 1
        task_coll.delete_many.return_value = delete_result

        mock_get_coll.return_value = task_coll

        raw_api = [{"id": 10}]
        deleted = sync_deleted_entities("task", "TestPrj", 42, CTX, raw_api=raw_api)

        assert deleted == 1
        # Only one delete_many call — no cascade to another collection
        assert mock_get_coll.call_count == 1

    @patch("utils.recovery.taiga_recovery.get_collection")
    def test_unsupported_event_returns_zero(self, mock_get_coll):
        from utils.recovery.taiga_recovery import sync_deleted_entities

        deleted = sync_deleted_entities("wiki", "TestPrj", 42, CTX, raw_api=[])
        assert deleted == 0
        mock_get_coll.assert_not_called()

    @patch("utils.recovery.taiga_recovery.fetch_entities", return_value=[{"id": 1}])
    @patch("utils.recovery.taiga_recovery.get_collection")
    def test_fetches_from_the_subject_server_when_raw_api_is_missing(
        self, mock_get_coll, mock_fetch
    ):
        from utils.recovery.taiga_recovery import sync_deleted_entities

        mock_coll = MagicMock()
        mock_coll.find.return_value = [{"task_id": 1}]
        mock_get_coll.return_value = mock_coll

        assert sync_deleted_entities("task", "TestPrj", 42, CTX) == 0
        mock_fetch.assert_called_once_with("task", 42, CTX, None, None)


@pytest.mark.usefixtures("sample_credentials_config")
class TestMain:
    @patch("utils.recovery.taiga_recovery.notify_eval_push")
    @patch("utils.recovery.taiga_recovery.upsert", return_value=5)
    @patch("utils.recovery.taiga_recovery.get_collection")
    @patch("utils.recovery.taiga_recovery.fetch_entities", return_value=[])
    @patch("utils.recovery.taiga_recovery.get_project_id_by_slug", return_value=42)
    def test_main_runs(self, mock_slug, mock_fetch, mock_coll, mock_upsert, mock_notify):
        from utils.recovery.taiga_recovery import main

        main(["--slug", "test-slug", "--prj", "TeamAlpha", "--events", "task"])

        ctx = get_taiga_context("TeamAlpha")
        mock_slug.assert_called_once_with("test-slug", ctx)
        mock_fetch.assert_called_once_with("task", 42, ctx, None, None)

    @pytest.mark.parametrize("team", ["TeamAlpha", "TeamGamma"])
    @patch("utils.recovery.taiga_recovery.notify_eval_push")
    @patch("utils.recovery.taiga_recovery.upsert", return_value=5)
    @patch("utils.recovery.taiga_recovery.get_collection")
    @patch("utils.recovery.taiga_recovery.fetch_entities", return_value=[])
    @patch("utils.recovery.taiga_recovery.get_project_id_by_slug", return_value=42)
    def test_main_uses_the_taiga_server_of_the_team_subject(
        self, mock_slug, mock_fetch, mock_coll, mock_upsert, mock_notify, team
    ):
        from utils.recovery.taiga_recovery import main

        main(["--slug", "test-slug", "--prj", team, "--events", "task,epic"])

        ctx = get_taiga_context(team)
        assert mock_slug.call_args.args == ("test-slug", ctx)
        assert [c.args[2] for c in mock_fetch.call_args_list] == [ctx, ctx]

    @patch("utils.recovery.taiga_recovery.fetch_entities")
    @patch("utils.recovery.taiga_recovery.get_project_id_by_slug")
    def test_main_unknown_team_fails_before_any_request(self, mock_slug, mock_fetch):
        from utils.recovery.taiga_recovery import main

        with pytest.raises(ProjectCredentialsNotFoundError):
            main(["--slug", "test-slug", "--prj", "UnknownTeam", "--events", "task"])
        mock_slug.assert_not_called()
        mock_fetch.assert_not_called()

    def test_main_rejects_removed_token_option(self):
        from utils.recovery.taiga_recovery import main

        with pytest.raises(SystemExit):
            main(["--slug", "s", "--prj", "TeamAlpha", "--taiga-token", "tok"])

    @patch("utils.recovery.taiga_recovery.notify_eval_push")
    @patch("utils.recovery.taiga_recovery.upsert", return_value=2)
    @patch("utils.recovery.taiga_recovery.get_collection")
    @patch("utils.recovery.taiga_recovery.fetch_entities", return_value=[])
    @patch("utils.recovery.taiga_recovery.get_project_id_by_slug", return_value=42)
    def test_main_with_dates(
        self, mock_slug, mock_fetch, mock_coll, mock_upsert, mock_notify
    ):
        from utils.recovery.taiga_recovery import main

        main(
            [
                "--slug",
                "s",
                "--prj",
                "TeamGamma",
                "--from-date",
                "2025-01-01",
                "--to-date",
                "2025-12-31",
            ]
        )
        mock_fetch.assert_called()
        assert all(c.args[3] is not None and c.args[4] is not None for c in mock_fetch.call_args_list)
