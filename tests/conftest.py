"""
Shared pytest fixtures for the LD_Connect_Event test suite.
"""

import os, json, pytest

# ── Set required env vars BEFORE any application module is imported ──────────
os.environ.setdefault("GITHUB_SIGNATURE_KEY", "test-github-secret")
os.environ.setdefault("TAIGA_SIGNATURE_KEY", "test-taiga-secret")
os.environ.setdefault("TAIGA_API_URL", "https://api.taiga.io/api/v1")
os.environ.setdefault("TAIGA_USERNAME", "testuser")
os.environ.setdefault("TAIGA_PASSWORD", "testpass")
os.environ.setdefault("MONGO_HOST", "localhost")
os.environ.setdefault("MONGO_PORT", "27017")
os.environ.setdefault("MONGO_DB", "testdb")


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_credentials_config(tmp_path):
    """Create a temporary credentials JSON file and return its path."""
    data = {
        "course_a": {
            "github_token": "ghp_FAKETOKEN123",
            "taiga_user": "tuser",
            "taiga_password": "tpass",
            "teams": ["TeamAlpha", "TeamBeta"],
        },
        "course_b": {
            "github_token": "ghp_FAKETOKEN456",
            "taiga_user": "",
            "taiga_password": "",
            "teams": ["TeamGamma"],
        },
    }
    p = tmp_path / "creds.json"
    p.write_text(json.dumps(data))
    return str(p)


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
