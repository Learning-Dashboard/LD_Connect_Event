## Inactivity Detector – User Guide

### What It Does
- Detects platform downtime using heartbeats only.
- Optional log sources add context in metadata; no user inactivity intervals are stored.

### Configure
- Edit `inactivity_detector/config.yaml`:
  - `heartbeat`: Mongo collection and fields (`collection`, `timestamp_field`, `status_field`, `ok_value`, `interval_seconds`, `max_missed`).
  - `log_sources` (optional): one per collection to include context. Set `name`, `project_id`, `source_type: mongo`, `collection`, `timestamp_field` (dot paths OK, e.g., `issue.created_at`), `inactivity_threshold_minutes`, and optional `filters`.
  - `outputs`: artifact locations; `enabled: true` writes JSONL/JSON snapshots under `base_dir/events` and `base_dir/runs`.
  - `persistence.downtime_collection`: Mongo collection for downtime intervals.

### Run Once
- From repo root: `python -m inactivity_detector.ID_detector --config inactivity_detector/config.yaml`
- Optional flag: `--dry-run` skips writes (logs to stdout only).

### What Gets Stored
- Mongo (downtime collection): one doc per heartbeat outage with `detection_method: "heartbeat"`, `start_time`, `end_time`, `duration_minutes`, `severity`, and `metadata` (heartbeat status + per-stream status if log sources are configured).
- Artifacts (if enabled): `events/<method>/YYYY/MM/DD/events.jsonl` and `runs/<run_id>/summary.json`.

### Interpreting Metadata
- `metadata.streams[*]` (context only): `last_activity`, `gap_minutes`, `threshold_minutes`, `is_stale`, `stale_since` (null when healthy), `reason` (“stream healthy”, “no historical activity”, or gap message).

### Healthy vs Stale Streams
- Healthy: `is_stale=false`, `stale_since=null`, `gap_minutes` ≥ 0, `reason="stream healthy"`.
- Stale: missing history or gap ≥ threshold; shows `stale_since` and a gap/no-history reason.

### Common Adjustments
- “No historical activity”: verify `collection`/`filters` and `timestamp_field` (use nested path if needed, e.g., `pull_request.created_at`).
- No log context needed: remove `log_sources`; heartbeats still drive detection.

### Files to Know
- Detector logic: `inactivity_detector/ID_detector.py`
- Persistence model: `inactivity_detector/ID_database.py`
- Config: `inactivity_detector/config.yaml`

### Typical Workflow
1) Configure heartbeats (and optional log sources).
2) Run detector (manual, cron, or scheduler).
3) Inspect Mongo downtime collection and/or artifacts for outages and stream context.
4) Adjust thresholds/collections/paths if metadata shows missing history or incorrect gaps.
