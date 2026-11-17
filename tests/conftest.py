"""
Shared pytest fixtures for the LD_Connect_Event test suite.
"""

import os
import json
import pytest

# ── Set required env vars BEFORE any application module is imported ──────────
os.environ.setdefault("GITHUB_SIGNATURE_KEY", "test-github-secret")
os.environ.setdefault("TAIGA_SIGNATURE_KEY", "test-taiga-secret")
os.environ.setdefault("MONGO_HOST", "localhost")
os.environ.setdefault("MONGO_PORT", "27017")
os.environ.setdefault("MONGO_DB", "testdb")


# ── Fixtures ─────────────────────────────────────────────────────────────────


OWN_TAIGA_API_URL = "https://taiga.course-a.example/api/v1"
OWN_TAIGA_AUTH_URL = "https://taiga.course-a.example/api/v1/auth"
FALLBACK_TAIGA_API_URL = "https://api.taiga.io/api/v1"
FALLBACK_TAIGA_AUTH_URL = "https://api.taiga.io/api/v1/auth"


@pytest.fixture
def fallback_taiga(monkeypatch):
    """Configure the TAIGA_FALLBACK_* settings used by subjects without their own Taiga."""
    monkeypatch.setattr("config.settings.TAIGA_FALLBACK_API_URL", FALLBACK_TAIGA_API_URL)
    monkeypatch.setattr("config.settings.TAIGA_FALLBACK_AUTH_URL", FALLBACK_TAIGA_AUTH_URL)
    monkeypatch.setattr("config.settings.TAIGA_FALLBACK_USERNAME", "fallback_user")
    monkeypatch.setattr("config.settings.TAIGA_FALLBACK_PASSWORD", "fallback_pass")


@pytest.fixture
def write_credentials(tmp_path, monkeypatch, fallback_taiga):
    """Return a function that writes a credentials config and points CREDENTIALS_FILE to it."""

    def _write(data) -> str:
        p = tmp_path / "creds.json"
        p.write_text(data if isinstance(data, str) else json.dumps(data))
        monkeypatch.setenv("CREDENTIALS_FILE", str(p))
        return str(p)

    return _write


@pytest.fixture
def sample_credentials_config(write_credentials):
    """Credentials config with one subject on its own Taiga and one on the fallback Taiga.

    CREDENTIALS_FILE points to it for the duration of the test. Returns its path.
    """
    return write_credentials(
        {
            "course_a": {
                "github_token": "ghp_FAKETOKEN123",
                "taiga_api_url": OWN_TAIGA_API_URL,
                "taiga_auth_url": OWN_TAIGA_AUTH_URL,
                "taiga_token": "app:token:hash",
                "teams": ["TeamAlpha", "TeamBeta"],
            },
            "course_b": {
                "github_token": "ghp_FAKETOKEN456",
                "taiga_api_url": "",
                "taiga_auth_url": "",
                "taiga_token": "",
                "teams": ["TeamGamma"],
            },
        }
    )


@pytest.fixture
def flask_app():
    """Create a Flask test application."""
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(flask_app):
    """Flask test client."""
    return flask_app.test_client()


# ── Sample payloads ──────────────────────────────────────────────────────────


@pytest.fixture
def github_push_payload():
    """Minimal GitHub push webhook payload."""
    return {
        "X-GitHub-Event": "push",
        "organization": {"login": "TestOrg"},
        "repository": {"full_name": "TestOrg/test-repo"},
        "sender": {
            "id": 1,
            "login": "devuser",
            "url": "https://api.github.com/users/devuser",
            "type": "User",
            "site_admin": False,
        },
        "commits": [
            {
                "id": "abc123def456",
                "url": "https://github.com/TestOrg/test-repo/commit/abc123def456",
                "message": "fix: resolve task #42 issue",
                "timestamp": "2025-06-15T10:30:00Z",
                "author": {
                    "username": "devuser",
                    "name": "Dev User",
                    "email": "dev@example.com",
                },
            }
        ],
    }


@pytest.fixture
def github_issue_payload():
    """Minimal GitHub issue webhook payload."""
    return {
        "X-GitHub-Event": "issues",
        "action": "opened",
        "organization": {"login": "TestOrg"},
        "repository": {"full_name": "TestOrg/test-repo"},
        "sender": {
            "id": 2,
            "login": "issueuser",
            "url": "https://api.github.com/users/issueuser",
            "type": "User",
            "site_admin": False,
        },
        "issue": {
            "number": 10,
            "title": "Bug in login",
            "state": "open",
            "body": "Login fails with error 500",
            "user": {"login": "issueuser", "id": 2},
        },
    }


