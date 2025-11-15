"""
Hybrid inactivity detection logic.

The detector correlates webhook/log activity with system heartbeats to
differentiate between user inactivity and infrastructure issues. It can be run
manually or scheduled via cron/k8s jobs.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import yaml
from dateutil import parser as dtparser

from inactivity_detector.ID_database import (
    InactivityInterval,
    InactivityRepository,
    UserInactivityInterval,
    UserInactivityRepository,
)
from database.mongo_client import get_collection

LOGGER = logging.getLogger(__name__)


def _ensure_utc(dt_value: datetime) -> datetime:
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=timezone.utc)
    return dt_value.astimezone(timezone.utc)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_utc(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            return _ensure_utc(dtparser.isoparse(value.strip()))
        except (ValueError, TypeError):
            pass
    return None


@dataclass
class HeartbeatConfig:
    collection: str = "system_heartbeats"
    timestamp_field: str = "timestamp"
    status_field: Optional[str] = "status"
    ok_value: Optional[str] = "alive"
    interval_seconds: int = 60
    max_missed: int = 2


@dataclass
class OutputConfig:
    base_dir: Path
    events_dir: Path
    reports_dir: Path
    enabled: bool = True

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], base_dir: Path) -> "OutputConfig":
        base = Path(raw.get("base_dir", "artifacts/inactivity_detector"))
        if not base.is_absolute():
            base = (base_dir / base).resolve()
        events = Path(raw.get("events_dir", base / "events"))
        if not events.is_absolute():
            events = (base_dir / events).resolve()
        reports = Path(raw.get("reports_dir", base / "runs"))
        if not reports.is_absolute():
            reports = (base_dir / reports).resolve()
        enabled = raw.get("enabled", True)
        return cls(base_dir=base, events_dir=events, reports_dir=reports, enabled=enabled)

    def ensure_directories(self) -> None:
        if not self.enabled:
            return
        for directory in {self.base_dir, self.events_dir, self.reports_dir}:
            directory.mkdir(parents=True, exist_ok=True)


@dataclass
class LogSourceConfig:
    name: str
    project_id: str
    source_type: str  # "file" or "mongo"
    inactivity_threshold: timedelta
    root_dir: Path
    glob_pattern: Optional[str] = None
    collection: Optional[str] = None
    timestamp_field: str = "timestamp"
    timestamp_regex: Optional[str] = None
    timestamp_format: Optional[str] = None
    timezone: str = "UTC"
    tail_lines: int = 400
    encoding: str = "utf-8"
    filters: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], base_dir: Path) -> "LogSourceConfig":
        threshold_minutes = raw.get("inactivity_threshold_minutes", 10)
        root_dir = Path(raw.get("root_dir", base_dir))
        if not root_dir.is_absolute():
            root_dir = (base_dir / root_dir).resolve()
        return cls(
            name=raw["name"],
            project_id=raw.get("project_id", raw["name"]),
            source_type=raw.get("source_type", "file"),
            inactivity_threshold=timedelta(minutes=float(threshold_minutes)),
            root_dir=root_dir,
            glob_pattern=raw.get("glob"),
            collection=raw.get("collection"),
            timestamp_field=raw.get("timestamp_field", "timestamp"),
            timestamp_regex=raw.get("timestamp_regex"),
            timestamp_format=raw.get("timestamp_format"),
            timezone=raw.get("timezone", "UTC"),
            tail_lines=raw.get("tail_lines", 400),
            encoding=raw.get("encoding", "utf-8"),
            filters=raw.get("filters", {}),
        )


@dataclass
class DetectorConfig:
    heartbeat: HeartbeatConfig
    log_sources: List[LogSourceConfig]
    outputs: OutputConfig
    inactivity_collection: str = "inactivity_intervals"
    user_inactivity_collection: str = "user_inactivity_intervals"

    @classmethod
    def from_file(cls, path: Path) -> "DetectorConfig":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_mapping(data, base_dir=Path(path).parent)

    @classmethod
    def from_mapping(cls, raw: Dict[str, Any], base_dir: Path) -> "DetectorConfig":
        section = raw.get("inactivity_detector", raw)
        heartbeat_cfg = HeartbeatConfig(
            collection=section.get("heartbeat", {}).get("collection", "system_heartbeats"),
            timestamp_field=section.get("heartbeat", {}).get("timestamp_field", "timestamp"),
            status_field=section.get("heartbeat", {}).get("status_field", "status"),
            ok_value=section.get("heartbeat", {}).get("ok_value", "alive"),
            interval_seconds=section.get("heartbeat", {}).get("interval_seconds", 60),
            max_missed=section.get("heartbeat", {}).get("max_missed", 2),
        )
        log_sources_cfg = [
            LogSourceConfig.from_raw(entry, base_dir=base_dir)
            for entry in section.get("log_sources", [])
        ]
        if not log_sources_cfg:
            raise ValueError("At least one log source must be configured.")
        outputs_cfg = OutputConfig.from_raw(section.get("outputs", {}), base_dir=base_dir)
        outputs_cfg.ensure_directories()
        persistence_cfg = section.get("persistence", {})
        downtime_collection = persistence_cfg.get(
            "downtime_collection", persistence_cfg.get("collection", "inactivity_intervals")
        )
        user_inactivity_collection = persistence_cfg.get(
            "user_inactivity_collection", f"{downtime_collection}_user"
        )
        return cls(
            heartbeat=heartbeat_cfg,
            log_sources=log_sources_cfg,
            outputs=outputs_cfg,
            inactivity_collection=downtime_collection,
            user_inactivity_collection=user_inactivity_collection,
        )


@dataclass
class HeartbeatStatus:
    last_heartbeat: Optional[datetime]
    is_stale: bool
    missed_heartbeats: int
    stale_since: datetime
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "is_stale": self.is_stale,
            "missed_heartbeats": self.missed_heartbeats,
            "stale_since": self.stale_since.isoformat(),
            "reason": self.reason,
        }


@dataclass
class LogStreamStatus:
    name: str
    project_id: str
    last_activity: Optional[datetime]
    inactivity_threshold: timedelta
    gap_seconds: Optional[float]
    is_stale: bool
    stale_since: Optional[datetime]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "project_id": self.project_id,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "gap_seconds": self.gap_seconds,
            "threshold_seconds": self.inactivity_threshold.total_seconds(),
            "is_stale": self.is_stale,
            "stale_since": self.stale_since.isoformat() if self.stale_since else None,
            "reason": self.reason,
        }


class HeartbeatMonitor:
    def __init__(
        self,
        config: HeartbeatConfig,
        collection_resolver: Callable[[str], Any] = get_collection,
    ) -> None:
        self.config = config
        self.collection = collection_resolver(config.collection)

    def evaluate(self, now: datetime) -> HeartbeatStatus:
        query = {}
        if self.config.status_field and self.config.ok_value:
            query[self.config.status_field] = self.config.ok_value
        doc = self.collection.find_one(query, sort=[(self.config.timestamp_field, -1)])
        last_seen = _parse_datetime(doc[self.config.timestamp_field]) if doc else None
        max_gap = max(1, self.config.interval_seconds) * (self.config.max_missed + 1)
        if last_seen:
            gap_seconds = (now - last_seen).total_seconds()
            missed = int(gap_seconds // max(1, self.config.interval_seconds))
            is_stale = gap_seconds >= max_gap
            stale_since = last_seen + timedelta(seconds=max_gap)
            reason = (
                f"heartbeat gap {gap_seconds:.0f}s >= {max_gap}s"
                if is_stale
                else "within expected heartbeat window"
            )
        else:
            is_stale = True
            missed = self.config.max_missed + 1
            stale_since = now - timedelta(seconds=max_gap)
            reason = "no heartbeat records found"
        return HeartbeatStatus(
            last_heartbeat=last_seen,
            is_stale=is_stale,
            missed_heartbeats=missed,
            stale_since=stale_since,
            reason=reason,
        )


class LogStreamInspector:
    def __init__(
        self,
        config: LogSourceConfig,
        collection_resolver: Callable[[str], Any] = get_collection,
    ) -> None:
        self.config = config
        self.collection_resolver = collection_resolver
        self._timestamp_pattern = (
            re.compile(config.timestamp_regex) if config.timestamp_regex else None
        )

    def evaluate(self, now: datetime) -> LogStreamStatus:
        last_activity = self._fetch_last_activity()
        if last_activity:
            gap_seconds = (now - last_activity).total_seconds()
        else:
            gap_seconds = None
        threshold_seconds = self.config.inactivity_threshold.total_seconds()
        is_stale = (
            gap_seconds is not None and gap_seconds >= threshold_seconds
        ) or last_activity is None
        if last_activity:
            stale_since = last_activity + self.config.inactivity_threshold
        else:
            stale_since = now - self.config.inactivity_threshold
        reason = (
            "no historical activity"
            if last_activity is None
            else f"gap {gap_seconds:.0f}s >= {threshold_seconds:.0f}s"
        )
        return LogStreamStatus(
            name=self.config.name,
            project_id=self.config.project_id,
            last_activity=last_activity,
            inactivity_threshold=self.config.inactivity_threshold,
            gap_seconds=gap_seconds,
            is_stale=is_stale,
            stale_since=stale_since,
            reason=reason,
        )

    def _fetch_last_activity(self) -> Optional[datetime]:
        if self.config.source_type == "file":
            return self._fetch_from_files()
        if self.config.source_type == "mongo":
            return self._fetch_from_mongo()
        raise ValueError(f"Unsupported source_type '{self.config.source_type}'")

    def _fetch_from_files(self) -> Optional[datetime]:
        if not self.config.glob_pattern:
            raise ValueError(f"Log source '{self.config.name}' missing 'glob' pattern.")
        files = sorted(
            self.config.root_dir.glob(self.config.glob_pattern),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in files:
            ts = self._scan_file(path)
            if ts:
                return ts
        return None

    def _scan_file(self, path: Path) -> Optional[datetime]:
        buffer: deque[str] = deque(maxlen=self.config.tail_lines)
        with path.open("r", encoding=self.config.encoding, errors="ignore") as handle:
            for line in handle:
                buffer.append(line.rstrip("\n"))
        for row in reversed(buffer):
            ts = self._extract_timestamp(row)
            if ts:
                return ts
        return None

    def _extract_timestamp(self, line: str) -> Optional[datetime]:
        if not line.strip():
            return None
        if self._timestamp_pattern:
            match = self._timestamp_pattern.search(line)
            if match:
                return _parse_datetime(match.group("ts") if "ts" in match.groupdict() else match.group(0))
        try:
            payload = json.loads(line)
            if isinstance(payload, dict) and self.config.timestamp_field in payload:
                return _parse_datetime(payload[self.config.timestamp_field])
        except json.JSONDecodeError:
            pass
        if self.config.timestamp_format:
            try:
                parsed = datetime.strptime(line.strip(), self.config.timestamp_format)
                return _ensure_utc(parsed)
            except ValueError:
                pass
        return _parse_datetime(line)

    def _fetch_from_mongo(self) -> Optional[datetime]:
        if not self.config.collection:
            raise ValueError(f"Log source '{self.config.name}' missing 'collection'.")
        collection = self.collection_resolver(self.config.collection)
        query = dict(self.config.filters)
        doc = collection.find_one(query, sort=[(self.config.timestamp_field, -1)])
        if not doc or self.config.timestamp_field not in doc:
            return None
        return _parse_datetime(doc[self.config.timestamp_field])


class SnapshotWriter:
    def __init__(self, config: OutputConfig) -> None:
        self.config = config
        self.config.ensure_directories()

    def append_event(self, interval: InactivityInterval) -> None:
        if not self.config.enabled:
            return
        method_dir = interval.detection_method or "unknown"
        day_dir = (
            self.config.events_dir
            / method_dir
            / interval.start_time.strftime("%Y")
            / interval.start_time.strftime("%m")
            / interval.start_time.strftime("%d")
        )
        day_dir.mkdir(parents=True, exist_ok=True)
        target = day_dir / "events.jsonl"
        payload = {
            "detection_method": interval.detection_method,
            "severity": interval.severity,
            "start_time": interval.start_time.isoformat(),
            "end_time": interval.end_time.isoformat(),
            "duration_minutes": interval.duration_minutes,
            "metadata": interval.metadata,
        }
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

    def record_run(self, summary: Dict[str, Any]) -> None:
        if not self.config.enabled:
            return
        run_dir = self.config.reports_dir / summary["run_id"]
        run_dir.mkdir(parents=True, exist_ok=True)
        with (run_dir / "summary.json").open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)


class InactivityDetector:
    def __init__(
        self,
        config: DetectorConfig,
        *,
        repository: Optional[InactivityRepository] = None,
        user_repository: Optional[UserInactivityRepository] = None,
        heartbeat_monitor: Optional[HeartbeatMonitor] = None,
        collection_resolver: Callable[[str], Any] = get_collection,
        snapshot_writer: Optional[SnapshotWriter] = None,
    ) -> None:
        self.config = config
        self.collection_resolver = collection_resolver
        self.repository = repository or InactivityRepository(config.inactivity_collection)
        self.user_repository = user_repository or UserInactivityRepository(
            config.user_inactivity_collection
        )
        self.heartbeat_monitor = heartbeat_monitor or HeartbeatMonitor(
            config.heartbeat, collection_resolver=collection_resolver
        )
        self.log_inspectors = [
            LogStreamInspector(source_cfg, collection_resolver=collection_resolver)
            for source_cfg in config.log_sources
        ]
        self.snapshot_writer = snapshot_writer or SnapshotWriter(config.outputs)

    @classmethod
    def from_file(cls, path: Path) -> "InactivityDetector":
        config = DetectorConfig.from_file(path)
        return cls(config)

    def run_once(self, now: Optional[datetime] = None, *, dry_run: bool = False) -> List[InactivityInterval]:
        now = _ensure_utc(now or datetime.now(timezone.utc))
        heartbeat_status = self.heartbeat_monitor.evaluate(now)
        stream_statuses = [inspector.evaluate(now) for inspector in self.log_inspectors]
        downtime_intervals: List[InactivityInterval] = []
        user_inactivity: List[UserInactivityInterval] = []

        interval = self._build_downtime_interval(
            heartbeat_status=heartbeat_status,
            log_statuses=stream_statuses,
            now=now,
        )
        if interval:
            downtime_intervals.append(interval)
            if not dry_run:
                self.repository.save_interval(interval)
                self.snapshot_writer.append_event(interval)

        grouped = self._group_by_project(stream_statuses)
        for statuses in grouped.values():
            for status in statuses:
                user_interval = self._build_user_inactivity_interval(status=status, now=now)
                if user_interval:
                    user_inactivity.append(user_interval)
                    if not dry_run:
                        self.user_repository.save_interval(user_interval)

        if not dry_run:
            summary = {
                "run_id": now.strftime("%Y%m%dT%H%M%SZ"),
                "evaluated_at": now.isoformat(),
                "detected_events": [self._interval_to_dict(i) for i in downtime_intervals],
                "user_inactivity_events": [self._user_interval_to_dict(i) for i in user_inactivity],
                "heartbeat": heartbeat_status.to_dict(),
                "streams": [s.to_dict() for s in stream_statuses],
            }
            self.snapshot_writer.record_run(summary)
        return downtime_intervals

    def _group_by_project(
        self, statuses: Iterable[LogStreamStatus]
    ) -> Dict[str, List[LogStreamStatus]]:
        grouped: Dict[str, List[LogStreamStatus]] = {}
        for status in statuses:
            grouped.setdefault(status.project_id, []).append(status)
        return grouped

    def _build_downtime_interval(
        self,
        heartbeat_status: HeartbeatStatus,
        log_statuses: List[LogStreamStatus],
        now: datetime,
    ) -> Optional[InactivityInterval]:
        if not heartbeat_status.is_stale:
            return None
        start_time = heartbeat_status.stale_since
        duration_minutes = max(0.0, (now - start_time).total_seconds()) / 60.0
        metadata = {
            "heartbeat": heartbeat_status.to_dict(),
            "streams": [status.to_dict() for status in log_statuses],
        }
        return InactivityInterval(
            detection_method="heartbeat",
            start_time=start_time,
            end_time=now,
            detection_source="heartbeat",
            severity="critical",
            duration_minutes=duration_minutes,
            metadata=metadata,
        )

    def _build_user_inactivity_interval(
        self,
        status: LogStreamStatus,
        now: datetime,
    ) -> Optional[UserInactivityInterval]:
        if not status.is_stale or not status.stale_since:
            return None
        start_time = status.stale_since
        duration_minutes = max(0.0, (now - start_time).total_seconds()) / 60.0
        metadata = {
            "reason": status.reason,
            "last_activity": status.last_activity.isoformat() if status.last_activity else None,
        }
        return UserInactivityInterval(
            project_id=status.project_id,
            stream_name=status.name,
            start_time=start_time,
            end_time=now,
            duration_minutes=duration_minutes,
            gap_seconds=status.gap_seconds,
            threshold_seconds=status.inactivity_threshold.total_seconds(),
            metadata=metadata,
        )

    def _interval_to_dict(self, interval: InactivityInterval) -> Dict[str, Any]:
        return {
            "detection_method": interval.detection_method,
            "severity": interval.severity,
            "start_time": interval.start_time.isoformat(),
            "end_time": interval.end_time.isoformat(),
            "duration_minutes": interval.duration_minutes,
        }

    def _user_interval_to_dict(self, interval: UserInactivityInterval) -> Dict[str, Any]:
        return {
            "project_id": interval.project_id,
            "stream_name": interval.stream_name,
            "start_time": interval.start_time.isoformat(),
            "end_time": interval.end_time.isoformat(),
            "duration_minutes": interval.duration_minutes,
            "gap_seconds": interval.gap_seconds,
            "threshold_seconds": interval.threshold_seconds,
        }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the LD inactivity detector once.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("inactivity_detector/config.yaml"),
        help="Path to the detector configuration file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate data sources without writing to Mongo or artifacts.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = _build_arg_parser().parse_args()
    detector = InactivityDetector.from_file(args.config)
    intervals = detector.run_once(dry_run=args.dry_run)
    if intervals:
        LOGGER.info("Detected %d inactivity interval(s).", len(intervals))
    else:
        LOGGER.info("No inactivity detected.")


if __name__ == "__main__":
    main()
