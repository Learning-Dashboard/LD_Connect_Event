"""Tests for datasources/github_handler.py"""

import pytest
from unittest.mock import patch, MagicMock


class TestParseGithubEvent:
    @patch(
        "datasources.github_handler.fetch_commit_stats",
        return_value={"total": 10, "additions": 7, "deletions": 3},
    )
    def test_push_event_dispatches(self, mock_stats, github_push_payload):
        from datasources.github_handler import parse_github_event

        result = parse_github_event(github_push_payload, "TestPrj")
        assert result["event"] == "commit"
        assert len(result["commits"]) == 1

    def test_issue_event_dispatches(self, github_issue_payload):
        from datasources.github_handler import parse_github_event

        result = parse_github_event(github_issue_payload, "TestPrj")
        assert result["event"] == "issue"
        assert result["action"] == "opened"

    @patch(
        "datasources.github_handler.to_madrid_local",
        return_value="2025-06-15T14:00:00.000",
    )
    def test_pull_request_event_dispatches(self, mock_tz, github_pr_payload):
        from datasources.github_handler import parse_github_event

        result = parse_github_event(github_pr_payload, "TestPrj")
        assert result["event"] == "pull_request"

    def test_unknown_event_returns_ignored(self):
        from datasources.github_handler import parse_github_event

        payload = {"X-GitHub-Event": "deployment"}
        result = parse_github_event(payload, "TestPrj")
        assert result["ignored"] is True
        assert result["event"] == "deployment"


class TestParseGithubPushEvent:
    @patch(
        "datasources.github_handler.fetch_commit_stats",
        return_value={"total": 15, "additions": 10, "deletions": 5},
    )
    def test_basic_push_parsing(self, mock_stats, github_push_payload):
        from datasources.github_handler import parse_github_push_event

        result = parse_github_push_event(github_push_payload, "TestPrj")

        assert result["event"] == "commit"
        assert result["repo_name"] == "TestOrg/test-repo"
        assert result["team_name"] == "TestOrg"
        assert result["sender_info"]["login"] == "devuser"
        assert result["sender_info"]["id"] == 1

    @patch(
        "datasources.github_handler.fetch_commit_stats",
        return_value={"total": 0, "additions": 0, "deletions": 0},
    )
    def test_commit_details(self, mock_stats, github_push_payload):
        from datasources.github_handler import parse_github_push_event

        result = parse_github_push_event(github_push_payload, "TestPrj")
        commit = result["commits"][0]

        assert commit["sha"] == "abc123def456"
        assert commit["user"]["login"] == "devuser"
        assert commit["user"]["name"] == "Dev User"
        assert commit["user"]["email"] == "dev@example.com"
        assert commit["message"] == "fix: resolve task #42 issue"
        assert commit["message_char_count"] == len("fix: resolve task #42 issue")
        assert commit["message_word_count"] == 5

    @patch(
        "datasources.github_handler.fetch_commit_stats",
        return_value={"total": 0, "additions": 0, "deletions": 0},
    )
    def test_task_reference_with_number(self, mock_stats, github_push_payload):
        from datasources.github_handler import parse_github_push_event

        result = parse_github_push_event(github_push_payload, "TestPrj")
        commit = result["commits"][0]

        assert commit["task_is_written"] is True
        assert commit["task_reference"] == 42

    @patch(
        "datasources.github_handler.fetch_commit_stats",
        return_value={"total": 0, "additions": 0, "deletions": 0},
    )
    def test_task_reference_catalan(self, mock_stats):
        from datasources.github_handler import parse_github_push_event

        payload = {
            "organization": {"login": "Org"},
            "repository": {"full_name": "Org/repo"},
            "sender": {},
            "commits": [
                {
                    "id": "sha1",
                    "url": "",
                    "message": "Implementar tasca #99",
                    "timestamp": "2025-06-15T10:30:00Z",
                    "author": {"username": "u", "name": "n", "email": "e"},
                }
            ],
        }
        result = parse_github_push_event(payload, "P")
        commit = result["commits"][0]
        assert commit["task_is_written"] is True
        assert commit["task_reference"] == 99

    @patch(
        "datasources.github_handler.fetch_commit_stats",
        return_value={"total": 0, "additions": 0, "deletions": 0},
    )
    def test_task_word_without_number(self, mock_stats):
        from datasources.github_handler import parse_github_push_event

        payload = {
            "organization": {"login": "Org"},
            "repository": {"full_name": "Org/repo"},
            "sender": {},
            "commits": [
                {
                    "id": "sha1",
                    "url": "",
                    "message": "Working on a task",
                    "timestamp": "2025-06-15T10:30:00Z",
                    "author": {"username": "u", "name": "n", "email": "e"},
                }
            ],
        }
        result = parse_github_push_event(payload, "P")
        commit = result["commits"][0]
        assert commit["task_is_written"] is True
        assert commit["task_reference"] is None

    @patch(
        "datasources.github_handler.fetch_commit_stats",
        return_value={"total": 0, "additions": 0, "deletions": 0},
    )
    def test_no_task_reference(self, mock_stats):
        from datasources.github_handler import parse_github_push_event

        payload = {
            "organization": {"login": "Org"},
            "repository": {"full_name": "Org/repo"},
            "sender": {},
            "commits": [
                {
                    "id": "sha1",
                    "url": "",
                    "message": "fix a bug",
                    "timestamp": "2025-06-15T10:30:00Z",
                    "author": {"username": "u", "name": "n", "email": "e"},
                }
            ],
        }
        result = parse_github_push_event(payload, "P")
        commit = result["commits"][0]
        assert commit["task_is_written"] is False
        assert commit["task_reference"] is None

    @patch(
        "datasources.github_handler.fetch_commit_stats",
        return_value={"total": 0, "additions": 0, "deletions": 0},
    )
    def test_empty_commits_list(self, mock_stats):
        from datasources.github_handler import parse_github_push_event

        payload = {
            "organization": {"login": "Org"},
            "repository": {"full_name": "Org/repo"},
            "sender": {},
            "commits": [],
        }
        result = parse_github_push_event(payload, "P")
        assert result["commits"] == []

    @patch(
        "datasources.github_handler.fetch_commit_stats",
        return_value={"total": 20, "additions": 15, "deletions": 5},
    )
    def test_commit_stats_stored(self, mock_stats, github_push_payload):
        from datasources.github_handler import parse_github_push_event

        result = parse_github_push_event(github_push_payload, "TestPrj")
        commit = result["commits"][0]
        assert commit["stats"] == {"total": 20, "additions": 15, "deletions": 5}

    @patch(
        "datasources.github_handler.fetch_commit_stats",
        return_value={"total": 0, "additions": 0, "deletions": 0},
    )
    def test_missing_organization(self, mock_stats):
        from datasources.github_handler import parse_github_push_event

        payload = {"repository": {"full_name": "Org/repo"}, "sender": {}, "commits": []}
        result = parse_github_push_event(payload, "P")
        assert result["team_name"] == "UnknownTeam"