@pytest.fixture
def github_pr_payload():
    """Minimal GitHub pull_request (closed) webhook payload."""
    return {
        "X-GitHub-Event": "pull_request",
        "action": "closed",
        "organization": {"login": "TestOrg"},
        "repository": {"full_name": "TestOrg/test-repo"},
        "sender": {
            "id": 3,
            "login": "pruser",
            "url": "https://api.github.com/users/pruser",
            "type": "User",
            "site_admin": False,
        },
        "pull_request": {
            "number": 5,
            "title": "Add feature X",
            "created_at": "2025-06-10T08:00:00Z",
            "closed_at": "2025-06-15T12:00:00Z",
            "merged": True,
            "merged_by": {"login": "merger"},
            "assignee": {"login": "pruser"},
            "requested_reviewers": [{"login": "reviewer1"}],
        },
    }


@pytest.fixture
def taiga_task_payload():
    """Minimal Taiga task webhook payload."""
    return {
        "type": "task",
        "action": "create",
        "by": {"username": "taigauser"},
        "data": {
            "id": 100,
            "project": {"id": 1, "name": "TestProject"},
            "subject": "Implement login",
            "user_story": {"id": 50, "is_closed": False},
            "status": {"name": "New", "is_closed": False},
            "created_date": "2025-06-01T10:00:00Z",
            "modified_date": "2025-06-10T15:00:00Z",
            "finished_date": None,
            "ref": 42,
            "milestone": {
                "id": 10,
                "name": "Sprint 1",
                "closed": False,
                "created_date": "2025-05-01T00:00:00Z",
                "modified_date": "2025-06-01T00:00:00Z",
                "estimated_start": "2025-05-01T00:00:00Z",
                "estimated_finish": "2025-06-01T00:00:00Z",
            },
            "assigned_to": {"username": "dev1"},
            "custom_attributes_values": {"story_points": 5},
        },
    }


@pytest.fixture
def taiga_issue_payload():
    """Minimal Taiga issue webhook payload."""
    return {
        "type": "issue",
        "action": "create",
        "by": {"username": "taigauser"},
        "data": {
            "id": 200,
            "project": {"id": 1, "name": "TestProject"},
            "subject": "Bug report",
            "due_date": "2025-07-01T00:00:00Z",
            "description": "Something is broken",
            "severity": {"name": "Normal"},
            "status": {"name": "New"},
            "priority": {"name": "High"},
            "type": {"name": "Bug"},
            "is_closed": False,
            "modified_date": "2025-06-10T10:00:00Z",
            "created_date": "2025-06-01T08:00:00Z",
            "finished_date": None,
            "assigned_to": {"username": "dev2"},
        },
        "is_closed": False,
    }


@pytest.fixture
def taiga_epic_payload():
    """Minimal Taiga epic webhook payload."""
    return {
        "type": "epic",
        "action": "create",
        "by": {"username": "taigauser"},
        "data": {
            "id": 300,
            "project": {"id": 1, "name": "TestProject"},
            "subject": "Epic feature",
            "status": {"name": "New"},
            "is_closed": False,
            "modified_date": "2025-06-10T10:00:00Z",
            "created_date": "2025-06-01T08:00:00Z",
        },
        "is_closed": False,
    }


@pytest.fixture
def taiga_userstory_payload():
    """Minimal Taiga userstory webhook payload."""
    return {
        "type": "userstory",
        "action": "create",
        "by": {"username": "taigauser"},
        "data": {
            "id": 400,
            "project": {"id": 1, "name": "TestProject"},
            "subject": "User login",
            "status": {"name": "New"},
            "is_closed": False,
            "modified_date": "2025-06-10T10:00:00Z",
            "created_date": "2025-06-01T08:00:00Z",
            "description": "As a user I want to login so that I can access my dashboard",
            "custom_attributes_values": {"Priority": "High"},
            "points": [{"value": 3}, {"value": 5}],
            "milestone": {
                "id": 10,
                "name": "Sprint 1",
                "closed": False,
                "created_date": "2025-05-01T00:00:00Z",
                "modified_date": "2025-06-01T00:00:00Z",
                "estimated_start": "2025-05-01T00:00:00Z",
                "estimated_finish": "2025-06-01T00:00:00Z",
            },
        },
        "is_closed": False,
    }


@pytest.fixture
def taiga_related_userstory_payload():
    """Minimal Taiga related userstory webhook payload."""
    return {
        "type": "relateduserstory",
        "action": "create",
        "by": {"username": "taigauser"},
        "data": {
            "user_story": {"id": 400},
            "epic": {
                "id": 300,
                "subject": "Epic feature",
                "ref": 1,
                "project": {"name": "TestProject"},
            },
            "finished_date": "2025-07-01T12:00:00Z",
            "assigned_to": {"username": "dev1"},
        },
    }


@pytest.fixture
def excel_payload():
    """Minimal Excel webhook payload."""
    return {
        "timestamp": "2025-06-15T10:00:00",
        "iteration": "Sprint 1",
        "date": "2025-06-15",
        "duration": 2.5,
        "activity": "Desenvolupament",
        "comment": "Worked on feature X",
        "epic": "Epic 1",
        "members": ["Alice", "Bob", ""],
        "memberHours": [3, 2],
        "configRange": [0, 0, 0, 0, 5, 0, 0, 0],
    }
