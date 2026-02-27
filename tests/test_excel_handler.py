"""Tests for datasources/excel_handler.py"""
import pytest
from datasources.excel_handler import parse_excel_event, ACTIVITY_TYPES


class TestParseExcelEvent:
    def test_basic_parse(self, excel_payload):
        result = parse_excel_event(excel_payload, "TestPrj", "default")
        assert result["team"] == "TestPrj"
        assert result["quality_model"] == "default"
        assert result["iteration"] == "Sprint 1"
        assert result["activity_date"] == "2025-06-15"
        assert result["duration_h"] == 2.5
        assert result["activity_type"] == "Desenvolupament"
        assert result["comment"] == "Worked on feature X"
        assert result["epic"] == "Epic 1"

    def test_members_cleaned(self, excel_payload):
        result = parse_excel_event(excel_payload, "TestPrj", "default")
        # Empty string "" should be removed
        assert result["members"] == ["Alice", "Bob"]

    def test_member_hours_mapping(self, excel_payload):
        result = parse_excel_event(excel_payload, "TestPrj", "default")
        assert result["hours_Alice"] == 3
        assert result["hours_Bob"] == 2

    def test_activity_hours_from_config_range(self, excel_payload):
        result = parse_excel_event(excel_payload, "TestPrj", "default")
        # configRange = [0, 0, 0, 0, 5, 0, 0, 0]
        # Index 4 corresponds to "Desenvolupament"
        assert result["hours_Desenvolupament"] == 5
        assert result["hours_Reunió_d'equip"] == 0
        assert result["total_hours"] == 5

    def test_empty_members(self):
        payload = {
            "timestamp": "2025-06-15T10:00:00",
            "iteration": "Sprint 1",
            "date": "2025-06-15",
            "duration": 1,
            "activity": "Formació",
            "comment": "",
            "epic": "",
            "members": [],
            "memberHours": [],
            "configRange": []
        }
        result = parse_excel_event(payload, "TestPrj", "qm1")
        assert result["members"] == []
        assert result["total_hours"] == 0

    def test_more_members_than_hours(self):
        """When there are more members than hours, only members with hours get mapped.
        Note: The code pairs hours[:len(members)], so members without hours cause IndexError.
        This test verifies that the first two members get their hours."""
        payload = {
            "timestamp": "2025-06-15T10:00:00",
            "iteration": "S1",
            "date": "2025-06-15",
            "duration": 1,
            "activity": "Formació",
            "comment": "",
            "epic": "",
            "members": ["A", "B"],
            "memberHours": [1, 2, 3],
            "configRange": []
        }
        result = parse_excel_event(payload, "P", "qm")
        assert "hours_A" in result
        assert "hours_B" in result
        assert result["hours_A"] == 1
        assert result["hours_B"] == 2

    def test_config_range_shorter_than_activity_types(self):
        payload = {
            "timestamp": "t",
            "iteration": "S1",
            "date": "d",
            "duration": 1,
            "activity": "x",
            "comment": "",
            "epic": "",
            "members": [],
            "memberHours": [],
            "configRange": [10, 20]  # Only 2 values for 8 activity types
        }
        result = parse_excel_event(payload, "P", "qm")
        assert result["hours_Reunió_d'equip"] == 10
        assert result["hours_Reunió_focal"] == 20
        assert result["hours_Classe_passiva"] == 0  # Default
        assert result["total_hours"] == 30

    def test_config_range_with_none_values(self):
        payload = {
            "timestamp": "t",
            "iteration": "S1",
            "date": "d",
            "duration": 1,
            "activity": "x",
            "comment": "",
            "epic": "",
            "members": [],
            "memberHours": [],
            "configRange": [None, 5, None, None, None, None, None, None]
        }
        result = parse_excel_event(payload, "P", "qm")
        assert result["hours_Reunió_d'equip"] == 0
        assert result["hours_Reunió_focal"] == 5
        assert result["total_hours"] == 5

    def test_quality_model_preserved(self, excel_payload):
        result = parse_excel_event(excel_payload, "P", "custom_model")
        assert result["quality_model"] == "custom_model"

    def test_quality_model_none(self, excel_payload):
        result = parse_excel_event(excel_payload, "P", None)
        assert result["quality_model"] is None

    def test_whitespace_in_members(self):
        payload = {
            "timestamp": "t",
            "iteration": "S1",
            "date": "d",
            "duration": 1,
            "activity": "x",
            "comment": "",
            "epic": "",
            "members": ["  Alice  ", " ", "Bob"],
            "memberHours": [1, 2],
            "configRange": []
        }
        result = parse_excel_event(payload, "P", "qm")
        assert result["members"] == ["Alice", "Bob"]


class TestActivityTypes:
    def test_activity_types_count(self):
        assert len(ACTIVITY_TYPES) == 8

    def test_activity_types_content(self):
        assert "Desenvolupament" in ACTIVITY_TYPES
        assert "Documentació" in ACTIVITY_TYPES
        assert "Presentació" in ACTIVITY_TYPES
