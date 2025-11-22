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


def _madrid_iso(value: datetime) -> str:
    """Convert to a timezone-aware ISO string in Madrid time."""
    return _ensure_madrid(value).isoformat()


def _parse_local(value: Any) -> datetime:
    """Normalize different representations into a Madrid-aware datetime."""
    if value is None:
        raise ValueError("Cannot parse null datetime value.")
    if isinstance(value, datetime):
        return _ensure_madrid(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Cannot parse empty datetime string.")
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=MADRID_TZ)
        return _ensure_madrid(parsed)
    raise TypeError(f"Unsupported datetime value {value!r}")


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
        doc["start_time"] = _madrid_iso(self.start_time)
        doc["end_time"] = _madrid_iso(self.end_time)
        doc["duration_minutes"] = float(self.duration_minutes)
        now_local = datetime.now(MADRID_TZ)
        doc.setdefault("last_updated", now_local.isoformat())
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
            start_time=_parse_local(data["start_time"]),
            end_time=_parse_local(data["end_time"]),
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
        ensure_interval_timezone_fields(self.collection)
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create/refresh indexes, dropping legacy ones when necessary."""
        info = self.collection.index_information()
        desired_primary = [("detection_method", 1), ("start_time", 1)]
        desired_secondary = [("end_time", -1)]
        existing_primary = info.get("method_start_idx")
        if existing_primary and existing_primary.get("key") != desired_primary:
            self.collection.drop_index("method_start_idx")
        existing_secondary = info.get("end_time_idx")
        if existing_secondary and existing_secondary.get("key") != desired_secondary:
            self.collection.drop_index("end_time_idx")
        self.collection.create_index(
            desired_primary,
            name="method_start_idx",
            unique=True,
        )
        self.collection.create_index(
            desired_secondary,
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
            "start_time": doc["start_time"],
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


def ensure_interval_timezone_fields(collection) -> None:
    """
    Upgrade existing inactivity interval documents so their timestamps are stored
    as Madrid-aware ISO strings.
    """
    candidates = collection.find(
        {
            "$or": [
                {"start_time_sort": {"$exists": True}},
                {"end_time_sort": {"$exists": True}},
                {"last_updated_sort": {"$exists": True}},
                {"start_time": {"$type": "date"}},
                {"end_time": {"$type": "date"}},
                {"last_updated": {"$type": "date"}},
            ]
        }
    )
    for doc in candidates:
        set_ops: Dict[str, Any] = {}
        unset_ops: Dict[str, int] = {}
        if "start_time" in doc:
            start = _parse_local(doc["start_time"])
            set_ops["start_time"] = _madrid_iso(start)
        if "start_time_sort" in doc:
            unset_ops["start_time_sort"] = ""
        if "end_time" in doc:
            end = _parse_local(doc["end_time"])
            set_ops["end_time"] = _madrid_iso(end)
        if "end_time_sort" in doc:
            unset_ops["end_time_sort"] = ""
        last_updated_value = doc.get("last_updated")
        if last_updated_value is not None:
            last_updated = _parse_local(last_updated_value)
        else:
            last_updated = datetime.now(MADRID_TZ)
        set_ops.setdefault("last_updated", _madrid_iso(last_updated))
        if "last_updated_sort" in doc:
            unset_ops["last_updated_sort"] = ""
        update_doc: Dict[str, Any] = {}
        if set_ops:
            update_doc["$set"] = set_ops
        if unset_ops:
            update_doc["$unset"] = unset_ops
        if update_doc:
            collection.update_one({"_id": doc["_id"]}, update_doc)
