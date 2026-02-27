"""Tests for utils/recovery/github_recovery.py"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


class TestParseDt:
    def test_date_only(self):
        from utils.recovery.github_recovery import parse_dt
        result = parse_dt("2025-06-15")
        assert result is not None
        assert result.year == 2025
        assert result.month == 6
        assert result.day == 15

    def test_datetime_with_time(self):
        from utils.recovery.github_recovery import parse_dt
        result = parse_dt("2025-06-15T14:30")
        assert result.hour == 14
        assert result.minute == 30

    def test_none_returns_none(self):
        from utils.recovery.github_recovery import parse_dt
        result = parse_dt(None)
        assert result is None

    def test_empty_string_returns_none(self):
        from utils.recovery.github_recovery import parse_dt
        result = parse_dt("")
        assert result is None

    def test_timezone_aware(self):
        from utils.recovery.github_recovery import parse_dt
        result = parse_dt("2025-06-15")
        assert result.tzinfo is not None


class TestGetOrganizationRepos:
    @patch("utils.recovery.github_recovery.gh_paginated")
    def test_returns_repo_names(self, mock_pag):
        from utils.recovery.github_recovery import get_organization_repos
        mock_pag.return_value = [
            {"name": "repo1"},
            {"name": "repo2"},
        ]
        repos = get_organization_repos("TestOrg", {"Authorization": "Bearer tok"})
        assert repos == ["repo1", "repo2"]


class TestGhPaginated:
    @patch("utils.recovery.github_recovery.requests.get")
    def test_single_page(self, mock_get):
        from utils.recovery.github_recovery import gh_paginated

        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": 1}, {"id": 2}]
        mock_resp.raise_for_status = MagicMock()
        mock_resp.links = {}
        mock_get.return_value = mock_resp

        results = list(gh_paginated("https://api.github.com/test", {}))
        assert len(results) == 2

    @patch("utils.recovery.github_recovery.requests.get")
    def test_multiple_pages(self, mock_get):
        from utils.recovery.github_recovery import gh_paginated

        # First page
        resp1 = MagicMock()
        resp1.json.return_value = [{"id": 1}]
        resp1.raise_for_status = MagicMock()
        resp1.links = {"next": {"url": "https://api.github.com/test?page=2"}}

        # Second page
        resp2 = MagicMock()
        resp2.json.return_value = [{"id": 2}]
        resp2.raise_for_status = MagicMock()
        resp2.links = {}

        mock_get.side_effect = [resp1, resp2]

        results = list(gh_paginated("https://api.github.com/test", {}))
        assert len(results) == 2
        assert results[0]["id"] == 1
        assert results[1]["id"] == 2


class TestUpsert:
    def test_upsert_empty_list(self):
        from utils.recovery.github_recovery import upsert
        mock_coll = MagicMock()
        result = upsert(mock_coll, [], "sha")
        assert result == 0
        mock_coll.bulk_write.assert_not_called()

    def test_upsert_with_docs(self):
        from utils.recovery.github_recovery import upsert
        mock_coll = MagicMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_result.upserted_ids = {0: "id1"}
        mock_coll.bulk_write.return_value = mock_result

        docs = [{"sha": "abc", "msg": "hi"}, {"sha": "def", "msg": "bye"}]
        result = upsert(mock_coll, docs, "sha")
        assert result == 2  # 1 matched + 1 upserted
        mock_coll.bulk_write.assert_called_once()


class TestCollectGithub:
    @patch("utils.recovery.github_recovery.notify_eval_push")
    @patch("utils.recovery.github_recovery.get_collection")
    @patch("utils.recovery.github_recovery.parse_github_event")
    @patch("utils.recovery.github_recovery.gh_paginated")
    def test_collect_commits(self, mock_pag, mock_parse, mock_coll, mock_notify):
        from utils.recovery.github_recovery import collect_github

        mock_pag.return_value = [{
            "sha": "abc123",
            "url": "https://github.com/Org/repo/commit/abc123",
            "commit": {
                "message": "fix bug",
                "author": {"date": "2025-06-15T10:00:00Z", "name": "Dev", "email": "d@e.com"}
            },
            "author": {"login": "dev"}
        }]

        mock_parse.return_value = {
            "event": "commit",
            "team_name": "Org",
            "repo_name": "Org/repo",
            "sender_info": {"login": "dev"},
            "commits": [{"sha": "abc123", "message": "fix bug"}]
        }

        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_result.upserted_ids = {0: "id1"}
        mock_collection.bulk_write.return_value = mock_result
        mock_coll.return_value = mock_collection

        collect_github("Org", "repo", "TestPrj", ["commits"], None, None, "default")

        mock_coll.assert_called_with("github_TestPrj.commits")
        mock_notify.assert_called_once()

    @patch("utils.recovery.github_recovery.notify_eval_push")
    @patch("utils.recovery.github_recovery.get_collection")
    @patch("utils.recovery.github_recovery.parse_github_event")
    @patch("utils.recovery.github_recovery.gh_paginated")
    def test_collect_issues(self, mock_pag, mock_parse, mock_coll, mock_notify):
        from utils.recovery.github_recovery import collect_github

        mock_pag.return_value = [{
            "number": 1,
            "state": "open",
            "user": {"login": "dev"},
            "title": "Bug"
        }]

        mock_parse.return_value = {
            "event": "issue",
            "team_name": "Org",
            "repo_name": "Org/repo",
            "sender_info": {"login": "dev"},
            "issue": {"number": 1}
        }

        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_result.upserted_ids = {0: "id1"}
        mock_collection.bulk_write.return_value = mock_result
        mock_coll.return_value = mock_collection

        collect_github("Org", "repo", "TestPrj", ["issues"], None, None, "default")
        mock_coll.assert_called_with("github_TestPrj.issues")

    @patch("utils.recovery.github_recovery.notify_eval_push")
    @patch("utils.recovery.github_recovery.get_collection")
    @patch("utils.recovery.github_recovery.parse_github_event")
    @patch("utils.recovery.github_recovery.gh_paginated")
    def test_collect_pull_requests(self, mock_pag, mock_parse, mock_coll, mock_notify):
        from utils.recovery.github_recovery import collect_github

        mock_pag.return_value = [{
            "number": 5,
            "user": {"login": "dev"},
            "title": "PR"
        }]

        mock_parse.return_value = {
            "event": "pull_request",
            "team_name": "Org",
            "repo_name": "Org/repo",
            "sender_info": {"login": "dev"},
            "pr_number": 5
        }

        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_result.upserted_ids = {0: "id1"}
        mock_collection.bulk_write.return_value = mock_result
        mock_coll.return_value = mock_collection

        collect_github("Org", "repo", "TestPrj", ["pull_requests"], None, None, "default")
        mock_coll.assert_called_with("github_TestPrj.pull_requests")

    @patch("utils.recovery.github_recovery.notify_eval_push")
    @patch("utils.recovery.github_recovery.get_collection")
    @patch("utils.recovery.github_recovery.gh_paginated")
    def test_unsupported_event_logged(self, mock_pag, mock_coll, mock_notify):
        from utils.recovery.github_recovery import collect_github
        # Should not crash on unsupported event
        collect_github("Org", "repo", "P", ["unsupported"], None, None, "default")
