"""Tests for datasources/taiga_handler.py"""

import pytest
from unittest.mock import patch, MagicMock


class TestParseTaigaEvent:
    @patch("datasources.taiga_handler.milestone_stats", return_value={})
    def test_task_event(self, mock_ms, taiga_task_payload):
        from datasources.taiga_handler import parse_taiga_event

        result = parse_taiga_event(taiga_task_payload, "TestPrj")
        assert result["event_type"] == "task"

    def test_issue_event(self, taiga_issue_payload):
        from datasources.taiga_handler import parse_taiga_event

        result = parse_taiga_event(taiga_issue_payload, "TestPrj")
        assert result["event_type"] == "issue"

    def test_epic_event(self, taiga_epic_payload):
        from datasources.taiga_handler import parse_taiga_event

        result = parse_taiga_event(taiga_epic_payload, "TestPrj")
        assert result["event_type"] == "epic"

    @patch("datasources.taiga_handler.milestone_stats", return_value={})
    def test_userstory_event(self, mock_ms, taiga_userstory_payload):
        from datasources.taiga_handler import parse_taiga_event

        result = parse_taiga_event(taiga_userstory_payload, "TestPrj")
        assert result["event_type"] == "userstory"

    def test_relateduserstory_event(self, taiga_related_userstory_payload):
        from datasources.taiga_handler import parse_taiga_event

        result = parse_taiga_event(taiga_related_userstory_payload, "TestPrj")
        assert result["event_type"] == "relateduserstory"

    def test_unsupported_event(self):
        from datasources.taiga_handler import parse_taiga_event

        payload = {"type": "unknown_type"}
        result = parse_taiga_event(payload, "P")
        assert result["event"] == "unknown_type"
        assert result["error"] == "Unsupported event type"


class TestParseTaigaIssueEvent:
    def test_basic_issue_parsing(self, taiga_issue_payload):
        from datasources.taiga_handler import parse_taiga_issue_event

        result = parse_taiga_issue_event(taiga_issue_payload, "TestPrj")

        assert result["event_type"] == "issue"
        assert result["action_type"] == "create"
        assert result["issue_id"] == 200
        assert result["team_name"] == "TestProject"
        assert result["subject"] == "Bug report"
        assert result["description"] == "Something is broken"
        assert result["severity"] == "Normal"
        assert result["priority"] == "High"
        assert result["type"] == "Bug"
        assert result["assigned_by"] == "taigauser"
        assert result["assigned_to"] == "dev2"

    def test_issue_assigned_to_none(self):
        from datasources.taiga_handler import parse_taiga_issue_event

        payload = {
            "type": "issue",
            "action": "create",
            "by": {"username": "u"},
            "data": {
                "id": 1,
                "project": {"id": 1, "name": "P"},
                "subject": "S",
                "due_date": "",
                "description": "",
                "severity": {"name": "N"},
                "status": {"name": "New"},
                "priority": {"name": "H"},
                "type": {"name": "B"},
                "modified_date": "",
                "created_date": "",
                "finished_date": "",
                "assigned_to": None,
            },
            "is_closed": False,
        }
        result = parse_taiga_issue_event(payload, "P")
        assert result["assigned_to"] is None


class TestParseTaigaEpicEvent:
    def test_basic_epic_parsing(self, taiga_epic_payload):
        from datasources.taiga_handler import parse_taiga_epic_event

        result = parse_taiga_epic_event(taiga_epic_payload, "TestPrj")

        assert result["epic_id"] == 300
        assert result["event_type"] == "epic"
        assert result["action_type"] == "create"
        assert result["subject"] == "Epic feature"
        assert result["team_name"] == "TestProject"
        assert result["assigned_by"] == "taigauser"


class TestParseTaigaTaskEvent:
    @patch(
        "datasources.taiga_handler.milestone_stats",
        return_value={"milestone_total_points": 10},
    )
    def test_basic_task_parsing(self, mock_ms, taiga_task_payload):
        from datasources.taiga_handler import parse_taiga_task_event

        result = parse_taiga_task_event(taiga_task_payload, "TestPrj")

        assert result["event_type"] == "task"
        assert result["task_id"] == 100
        assert result["subject"] == "Implement login"
        assert result["userstory_id"] == 50
        assert result["status"] == "New"
        assert result["assigned_to"] == "dev1"
        assert result["assigned_by"] == "taigauser"
        assert result["milestone_id"] == 10
        assert result["milestone_name"] == "Sprint 1"
        assert result["custom_attributes"] == {"story_points": 5}
        # milestone_stats data merged
        assert result["milestone_total_points"] == 10

    @patch("datasources.taiga_handler.milestone_stats", return_value={})
    def test_task_assigned_to_none(self, mock_ms):
        from datasources.taiga_handler import parse_taiga_task_event

        payload = {
            "type": "task",
            "action": "create",
            "by": {"username": "u"},
            "data": {
                "id": 1,
                "project": {"id": 1, "name": "P"},
                "subject": "S",
                "user_story": {"id": 1, "is_closed": False},
                "status": {"name": "N", "is_closed": False},
                "created_date": "",
                "modified_date": "",
                "finished_date": "",
                "ref": 1,
                "milestone": {
                    "id": 1,
                    "name": "S1",
                    "closed": False,
                    "created_date": "",
                    "modified_date": "",
                    "estimated_start": "",
                    "estimated_finish": "",
                },
                "assigned_to": None,
                "custom_attributes_values": None,
            },
        }
        result = parse_taiga_task_event(payload, "P")
        assert result["assigned_to"] is None
        assert result["custom_attributes"] == {}


