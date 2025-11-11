# Inactivity Detector (ID)

## Overview
The **Inactivity Detector (ID)** identifies periods during which the Learning Dashboard (LD) was inactive or unable to collect data.  
It ensures that subsequent components (data recovery and metric recalculation) operate only on verified missing periods.

This module continuously analyzes heartbeats to detect platform downtime and inspects event streams (GitHub/Taiga) to capture user inactivity trends. Heartbeats are the source of truth for downtime, while log-derived windows are informational so professors can evaluate how teams distribute their effort.

---

## Subcomponents

### ID1 - Inactivity Detection Logic
**Objective:** Implement robust logic to detect downtime periods with heartbeats and capture log-based user inactivity windows for later pedagogical analysis.

**Tasks:**
- Parse system logs and timestamps.
- Differentiate between genuine system downtime (heartbeat gaps) and periods of normal user inactivity (per log source).
- Integrate heartbeat monitoring to verify system-level availability.

**Inputs:**
- Log files from the main data collector service `LD_CONNECT` (check github_routes.py and taiga_routes.py to know which events are collected).
- System heartbeats emitted by the service itself.
- Database timestamps of last successfully stored events.

**Outputs:**
- Heartbeat-driven downtime intervals (start/end time, duration, metadata with log context).
- Per-stream user inactivity intervals to characterize GitHub/Taiga usage patterns.

---

### Detection Approaches

| Component | Purpose | What It Detects | Stored In |
|------------|----------|----------------|-----------|
| Heartbeat Monitoring | Periodically emitted `alive` documents that reflect LD_CONNECT's own health. | Platform downtime (critical). | `persistence.downtime_collection` |
| Log-based Analysis | GitHub/Taiga activity streams with configurable thresholds. | Student/user inactivity per source (informational). | `persistence.user_inactivity_collection` |

**How It Works:**
- The heartbeat gap is evaluated first. When the gap exceeds `(interval_seconds * (max_missed + 1))`, the detector records a downtime interval for every configured project with severity `critical`. Log streams are attached as metadata so recovery jobs can understand what data was missing when the platform was down.
- Every log source is evaluated independently. If a stream has no history or the last event exceeds its `inactivity_threshold_minutes`, the detector stores a user inactivity interval for that `(project, stream)` pair. These intervals never flip the system into a "down" state; they simply describe how students distributed their effort.
- Because LD_CONNECT writes both the heartbeat and the GitHub/Taiga events, the downtime interval clearly marks windows where events could not be collected. A future module can replay those windows against external APIs to backfill data.

**Implementation Notes:**
- Heartbeat documents live in MongoDB (local database on port 27017, credentials in `.env`) and must carry `ok_value` (default `alive`) while healthy.
- Log thresholds should reflect instructional expectations (possibly days/weeks) rather than infrastructure assumptions.
- `config.yaml` separates persistence into `downtime_collection` (heartbeat outages) and `user_inactivity_collection` (per-stream informational intervals).

---

### ID2 - Database Integration
**Objective:** Persist heartbeat downtime intervals and user inactivity windows with dedicated indexes.

**Tasks:**
- Create or extend collections for downtime (`downtime_collection`) and user inactivity (`user_inactivity_collection`).
- Store `start_time`, `end_time`, `duration`, `detection_method/stream_name`, and metadata in each collection.
- Guarantee atomic writes when updating.

**Dependencies:** `ID1`.

**Implementation:**
1. **Direct Mongo Integration:** Insert downtime intervals and user inactivity windows into their respective Mongo collections.

---

### ID3 - Unit Testing
**Objective:** Validate heartbeat-only downtime detection while still capturing user inactivity windows and ensuring persistence.

**Tasks:**
- Mock logs, heartbeat signals, and database states with known inactivity patterns.
- Verify that heartbeats solely control downtime intervals while log thresholds populate the user inactivity collection.
- Test edge cases: short heartbeat delays, overlapping log gaps, corrupted logs, intermittent network issues, and empty streams.

**Dependencies:** `ID2`.

**Tools:** `pytest`, `unittest`, `mock`, CI integration.

---

## Expected Deliverables
- `ID_detector.py`: Heartbeat-driven downtime detection plus per-stream user inactivity tracking.
- `ID_database.py`: Persistence logic for downtime and user inactivity collections.
- `test_ID.py`: Unit and integration tests covering both behaviors.
- `config.yaml`: Detection thresholds, persistence targets, and system parameters.

---

## Summary
The refreshed inactivity detector ensures:
- **Authoritative downtime detection** by trusting heartbeats only.
- **Actionable context** through user inactivity windows without risking false downtime alerts.
- **Scalability** for additional sources (GitHub, Taiga, etc.) with dedicated persistence.

## Runtime Integration
- Run `python app.py` (or your WSGI server) to serve LD_CONNECT and emit heartbeats from the ingestion process itself.
- Run `python -m inactivity_detector.runner_main` as a separate worker to keep evaluating heartbeats/log sources even if the app is rebooting. This command respects `INACTIVITY_DETECTOR_CONFIG` and `INACTIVITY_DETECTOR_INTERVAL_SECONDS`.
- The heartbeat emitter can be disabled with `ENABLE_HEARTBEATS=false`; detector cadence can be overridden with `HEARTBEAT_INTERVAL_SECONDS` (emitter) and `INACTIVITY_DETECTOR_INTERVAL_SECONDS` (worker).
- Supervisors (systemd, Docker Compose, Kubernetes) should manage both commands so they restart automatically and no manual intervention is required.

This design cleanly separates infrastructure health from student workflow analytics, making both easier to reason about.
