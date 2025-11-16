"""
Persistence helpers for the Inactivity Detector.

The repository wraps MongoDB collections so the detector can focus on business
logic. All datetimes are normalized to UTC before storage to simplify queries.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from database.mongo_client import get_collection

MADRID_TZ = ZoneInfo("Europe/Madrid")

def _ensure_madrid(value: datetime) -> datetime:
    """Normalize datetimes to Europe/Madrid with tz info."""
    if value.tzinfo is None:
        return value.replace(tzinfo=MADRID_TZ)
    return value.astimezone(MADRID_TZ)


def _madrid_naive(value: datetime) -> datetime:
    """Convert to Madrid time and drop tzinfo for storage (keeps local wall time)."""
    return _ensure_madrid(value).replace(tzinfo=None)


@dataclass
class InactivityInterval:
    """
    Represents a detected system inactivity interval driven by heartbeats.
    """

    detection_method: str  # log | heartbeat | hybrid
    start_time: datetime
    end_time: datetime
    detection_source: str
    severity: str
    duration_minutes: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    project_id: Optional[str] = None

    def to_document(self) -> Dict[str, Any]:
        """Serialize the dataclass to a Mongo-friendly dict."""
        doc = asdict(self)
        doc["start_time"] = _madrid_naive(self.start_time)
        doc["end_time"] = _madrid_naive(self.end_time)
        doc["duration_minutes"] = float(self.duration_minutes)
        doc.setdefault("last_updated", datetime.now(MADRID_TZ).replace(tzinfo=None))
        if self.project_id is None:
            doc.pop("project_id", None)
        return doc

    @classmethod
    def from_document(cls, data: Dict[str, Any]) -> "InactivityInterval":
        """Create an interval from a Mongo document."""
        if "duration_minutes" in data:
            duration_minutes = float(data.get("duration_minutes", 0.0))
        elif "duration_seconds" in data:
            duration_minutes = float(data.get("duration_seconds", 0.0)) / 60.0
        else:
            duration_minutes = 0.0
        return cls(
            detection_method=data["detection_method"],
            start_time=_ensure_madrid(data["start_time"]),
            end_time=_ensure_madrid(data["end_time"]),
            detection_source=data.get("detection_source", data["detection_method"]),
            severity=data.get("severity", "warning"),
            duration_minutes=duration_minutes,
            metadata=data.get("metadata", {}),
            project_id=data.get("project_id"),
        )


class InactivityRepository:
    """
    Thin wrapper around the Mongo collection used for inactivity events.
    """

    def __init__(self, collection_name: str, *, collection=None) -> None:
        self.collection = collection or get_collection(collection_name)
        # Index to keep queries deterministic when upserting.
        self.collection.create_index(
            [("detection_method", 1), ("start_time", 1)],
            name="method_start_idx",
            unique=True,
        )
        self.collection.create_index(
            [("end_time", -1)],
            name="end_time_idx",
        )

    def save_interval(self, interval: InactivityInterval) -> Dict[str, Any]:
        """
        Upsert an inactivity interval. If the same (method, start_time) tuple
        already exists, update its measurements instead of creating a new
        document. Legacy records that carry a project_id are still supported.
        """
        doc = interval.to_document()
        query = {
            "detection_method": interval.detection_method,
            "start_time": _madrid_naive(interval.start_time),
        }
        if interval.project_id is not None:
            query["project_id"] = interval.project_id
        update = {"$set": doc}
        result = self.collection.update_one(query, update, upsert=True)
        return {"matched": result.matched_count, "modified": result.modified_count}

    def latest_interval(
        self, detection_method: Optional[str] = None
    ) -> Optional[InactivityInterval]:
        """Fetch the latest stored interval for diagnostics."""
        query: Dict[str, Any] = {}
        if detection_method is not None:
            query["detection_method"] = detection_method
        doc = self.collection.find_one(query, sort=[("end_time", -1)])
        return InactivityInterval.from_document(doc) if doc else None