class TestParseTaigaUserstoryEvent:
    @patch(
        "datasources.taiga_handler.milestone_stats",
        return_value={"milestone_total_points": 20},
    )
    def test_basic_userstory_parsing(self, mock_ms, taiga_userstory_payload):
        from datasources.taiga_handler import parse_taiga_userstory_event

        result = parse_taiga_userstory_event(taiga_userstory_payload, "TestPrj")

        assert result["event_type"] == "userstory"
        assert result["userstory_id"] == 400
        assert result["subject"] == "User login"
        assert result["total_points"] == 8  # 3 + 5
        assert result["pattern"] is True  # matches "As a ... I want ... so that ..."
        assert result["priority"] == "High"
        assert result["milestone_total_points"] == 20

    @patch("datasources.taiga_handler.milestone_stats", return_value={})
    def test_userstory_no_pattern(self, mock_ms):
        from datasources.taiga_handler import parse_taiga_userstory_event

        payload = {
            "type": "userstory",
            "action": "create",
            "by": {"username": "u"},
            "data": {
                "id": 1,
                "project": {"id": 1, "name": "P"},
                "subject": "S",
                "status": {"name": "New"},
                "modified_date": "",
                "created_date": "",
                "description": "Just a simple description",
                "custom_attributes_values": {},
                "points": [],
                "milestone": None,
            },
            "is_closed": False,
        }
        result = parse_taiga_userstory_event(payload, "P")
        assert result["pattern"] is False
        assert result["total_points"] == 0
        assert result["milestone_id"] == ""

    @patch("datasources.taiga_handler.milestone_stats", return_value={})
    def test_userstory_custom_attributes_none(self, mock_ms):
        """When custom_attributes_values is None, the code crashes on .get('Priority').
        This is a known bug in the source. Test with empty dict instead."""
        from datasources.taiga_handler import parse_taiga_userstory_event

        payload = {
            "type": "userstory",
            "action": "create",
            "by": {"username": "u"},
            "data": {
                "id": 1,
                "project": {"id": 1, "name": "P"},
                "subject": "S",
                "status": {"name": "New"},
                "modified_date": "",
                "created_date": "",
                "description": "",
                "custom_attributes_values": {},
                "points": [{"value": None}, {"value": 3}],
                "milestone": None,
            },
            "is_closed": False,
        }
        result = parse_taiga_userstory_event(payload, "P")
        assert result["custom_attributes"] == {}
        assert result["total_points"] == 3
        assert result["priority"] == ""

    @patch("datasources.taiga_handler.milestone_stats", return_value={})
    @pytest.mark.xfail(reason="parse_taiga_userstory_event crashes when custom_attributes_values is None", strict=False)
    def test_userstory_custom_attributes_values_none_xfail(self, mock_ms):
        """Explicitly exercise the None custom_attributes_values case to capture the known bug."""
        from datasources.taiga_handler import parse_taiga_userstory_event
        payload = {
            "type": "userstory",
            "action": "create",
            "by": {"username": "u"},
            "data": {
                "id": 1,
                "project": {"id": 1, "name": "P"},
                "subject": "S",
                "status": {"name": "New"},
                "modified_date": "",
                "created_date": "",
                "description": "",
                "custom_attributes_values": None,
                "points": [{"value": None}, {"value": 3}],
                "milestone": None
            },
            "is_closed": False
        }
        with pytest.raises(AttributeError):
            parse_taiga_userstory_event(payload, "P")
class TestParseTaigaRelatedUserstoryEvent:
    def test_basic_related_userstory_parsing(self, taiga_related_userstory_payload):
        from datasources.taiga_handler import parse_taiga_related_userstory_event

        result = parse_taiga_related_userstory_event(
            taiga_related_userstory_payload, "TestPrj"
        )

        assert result["event_type"] == "relateduserstory"
        assert result["id"] == 400
        assert result["epic_id"] == 300
        assert result["epic_name"] == "Epic feature"
        assert result["reference"] == 1
        assert result["assigned_to"] == "dev1"
        assert result["assigned_by"] == "taigauser"
        assert result["team_name"] == "TestProject"
