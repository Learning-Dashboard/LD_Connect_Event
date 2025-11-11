"""
Persistence helpers for the Inactivity Detector.

The repository wraps MongoDB collections so the detector can focus on business
logic. All datetimes are normalized to UTC before storage to simplify queries.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from database.mongo_client import get_collection


def _ensure_utc(value: datetime) -> datetime:
    """Normalize naive datetimes to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass
class InactivityInterval:
    """
    Represents a detected inactivity interval for a given project.
    """

    project_id: str
    detection_method: str  # log | heartbeat | hybrid
    start_time: datetime
    end_time: datetime
    detection_source: str
    severity: str
    duration_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_document(self) -> Dict[str, Any]:
        """Serialize the dataclass to a Mongo-friendly dict."""
        doc = asdict(self)
        doc["start_time"] = _ensure_utc(self.start_time)
        doc["end_time"] = _ensure_utc(self.end_time)
        doc["duration_seconds"] = float(self.duration_seconds)
        doc.setdefault("last_updated", datetime.now(timezone.utc))
        return doc

    @classmethod
    def from_document(cls, data: Dict[str, Any]) -> "InactivityInterval":
        """Create an interval from a Mongo document."""
        return cls(
            project_id=data["project_id"],
            detection_method=data["detection_method"],
            start_time=_ensure_utc(data["start_time"]),
            end_time=_ensure_utc(data["end_time"]),
            detection_source=data.get("detection_source", data["detection_method"]),
            severity=data.get("severity", "warning"),
            duration_seconds=data.get("duration_seconds", 0.0),
            metadata=data.get("metadata", {}),
        )


class InactivityRepository:
    """
    Thin wrapper around the Mongo collection used for inactivity events.
    """

    def __init__(self, collection_name: str, *, collection=None) -> None:
        self.collection = collection or get_collection(collection_name)
        # Index to keep queries deterministic when upserting.
        self.collection.create_index(
            [("project_id", 1), ("detection_method", 1), ("start_time", 1)],
            name="project_method_start_idx",
            unique=True,
        )
        self.collection.create_index(
            [("end_time", -1)],
            name="end_time_idx",
        )

    def save_interval(self, interval: InactivityInterval) -> Dict[str, Any]:
        """
        Upsert an inactivity interval. If the same (project, method, start_time)
        tuple already exists, update its measurements instead of creating a new
        document.
        """
        doc = interval.to_document()
        query = {
            "project_id": interval.project_id,
            "detection_method": interval.detection_method,
            "start_time": _ensure_utc(interval.start_time),
        }
        update = {"$set": doc}
        result = self.collection.update_one(query, update, upsert=True)
        return {"matched": result.matched_count, "modified": result.modified_count}

    def latest_interval(
        self, project_id: str, detection_method: Optional[str] = None
    ) -> Optional[InactivityInterval]:
        """Fetch the latest stored interval for diagnostics."""
        query: Dict[str, Any] = {"project_id": project_id}
        if detection_method:
            query["detection_method"] = detection_method
        doc = self.collection.find_one(query, sort=[("end_time", -1)])
        return InactivityInterval.from_document(doc) if doc else None


@dataclass
class UserInactivityInterval:
    """
    Represents a window of user inactivity for a given log stream.
    """

    project_id: str
    stream_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    gap_seconds: Optional[float]
    threshold_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_document(self) -> Dict[str, Any]:
        doc = asdict(self)
        doc["start_time"] = _ensure_utc(self.start_time)
        doc["end_time"] = _ensure_utc(self.end_time)
        doc["duration_seconds"] = float(self.duration_seconds)
        doc.setdefault("last_updated", datetime.now(timezone.utc))
        return doc


class UserInactivityRepository:
    """
    Stores user inactivity intervals per (project, stream).
    """

    def __init__(self, collection_name: str, *, collection=None) -> None:
        self.collection = collection or get_collection(collection_name)
        self.collection.create_index(
            [("project_id", 1), ("stream_name", 1), ("start_time", 1)],
            name="project_stream_start_idx",
            unique=True,
        )
        self.collection.create_index(
            [("end_time", -1)],
            name="stream_end_time_idx",
        )

    def save_interval(self, interval: UserInactivityInterval) -> Dict[str, Any]:
        doc = interval.to_document()
        query = {
            "project_id": interval.project_id,
            "stream_name": interval.stream_name,
            "start_time": _ensure_utc(interval.start_time),
        }
        update = {"$set": doc}
        result = self.collection.update_one(query, update, upsert=True)
        return {"matched": result.matched_count, "modified": result.modified_count}
