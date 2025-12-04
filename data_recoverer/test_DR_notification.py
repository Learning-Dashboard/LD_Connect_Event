"""
Unit tests for the data recovery notification logic.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock, patch

import mongomock
import pytest

from data_recoverer.DR_api import RecoveryBatch
from data_recoverer.DR_recovery import (
    DataRecoverer,
    GitHubProjectConfig,
    ProjectConfig,
    RecoveryConfig,
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


@patch("data_recoverer.DR_recovery.notify_eval_push")
def test_recoverer_notifies_eval_on_success(mock_notify):
    mongo_client = mongomock.MongoClient()
    db = mongo_client["tests"]
    collection_resolver = lambda name: db[name]

    # Create a batch with a document that has necessary fields
    doc = {
        "sha": "abc", 
        "value": 1,
        "event": "push",
        "prj": "team",
        "author_login": "alice"
    }
    gh_batch = RecoveryBatch(
        collection="github_team.commits", key_field="sha", documents=[doc]
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

    recoverer = DataRecoverer(
        config,
        github_client=FakeGitHubClient([gh_batch]),
        collection_resolver=collection_resolver,
    )

    interval = _interval()
    db["inactivity_intervals"].insert_one(interval.to_document())

    summary = recoverer.run_once()

    assert summary["processed_intervals"] == 1
    
    # Verify notify_eval_push was called
    mock_notify.assert_called_once()
    args, _ = mock_notify.call_args
    # Expected args: event_type, prj, author_login, quality_model
    assert args[0] == "push"
    assert args[1] == "team"
    assert args[2] == "alice"
    assert args[3] is None  # quality_model not in doc


@patch("data_recoverer.DR_recovery.notify_eval_push")
def test_recoverer_notifies_eval_with_fallback_fields(mock_notify):
    mongo_client = mongomock.MongoClient()
    db = mongo_client["tests"]
    collection_resolver = lambda name: db[name]

    # Document without explicit author_login, but with sender_info (GitHub style)
    doc = {
        "sha": "xyz", 
        "event": "push",
        "prj": "team",
        "sender_info": {"login": "bob"}
    }
    gh_batch = RecoveryBatch(
        collection="github_team.commits", key_field="sha", documents=[doc]
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

    recoverer = DataRecoverer(
        config,
        github_client=FakeGitHubClient([gh_batch]),
        collection_resolver=collection_resolver,
    )

    interval = _interval()
    db["inactivity_intervals"].insert_one(interval.to_document())

    recoverer.run_once()

    mock_notify.assert_called_once()
    args, _ = mock_notify.call_args
    assert args[2] == "bob"


@patch("data_recoverer.DR_recovery.notify_eval_push")
def test_recoverer_maps_commit_to_push(mock_notify):
    mongo_client = mongomock.MongoClient()
    db = mongo_client["tests"]
    collection_resolver = lambda name: db[name]

    # Document with event="commit" (as produced by github_handler)
    doc = {
        "sha": "123", 
        "event": "commit",
        "prj": "team",
        "author_login": "dave"
    }
    gh_batch = RecoveryBatch(
        collection="github_team.commits", key_field="sha", documents=[doc]
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

    recoverer = DataRecoverer(
        config,
        github_client=FakeGitHubClient([gh_batch]),
        collection_resolver=collection_resolver,
    )

    interval = _interval()
    db["inactivity_intervals"].insert_one(interval.to_document())

    recoverer.run_once()

    mock_notify.assert_called_once()
    args, _ = mock_notify.call_args
    # Verify that "commit" was mapped to "push"
    assert args[0] == "push"
    assert args[1] == "team"
    assert args[2] == "dave"
