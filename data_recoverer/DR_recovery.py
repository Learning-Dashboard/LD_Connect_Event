"""
Recovery orchestrator that ties inactivity intervals to API fetchers and
persists the recovered data using the same Mongo collections as the
live ingestion pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

import yaml
from pymongo import UpdateOne

from database.mongo_client import get_collection
from data_recoverer.DR_api import GitHubAPIClient, RecoveryBatch, TaigaAPIClient
from data_recoverer.DR_error_control import RecoveryErrorTracker
from inactivity_detector.ID_database import InactivityInterval, ensure_interval_timezone_fields

MADRID_TZ = ZoneInfo("Europe/Madrid")
LOGGER = logging.getLogger(__name__)


def _local_aware(dt_value: datetime) -> datetime:
    """Align datetimes to Madrid tz and keep tzinfo."""
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=MADRID_TZ)
    return dt_value.astimezone(MADRID_TZ)


def _local_iso(dt_value: datetime) -> str:
    return _local_aware(dt_value).isoformat()


def _parse_local(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _local_aware(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        cleaned = cleaned.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            return None
        return _local_aware(parsed)
    return None


@dataclass
class GitHubProjectConfig:
    repositories: List[str] = field(default_factory=list)
    events: List[str] = field(default_factory=lambda: ["commits", "issues", "pull_requests"])


@dataclass
class TaigaProjectConfig:
    slug: Optional[str] = None
    project_id: Optional[int] = None
    events: List[str] = field(default_factory=lambda: ["tasks", "issues", "userstories", "epics"])


@dataclass
class ProjectConfig:
    project_id: str
    github: Optional[GitHubProjectConfig] = None
    taiga: Optional[TaigaProjectConfig] = None


@dataclass
class StartupRunConfig:
    enabled: bool = False
    since_hours: Optional[float] = None
    limit: Optional[int] = None
    dry_run: bool = False

    def resolve_since(self, *, now: Optional[datetime] = None) -> Optional[datetime]:
        if self.since_hours is None:
            return None
        current = now or datetime.now(MADRID_TZ)
        delta = timedelta(hours=float(self.since_hours))
        return current - delta


@dataclass
class RecoveryConfig:
    inactivity_collection: str = "inactivity_intervals"
    run_log_collection: str = "data_recovery_runs"
    projects: List[ProjectConfig] = field(default_factory=list)
    startup_run: StartupRunConfig = field(default_factory=StartupRunConfig)

    @classmethod
    def from_file(cls, path: Path) -> "RecoveryConfig":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "RecoveryConfig":
        section = data.get("data_recoverer", data)
        projects: List[ProjectConfig] = []
        for entry in section.get("projects", []):
            github_cfg = None
            taiga_cfg = None
            if "github" in entry:
                gh = entry["github"]
                github_cfg = GitHubProjectConfig(
                    repositories=gh.get("repositories", []),
                    events=gh.get("events", ["commits", "issues", "pull_requests"]),
                )
            if "taiga" in entry:
                tg = entry["taiga"]
                taiga_cfg = TaigaProjectConfig(
                    slug=tg.get("slug"),
                    project_id=tg.get("project_id"),
                    events=tg.get("events", ["tasks", "issues", "userstories", "epics"]),
                )
            projects.append(
                ProjectConfig(
                    project_id=entry["project_id"],
                    github=github_cfg,
                    taiga=taiga_cfg,
                )
            )
        startup_section = section.get("startup_run", {})
        startup_cfg = StartupRunConfig(
            enabled=startup_section.get("enabled", False),
            since_hours=startup_section.get("since_hours"),
            limit=startup_section.get("limit"),
            dry_run=startup_section.get("dry_run", False),
        )
        return cls(
            inactivity_collection=section.get("inactivity_collection", "inactivity_intervals"),
            run_log_collection=section.get("run_log_collection", "data_recovery_runs"),
            projects=projects,
            startup_run=startup_cfg,
        )

    @property
    def project_map(self) -> Dict[str, ProjectConfig]:
        return {p.project_id: p for p in self.projects}


class DataRecoverer:
    """
    Coordinates recovery runs: fetches inactivity intervals, queries APIs,
    persists recovered documents, and logs the run outcome.
    """

    def __init__(
        self,
        config: RecoveryConfig,
        *,
        github_client: Optional[GitHubAPIClient] = None,
        taiga_client: Optional[TaigaAPIClient] = None,
        error_tracker: Optional[RecoveryErrorTracker] = None,
        collection_resolver: Callable[[str], Any] = get_collection,
    ) -> None:
        self.config = config
        self.github_client = github_client or GitHubAPIClient()
        self.taiga_client = taiga_client or TaigaAPIClient()
        self.error_tracker = error_tracker or RecoveryErrorTracker()
        self.collection_resolver = collection_resolver
        self.inactivity_collection = collection_resolver(config.inactivity_collection)
        ensure_interval_timezone_fields(self.inactivity_collection)
        self.run_log = collection_resolver(config.run_log_collection)

    @classmethod
    def from_file(cls, path: Path) -> "DataRecoverer":
        cfg = RecoveryConfig.from_file(path)
        return cls(cfg)

    def run_once(
        self,
        *,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        intervals = self._load_intervals(since=since, limit=limit)
        summary = {"processed_intervals": 0, "batches": 0, "documents": 0}
        for interval in intervals:
            try:
                batch_count, doc_count = self._recover_interval(interval, dry_run=dry_run)
                summary["processed_intervals"] += 1
                summary["batches"] += batch_count
                summary["documents"] += doc_count
            except Exception as exc:  # pragma: no cover - defensive logging
                project_ids = self._project_ids_for_interval(interval)
                self.error_tracker.record_failure(interval, "recovery", exc)
                if not dry_run:
                    self._record_run(interval, project_ids, [], status="failed")
        return summary

    def recover_manual_range(
        self,
        *,
        start: datetime,
        end: datetime,
        projects: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Manually trigger recovery for a specific time range, bypassing the
        inactivity detector's intervals.
        """
        start = _local_aware(start)
        end = _local_aware(end)
        
        # Create a synthetic interval for this manual run
        # We use a special detection_method to distinguish it in logs
        metadata = {}
        if projects:
            # If specific projects are requested, we can hint them in metadata
            # though _project_ids_for_interval will need to handle this or we override it.
            # For now, let's just rely on the fact that if projects is None, it does all.
            # If projects is set, we might need to filter inside _recover_interval or 
            # create a metadata structure that _project_ids_for_interval understands.
            # Let's stick to the simplest approach: if projects is passed, we construct
            # a metadata that looks like what _project_ids_for_interval expects.
            streams = [{"project_id": pid} for pid in projects]
            metadata["streams"] = streams

        interval = InactivityInterval(
            detection_method="manual_api",
            start_time=start,
            end_time=end,
            detection_source="manual",
            severity="manual",
            duration_minutes=(end - start).total_seconds() / 60.0,
            metadata=metadata,
        )

        summary = {"processed_intervals": 0, "batches": 0, "documents": 0}
        try:
            batch_count, doc_count = self._recover_interval(interval, dry_run=dry_run)
            summary["processed_intervals"] = 1
            summary["batches"] = batch_count
            summary["documents"] = doc_count
        except Exception as exc:
            project_ids = self._project_ids_for_interval(interval)
            self.error_tracker.record_failure(interval, "manual_recovery", exc)
            if not dry_run:
                self._record_run(interval, project_ids, [], status="failed")
            raise exc  # Re-raise for API feedback
            
        return summary

    def _load_intervals(
        self,
        *,
        since: Optional[datetime],
        limit: Optional[int],
    ) -> List[InactivityInterval]:
        query: Dict[str, Any] = {}
        if since:
            query["start_time"] = {"$gte": _local_iso(since)}
        cursor = self.inactivity_collection.find(query).sort("start_time", 1)
        if limit:
            cursor = cursor.limit(limit)
        intervals: List[InactivityInterval] = []
        for doc in cursor:
            interval = InactivityInterval.from_document(doc)
            if self._already_processed(interval):
                continue
            intervals.append(interval)
        return intervals

    def _already_processed(self, interval: InactivityInterval) -> bool:
        query = {
            "interval_start": _local_iso(interval.start_time),
            "interval_end": _local_iso(interval.end_time),
            "status": "success",
        }
        return bool(self.run_log.find_one(query))

    def _recover_interval(self, interval: InactivityInterval, *, dry_run: bool) -> tuple[int, int]:
        project_ids = self._project_ids_for_interval(interval)
        start_bound, end_bound = self._interval_bounds(interval)
        batches: List[RecoveryBatch] = []
        for pid in project_ids:
            project_cfg = self.config.project_map.get(pid)
            if not project_cfg:
                LOGGER.info("Skipping recovery for project %s (not configured).", pid)
                continue
            if project_cfg.github:
                gh_batches = self.github_client.collect_batches(
                    prj=pid,
                    repositories=project_cfg.github.repositories,
                    since=start_bound,
                    until=end_bound,
                    event_types=project_cfg.github.events,
                )
                batches.extend(gh_batches)
            if project_cfg.taiga:
                tg_batches = self.taiga_client.collect_batches(
                    prj=pid,
                    project_slug=project_cfg.taiga.slug,
                    project_id=project_cfg.taiga.project_id,
                    since=start_bound,
                    until=end_bound,
                    event_types=project_cfg.taiga.events,
                )
                batches.extend(tg_batches)

        inserted_docs = 0
        if not dry_run:
            for batch in batches:
                inserted_docs += self._persist_batch(batch)
            self._record_run(interval, project_ids, batches, status="success")
        return len(batches), inserted_docs

    def _persist_batch(self, batch: RecoveryBatch) -> int:
        coll = self.collection_resolver(batch.collection)
        operations = []
        for doc in batch.documents:
            key_value = doc.get(batch.key_field)
            if key_value is None:
                continue
            operations.append(UpdateOne({batch.key_field: key_value}, {"$set": doc}, upsert=True))
        if not operations:
            return 0
        try:
            res = coll.bulk_write(operations, ordered=False)
            return res.matched_count + len(res.upserted_ids)
        except TypeError:
            # mongomock compatibility: some versions do not accept all bulk args
            inserted = 0
            for op in operations:
                coll.update_one(op._filter, op._doc, upsert=True)
                inserted += 1
            return inserted

    def _record_run(
        self,
        interval: InactivityInterval,
        project_ids: Iterable[str],
        batches: List[RecoveryBatch],
        *,
        status: str,
    ) -> None:
        recorded_local = datetime.now(MADRID_TZ)
        doc = {
            "interval_start": _local_iso(interval.start_time),
            "interval_end": _local_iso(interval.end_time),
            "detection_method": interval.detection_method,
            "project_ids": list(project_ids),
            "batches": [b.collection for b in batches],
            "status": status,
            "recorded_at": _local_iso(recorded_local),
        }
        self.run_log.insert_one(doc)

    def _project_ids_for_interval(self, interval: InactivityInterval) -> List[str]:
        metadata = interval.metadata or {}
        projects = {stream.get("project_id") for stream in metadata.get("streams", []) if stream.get("project_id")}
        if projects:
            return list(projects)
        if self.config.projects:
            return [p.project_id for p in self.config.projects]
        return []

    def _heartbeat_last_seen(self, interval: InactivityInterval) -> Optional[datetime]:
        heartbeat_meta = (interval.metadata or {}).get("heartbeat") or {}
        last_seen = heartbeat_meta.get("last_heartbeat")
        return _parse_local(last_seen)

    def _interval_bounds(self, interval: InactivityInterval) -> tuple[datetime, datetime]:
        start = interval.start_time
        last_seen = self._heartbeat_last_seen(interval)
        if last_seen and last_seen < start:
            LOGGER.debug(
                "Extending recovery window back to last heartbeat %s from %s.",
                last_seen,
                start,
            )
            start = last_seen
        return start, interval.end_time
