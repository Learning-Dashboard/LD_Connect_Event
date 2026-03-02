"""Tests for utils/datetime_utils.py"""

import pytest
from utils.datetime_utils import to_madrid_local


class TestToMadridLocal:
    def test_utc_timestamp_converted(self):
        result = to_madrid_local("2025-06-15T10:00:00Z")
        # UTC+2 in summer (CEST) → 12:00
        assert "12:00:00" in result

    def test_utc_offset_format(self):
        result = to_madrid_local("2025-06-15T10:00:00+00:00")
        assert "12:00:00" in result

    def test_winter_time(self):
        # January = CET = UTC+1
        result = to_madrid_local("2025-01-15T10:00:00Z")
        assert "11:00:00" in result

    def test_empty_string_returns_empty(self):
        result = to_madrid_local("")
        assert result == ""

    def test_none_returns_none(self):
        result = to_madrid_local(None)
        assert result is None

    def test_output_format_milliseconds(self):
        result = to_madrid_local("2025-06-15T10:00:00Z")
        # Should end with milliseconds
        assert result.endswith(".000")

    def test_already_offset_timestamp(self):
        # Input already at +03:00
        result = to_madrid_local("2025-06-15T15:00:00+03:00")
        # 15:00 at +03:00 = 12:00 UTC = 14:00 Madrid (CEST/UTC+2)
        assert "14:00:00" in result

    def test_full_iso_output(self):
        result = to_madrid_local("2025-06-15T00:00:00Z")
        # Should be a valid ISO format
        assert "T" in result
        assert len(result) > 10
