"""
Unit tests for the inactivity detector.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mongomock
import pytest

from inactivity_detector.ID_database import InactivityRepository, UserInactivityRepository
from inactivity_detector.ID_detector import (
    DetectorConfig,
    HeartbeatConfig,
    InactivityDetector,
    LogSourceConfig,
    OutputConfig,
)


@pytest.fixture()
def detector_components(tmp_path: Path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    artifacts_dir = tmp_path / "artifacts"

    heartbeat_cfg = HeartbeatConfig(
        collection="system_heartbeats",
        timestamp_field="emitted_at",
        status_field="status",
        ok_value="alive",
        interval_seconds=60,
        max_missed=1,
    )
    log_cfg = LogSourceConfig(
        name="github_stream",
        project_id="TeamX",
        source_type="file",
        inactivity_threshold=timedelta(minutes=10),
        root_dir=logs_dir,
        glob_pattern="*.log",
        timestamp_field="timestamp",
        tail_lines=100,
    )
    output_cfg = OutputConfig(
        base_dir=artifacts_dir,
        events_dir=artifacts_dir / "events",
        reports_dir=artifacts_dir / "runs",
        enabled=False,
    )
    config = DetectorConfig(
        heartbeat=heartbeat_cfg,
        log_sources=[log_cfg],
        outputs=output_cfg,
        inactivity_collection="inactivity_intervals_test",
    )
    mongo_client = mongomock.MongoClient()
    db = mongo_client["detector_tests"]

    repository = InactivityRepository(
        "inactivity_intervals_test", collection=db["inactivity_intervals_test"]
    )
    user_repository = UserInactivityRepository(
        "user_inactivity_test", collection=db["user_inactivity_test"]
    )

    detector = InactivityDetector(
        config,
        repository=repository,
        user_repository=user_repository,
        collection_resolver=lambda name: db[name],
    )
    return {
        "detector": detector,
        "db": db,
        "logs_dir": logs_dir,
        "heartbeat_collection": db["system_heartbeats"],
        "downtime_collection": db["inactivity_intervals_test"],
        "user_collection": db["user_inactivity_test"],
    }


def _write_log(logs_dir: Path, timestamp: datetime) -> None:
    log_path = logs_dir / "events.log"
    log_path.write_text(
        json.dumps({"timestamp": timestamp.isoformat()}) + "\n",
        encoding="utf-8",
    )


def test_downtime_detection_records_heartbeat_only(detector_components):
    detector = detector_components["detector"]
    hb_collection = detector_components["heartbeat_collection"]
    logs_dir = detector_components["logs_dir"]
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    hb_collection.insert_one({"emitted_at": now - timedelta(minutes=5), "status": "alive"})
    _write_log(logs_dir, now - timedelta(minutes=20))

    intervals = detector.run_once(now=now)

    assert len(intervals) == 1
    interval = intervals[0]
    assert interval.detection_method == "heartbeat"
    assert interval.severity == "critical"

    downtime_doc = detector_components["downtime_collection"].find_one()
    assert downtime_doc is not None
    assert downtime_doc["detection_method"] == "heartbeat"

    user_docs = list(detector_components["user_collection"].find())
    assert len(user_docs) == 1
    assert user_docs[0]["stream_name"] == "github_stream"


def test_log_inactivity_persists_without_downtime(detector_components):
    detector = detector_components["detector"]
    hb_collection = detector_components["heartbeat_collection"]
    logs_dir = detector_components["logs_dir"]
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    hb_collection.insert_one({"emitted_at": now - timedelta(seconds=30), "status": "alive"})
    _write_log(logs_dir, now - timedelta(minutes=30))

    intervals = detector.run_once(now=now)

    assert intervals == []
    assert detector_components["downtime_collection"].count_documents({}) == 0
    user_docs = list(detector_components["user_collection"].find())
    assert len(user_docs) == 1
    assert user_docs[0]["gap_seconds"] > 0


def test_no_events_with_recent_activity(detector_components):
    detector = detector_components["detector"]
    hb_collection = detector_components["heartbeat_collection"]
    logs_dir = detector_components["logs_dir"]
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    hb_collection.insert_one({"emitted_at": now - timedelta(seconds=30), "status": "alive"})
    _write_log(logs_dir, now - timedelta(minutes=2))

    intervals = detector.run_once(now=now)

    assert intervals == []
    assert detector_components["downtime_collection"].count_documents({}) == 0
    assert detector_components["user_collection"].count_documents({}) == 0
