"""Tests for utils/recovery/taiga_recovery.py"""

import pytest
from unittest.mock import patch, MagicMock


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

        pid = get_project_id_by_slug("my-slug")
        assert pid == 42

    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_private_project_exits(self, mock_get):
        from utils.recovery.taiga_recovery import get_project_id_by_slug

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        with pytest.raises(SystemExit, match="private"):
            get_project_id_by_slug("private-slug")

    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_not_found_exits(self, mock_get):
        from utils.recovery.taiga_recovery import get_project_id_by_slug

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        with pytest.raises(SystemExit, match="not found"):
            get_project_id_by_slug("non-existent")

    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_other_error_raises(self, mock_get):
        import requests
        from utils.recovery.taiga_recovery import get_project_id_by_slug

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_get.return_value = mock_resp

        with pytest.raises(requests.HTTPError):
            get_project_id_by_slug("err-slug")


class TestGetUsernameId:
    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_returns_id(self, mock_get):
        from utils.recovery.taiga_recovery import get_username_id

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 123}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        uid = get_username_id("tok")
        assert uid == 123


class TestGetProjectIdByUsernameId:
    @patch("utils.recovery.taiga_recovery.get_username_id", return_value=1)
    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_project_found(self, mock_get, mock_uid):
        from utils.recovery.taiga_recovery import get_project_id_by_username_id

        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"name": "Other Project", "id": 10},
            {"name": "My Project", "id": 42},
        ]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        pid = get_project_id_by_username_id("My Project", "tok")
        assert pid == 42

    @patch("utils.recovery.taiga_recovery.get_username_id", return_value=1)
    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_project_not_found_exits(self, mock_get, mock_uid):
        from utils.recovery.taiga_recovery import get_project_id_by_username_id

        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with pytest.raises(SystemExit):
            get_project_id_by_username_id("Nonexistent", "tok")


class TestFetchEntities:
    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_fetch_tasks(self, mock_get):
        from utils.recovery.taiga_recovery import fetch_entities

        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": 1}, {"id": 2}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_entities("task", 42)
        assert len(result) == 2

    def test_unsupported_entity_raises(self):
        from utils.recovery.taiga_recovery import fetch_entities

        with pytest.raises(ValueError, match="Not supported"):
            fetch_entities("wiki", 42)

    @patch("utils.recovery.taiga_recovery.requests.get")
    def test_fetch_with_date_filters(self, mock_get):
        from utils.recovery.taiga_recovery import fetch_entities, parse_dt

        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        start = parse_dt("2025-01-01")
        end = parse_dt("2025-12-31")
        fetch_entities("task", 42, start, end)

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


class TestMain:
    @patch("utils.recovery.taiga_recovery.notify_eval_push")
    @patch("utils.recovery.taiga_recovery.upsert", return_value=5)
    @patch("utils.recovery.taiga_recovery.get_collection")
    @patch("utils.recovery.taiga_recovery.fetch_entities", return_value=[])
    @patch("utils.recovery.taiga_recovery.get_project_id_by_slug", return_value=42)
    def test_main_runs(
        self, mock_slug, mock_fetch, mock_coll, mock_upsert, mock_notify
    ):
        from utils.recovery.taiga_recovery import main

        main(["--slug", "test-slug", "--prj", "TestPrj", "--events", "task"])
        mock_slug.assert_called_once_with("test-slug")
        mock_fetch.assert_called_once()

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
                "P",
                "--from-date",
                "2025-01-01",
                "--to-date",
                "2025-12-31",
            ]
        )
        mock_fetch.assert_called()