class TestParseGithubIssueEvent:
    def test_basic_issue_parsing(self, github_issue_payload):
        from datasources.github_handler import parse_github_issue_event

        result = parse_github_issue_event(github_issue_payload, "TestPrj")

        assert result["event"] == "issue"
        assert result["action"] == "opened"
        assert result["repo_name"] == "TestOrg/test-repo"
        assert result["team_name"] == "TestOrg"

    def test_issue_object(self, github_issue_payload):
        from datasources.github_handler import parse_github_issue_event

        result = parse_github_issue_event(github_issue_payload, "TestPrj")
        issue = result["issue"]

        assert issue["number"] == 10
        assert issue["title"] == "Bug in login"
        assert issue["state"] == "open"
        assert issue["body"] == "Login fails with error 500"
        assert issue["user"]["login"] == "issueuser"

    def test_sender_info(self, github_issue_payload):
        from datasources.github_handler import parse_github_issue_event

        result = parse_github_issue_event(github_issue_payload, "TestPrj")
        assert result["sender_info"]["login"] == "issueuser"
        assert result["sender_info"]["id"] == 2


class TestParseGithubPullRequestEvent:
    @patch(
        "datasources.github_handler.to_madrid_local",
        return_value="2025-06-15T14:00:00.000",
    )
    def test_closed_pr_parsed(self, mock_tz, github_pr_payload):
        from datasources.github_handler import parse_github_pullrequest_event

        result = parse_github_pullrequest_event(github_pr_payload, "TestPrj")

        assert result["event"] == "pull_request"
        assert result["action"] == "closed"
        assert result["pr_number"] == 5
        assert result["title"] == "Add feature X"
        assert result["merged_by"] == "merger"
        assert result["reviewers"] == ["reviewer1"]

    def test_non_closed_pr_ignored(self):
        from datasources.github_handler import parse_github_pullrequest_event

        payload = {
            "action": "opened",
            "organization": {"login": "Org"},
            "repository": {"full_name": "Org/repo"},
            "sender": {},
            "pull_request": {},
        }
        result = parse_github_pullrequest_event(payload, "P")
        assert result["ignored"] is True

    @patch("datasources.github_handler.to_madrid_local", return_value="")
    def test_pr_no_assignee(self, mock_tz):
        from datasources.github_handler import parse_github_pullrequest_event

        payload = {
            "action": "closed",
            "organization": {"login": "Org"},
            "repository": {"full_name": "Org/repo"},
            "sender": {},
            "pull_request": {
                "number": 1,
                "title": "PR",
                "created_at": "",
                "closed_at": "",
                "merged": False,
                "merged_by": {},
                "assignee": None,
                "requested_reviewers": [],
            },
        }
        result = parse_github_pullrequest_event(payload, "P")
        assert result["reviewers"] == []
