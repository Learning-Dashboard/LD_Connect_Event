# Inactivity Detector (Current Branch)

This branch packages the heartbeat‑driven downtime detector plus the user
inactivity logic. By default, both the heartbeat emitter and the inactivity
detector start inside the LD_CONNECT app process (the detector runs in a
background thread guarded against Flask's reloader). An optional standalone
worker entrypoint (`python -m inactivity_detector.runner_main`) remains available
for deployments that prefer process isolation, but it is no longer required.

The log/user inactivity logic still exists in the codebase, but this branch only
documents the heartbeat flow described below.

---

## Architecture

| Component | Location | Responsibility |
| --- | --- | --- |
| Heartbeat emitter | `utils/heartbeat_emitter.py` (started by `app.py`) | Insert `{status:"alive"}` documents in Mongo on a fixed cadence. |
| Startup delay guard | Same emitter | Optional initial delay (`startup_delay_seconds`) so the detector records downtime before the first post‑crash heartbeat. |
| Detector runner | `inactivity_detector/runner.py` (+ optional `runner_main.py`) | Executes `InactivityDetector.run_once()` on a cadence, evaluating heartbeats and configured log sources. |
| Log harvesters | `inactivity_detector/ID_detector.py` (`LogSourceConfig`, `LogStreamStatus`) | Tail file/mongo sources and measure per‑stream inactivity versus thresholds. |
| Persistence helpers | `inactivity_detector/ID_database.py` | Serialize downtime intervals (`InactivityInterval`) and per-stream inactivity windows (`UserInactivityInterval`). |
| Configuration | `inactivity_detector/config.yaml` | Heartbeat cadence, startup delay, log sources, persistence targets. |

---

## Configuration

`inactivity_detector/config.yaml` controls both services. Key keys inside the
`heartbeat:` section:

- `interval_seconds`: heartbeat period (defaults to 60 s). Must stay aligned with
  `HEARTBEAT_INTERVAL_SECONDS` if overridden via env.
- `startup_delay_seconds`: initial delay before the first heartbeat after startup.
  Set this to a value ≥ detector cadence to let the worker detect cold‑boot
  downtime before the gap is reset.
- `max_missed`: detector tolerance. Downtime is recorded when the heartbeat gap
  exceeds `(interval_seconds * (max_missed + 1))`.

Environment overrides (read inside `app.py` and `runner_main.py`):

- `HEARTBEAT_INTERVAL_SECONDS`, `HEARTBEAT_STARTUP_DELAY_SECONDS`
- `INACTIVITY_DETECTOR_INTERVAL_SECONDS`
- `INACTIVITY_DETECTOR_CONFIG`
- `ENABLE_HEARTBEATS` (disable emitter for tests)

---

## Runtime Instructions

1. **Start LD_CONNECT** (heartbeats + detector):
   ```bash
   python app.py
   ```
   This spins up Flask, the heartbeat emitter (with optional startup delay), and
   the inactivity detector background runner in the same process. The runner
   only starts inside the serving process (never the Flask reloader parent).

2. **Optional:** run the detector worker as its own process:
   ```bash
   python -m inactivity_detector.runner_main --config inactivity_detector/config.yaml
   ```
   Use this when you want the detector decoupled from LD_CONNECT. Do **not** run
   the standalone worker at the same time as the in‑app runner unless you set
   `ENABLE_INACTIVITY_DETECTOR=false` to avoid duplicate intervals.

3. **Configure startup delay** (optional but recommended for cold‑boot recovery):
   set `HEARTBEAT_STARTUP_DELAY_SECONDS=120` (or edit `startup_delay_seconds` in
   YAML). The app becomes available immediately; only the first heartbeat waits.

Supervisors should run both commands as separate processes so a crash in one
does not take down the other. On host‑wide restarts, keep the detector process
in the same unit file / Compose stack so it restarts automatically.

---

## Testing Scenarios

1. **Healthy loop**: run both services with `startup_delay_seconds=0`. Confirm
   heartbeats land every `interval_seconds` and no downtime intervals are stored.

2. **Cold boot detection**: stop `python app.py` long enough to exceed
   `(interval_seconds * (max_missed + 1))`, then start it again with
   `startup_delay_seconds >= detector cadence`. The detector thread should log a
   stale heartbeat and store a downtime interval before the emitter’s first
   `"alive"` document. (If you prefer the standalone worker, start it first,
   then launch the app after the delay.)

3. **Quick restart**: restart the app quickly (downtime shorter than the
   threshold). The detector observes the short gap and does not write an
   interval, confirming that normal redeploys don’t create false positives.

4. **Emitter disabled**: set `ENABLE_HEARTBEATS=false` and start the app. The
   detector runs but no heartbeats arrive, so it records continuous downtime—
   useful for exercising alerting/monitoring pipelines.
   alerting/monitoring pipelines.

5. **User inactivity**: populate sample GitHub/Taiga logs (see `routes/*` or
   tests) so the detector stores `UserInactivityInterval` records whenever a
   stream exceeds its `inactivity_threshold_minutes`. This proves log-side logic
   is still active alongside heartbeat monitoring.

---

## Operations Notes

- Mongo collections (`system_heartbeats`, `inactivity_intervals`, etc.) are
  defined via `config.yaml`. Ensure the same database is reachable by both
  processes.
- The detector runner writes run summaries under
  `inactivity_detector/artifacts/.../summary.json` when persistence is enabled,
  useful for troubleshooting.
- Startup delay only affects the first heartbeat after process start; webhook
  ingestion is never blocked.
- For machine‑wide crashes, the detector can only record downtime once both the
  database and detector thread/process are back online. The delayed heartbeat
  ensures the gap is still visible when that happens.

This documentation reflects the current branch’s behavior; other branches that
experiment with different inactivity logic (e.g., legacy background workers or
alternate detectors) are documented separately.***
