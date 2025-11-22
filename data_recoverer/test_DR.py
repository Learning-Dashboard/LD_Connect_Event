"""
Unit tests for the data recovery module.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import mongomock
import pytest

from data_recoverer.DR_api import RecoveryBatch
from data_recoverer.DR_recovery import (
    DataRecoverer,
    GitHubProjectConfig,
    ProjectConfig,
    RecoveryConfig,
    StartupRunConfig,
    TaigaProjectConfig,
)
from inactivity_detector.ID_database import InactivityInterval

MADRID_TZ = ZoneInfo("Europe/Madrid")


class FakeGitHubClient:
    def __init__(self, batches):
        self._batches = batches
        self.calls = []

    def collect_batches(self, **kwargs):
        self.calls.append(kwargs)
        return self._batches


class FakeTaigaClient:
    def __init__(self, batches):
        self._batches = batches
        self.calls = []

    def collect_batches(self, **kwargs):
        self.calls.append(kwargs)
        return self._batches


def _interval(hours_ago: int = 1) -> InactivityInterval:
    end = datetime.now(MADRID_TZ)
    start = end - timedelta(hours=hours_ago)
    return InactivityInterval(
        detection_method="heartbeat",
        start_time=start,
        end_time=end,
        detection_source="heartbeat",
        severity="critical",
        duration_minutes=hours_ago * 60,
        metadata={},
    )


def test_recoverer_upserts_and_logs_success():
    mongo_client = mongomock.MongoClient()
    db = mongo_client["tests"]
    collection_resolver = lambda name: db[name]

    gh_batch = RecoveryBatch(
        collection="github_team.commits", key_field="sha", documents=[{"sha": "abc", "value": 1}]
    )
    tg_batch = RecoveryBatch(
        collection="taiga_team.tasks", key_field="task_id", documents=[{"task_id": 1, "value": 2}]
    )

    config = RecoveryConfig(
        inactivity_collection="inactivity_intervals",
        run_log_collection="data_recovery_runs",
        projects=[
            ProjectConfig(
                project_id="team",
                github=GitHubProjectConfig(repositories=["org/repo"]),
                taiga=TaigaProjectConfig(slug="project-slug"),
            )
        ],
    )

    recoverer = DataRecoverer(
        config,
        github_client=FakeGitHubClient([gh_batch]),
        taiga_client=FakeTaigaClient([tg_batch]),
        collection_resolver=collection_resolver,
    )

    interval = _interval()
    db["inactivity_intervals"].insert_one(interval.to_document())

    summary = recoverer.run_once()

    assert summary["processed_intervals"] == 1
    assert db["github_team.commits"].count_documents({}) == 1
    assert db["taiga_team.tasks"].count_documents({}) == 1
    run_log = db["data_recovery_runs"].find_one()
    assert run_log is not None
    assert run_log["status"] == "success"


def test_github_batches_shape_documents_with_prj(monkeypatch):
    from data_recoverer import DR_api

    client = DR_api.GitHubAPIClient()

    monkeypatch.setattr(
        "datasources.github_handler.fetch_commit_stats",
        lambda *_, **__: {"total": 1, "additions": 1, "deletions": 0},
    )

    def fake_paginate(url, headers):
        if "commits" in url:
            yield {
                "sha": "1",
                "url": "http://example/commit/1",
                "commit": {"message": "feat: add", "author": {"date": "2025-01-01T10:00:00Z", "name": "A", "email": "a@x"}},
                "author": {"login": "alice"},
            }
        elif "issues" in url:
            yield {"id": 9, "number": 9, "title": "Bug", "state": "open", "user": {"login": "alice"}, "updated_at": "2025-01-01T10:00:00Z"}
        else:
            yield {
                "id": 3,
                "number": 3,
                "title": "PR",
                "state": "closed",
                "created_at": "2025-01-01T09:00:00Z",
                "closed_at": "2025-01-01T11:00:00Z",
                "merged": True,
                "merged_by": {"login": "bob"},
                "user": {"login": "alice"},
                "updated_at": "2025-01-01T12:00:00Z",
                "assignee": {"login": "bob"},
                "requested_reviewers": [],
            }

    monkeypatch.setattr(client, "_paginate", fake_paginate)

    batches = client.collect_batches(
        prj="team",
        repositories=["org/repo"],
        since=datetime(2025, 1, 1, tzinfo=MADRID_TZ),
        until=datetime(2025, 1, 2, tzinfo=MADRID_TZ),
        event_types=["commits", "issues", "pull_requests"],
    )

    collections = {b.collection for b in batches}
    assert "github_team.commits" in collections
    assert "github_team.issues" in collections
    assert "github_team.pull_requests" in collections

    commit_batch = next(b for b in batches if b.collection.endswith("commits"))
    assert commit_batch.documents[0]["prj"] == "team"
    issue_batch = next(b for b in batches if b.collection.endswith("issues"))
    assert issue_batch.documents[0]["issue_id"] == 9


def test_startup_run_config_parsing_and_since(monkeypatch):
    fixed_now = datetime(2025, 1, 2, 12, 0, tzinfo=MADRID_TZ)
    cfg = RecoveryConfig.from_mapping(
        {
            "data_recoverer": {
                "startup_run": {"enabled": True, "since_hours": 6, "limit": 3, "dry_run": True},
                "projects": [],
            }
        }
    )
    startup = cfg.startup_run
    assert isinstance(startup, StartupRunConfig)
    assert startup.enabled is True
    assert startup.limit == 3
    assert startup.dry_run is True
    resolved = startup.resolve_since(now=fixed_now)
    assert resolved == fixed_now - timedelta(hours=6)


def test_interval_bounds_extend_to_last_heartbeat():
    mongo_client = mongomock.MongoClient()
    db = mongo_client["tests"]
    collection_resolver = lambda name: db[name]

    gh_batch = RecoveryBatch(
        collection="github_team.commits", key_field="sha", documents=[{"sha": "abc", "value": 1}]
    )

    config = RecoveryConfig(
        inactivity_collection="inactivity_intervals",
        run_log_collection="data_recovery_runs",
        projects=[
            ProjectConfig(
                project_id="team",
                github=GitHubProjectConfig(repositories=["org/repo"]),
            )
        ],
    )

    interval = _interval()
    last_hb = interval.start_time - timedelta(minutes=5)
    interval.metadata = {
        "heartbeat": {
            "last_heartbeat": last_hb.isoformat(),
        }
    }

    db["inactivity_intervals"].insert_one(interval.to_document())

    gh_client = FakeGitHubClient([gh_batch])
    recoverer = DataRecoverer(
        config,
        github_client=gh_client,
        taiga_client=FakeTaigaClient([]),
        collection_resolver=collection_resolver,
    )

    recoverer.run_once()

    assert gh_client.calls, "GitHub client was not invoked"
    assert gh_client.calls[0]["since"] == last_hb
