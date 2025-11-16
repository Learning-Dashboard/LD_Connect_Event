# Inactivity Detector (ID)

## Overview
The **Inactivity Detector (ID)** identifies periods during which the Learning Dashboard (LD) was inactive or unable to collect data.  
It ensures that subsequent components (data recovery and metric recalculation) operate only on verified missing periods.

This module now relies solely on heartbeats to detect platform downtime. Log streams are optional and only used as context in metadata; no user inactivity windows are produced.

---

## Subcomponents

### ID1 - Inactivity Detection Logic
**Objective:** Implement robust logic to detect downtime periods with heartbeats. Log streams can be inspected for context, but no user inactivity windows are emitted.

**Tasks:**
- Parse system heartbeats and timestamps.
- Detect genuine system downtime (heartbeat gaps).
- Optionally attach log stream status as metadata for diagnostics.

**Inputs:**
- System heartbeats emitted by the service itself.
- (Optional) Log files or collections from `LD_CONNECT` to provide context.
- Database timestamps of last successfully stored events.

**Outputs:**
- Heartbeat-driven downtime intervals (start/end time, duration, metadata with optional log context).

---

### Detection Approach

| Component | Purpose | What It Detects | Stored In |
|------------|----------|----------------|-----------|
| Heartbeat Monitoring | Periodically emitted `alive` documents that reflect LD_CONNECT's own health. | Platform downtime (critical). | `persistence.downtime_collection` |

**How It Works:**
- The heartbeat gap is evaluated. When the gap exceeds `(interval_seconds * (max_missed + 1))`, the detector records a downtime interval (severity `critical`). Log streams, if configured, are attached as metadata so recovery jobs can understand what data might have been missed.
- Because LD_CONNECT writes the heartbeat events, the downtime interval clearly marks windows where events could not be collected. A future module can replay those windows against external APIs to backfill data.

**Implementation Notes:**
- Heartbeat documents live in MongoDB (local database on port 27017, credentials in `.env`) and must carry `ok_value` (default `alive`) while healthy.
- Log thresholds should reflect instructional expectations (possibly days/weeks) rather than infrastructure assumptions.
- `config.yaml` separates persistence into `downtime_collection` (heartbeat outages) and `user_inactivity_collection` (per-stream informational intervals).

---

### ID2 - Database Integration
**Objective:** Persist heartbeat downtime intervals with dedicated indexes.

**Tasks:**
- Create or extend the downtime collection (`downtime_collection`).
- Store `start_time`, `end_time`, `duration`, `detection_method`, and metadata.
- Guarantee atomic writes when updating.

---

### ID3 - Unit Testing
**Objective:** Validate heartbeat-only downtime detection and persistence.

**Tasks:**
- Mock heartbeat signals and database states with known inactivity patterns.
- Verify that heartbeats solely control downtime intervals.
- Test edge cases: short heartbeat delays, corrupted logs, intermittent network issues, and empty streams (if present for metadata).

**Dependencies:** `ID2`.

**Tools:** `pytest`, `unittest`, `mock`, CI integration.

---

## Expected Deliverables
- `ID_detector.py`: Heartbeat-driven downtime detection with optional log context.
- `ID_database.py`: Persistence logic for downtime collection.
- `test_ID.py`: Unit and integration tests covering heartbeat-driven detection.
- `config.yaml`: Detection thresholds, persistence targets, and system parameters.

---

## Summary
The refreshed inactivity detector ensures:
- **Authoritative downtime detection** by trusting heartbeats only.
- **Simple context** by optionally attaching log stream status as metadata, without emitting separate user inactivity intervals.
- **Scalability** for additional sources while keeping the core detection simple.

## Runtime Integration
- Run `python app.py` (or your WSGI server) to serve LD_CONNECT and emit heartbeats from the ingestion process itself.
- Run `python -m inactivity_detector.runner_main` as a separate worker to keep evaluating heartbeats/log sources even if the app is rebooting. This command respects `INACTIVITY_DETECTOR_CONFIG` and `INACTIVITY_DETECTOR_INTERVAL_SECONDS`.
- The heartbeat emitter can be disabled with `ENABLE_HEARTBEATS=false`; detector cadence can be overridden with `HEARTBEAT_INTERVAL_SECONDS` (emitter) and `INACTIVITY_DETECTOR_INTERVAL_SECONDS` (worker).
- Supervisors (systemd, Docker Compose, Kubernetes) should manage both commands so they restart automatically and no manual intervention is required.

This design cleanly separates infrastructure health from student workflow analytics, making both easier to reason about.
