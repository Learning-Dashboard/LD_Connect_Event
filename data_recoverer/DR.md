# Data Recovery from APIs (DR)

## Overview
The **Data Recovery (DR)** module retrieves missing information from external platforms (e.g., GitHub and Taiga) corresponding to downtime intervals identified by the Inactivity Detector. It ensures completeness of historical data by making retrospective API calls and handling errors robustly.

When the recoverer processes an inactivity interval it automatically
extends the query window to the detector’s recorded `metadata.heartbeat.last_heartbeat`.
That means every run covers the entire period since the last known heartbeat
through the interval’s `end_time`, so spikes that happened right before the
detector declared downtime are still recovered.

---

## Subcomponents

### DR1 - API Analysis
**Objective:** Understand and document the API endpoints required for recovery.

**Tasks:**
- Review GitHub and Taiga API documentation.
- Identify endpoints supporting time-based queries.
- Determine authentication methods and rate limits.

**Dependencies:** `ID` (Inactivity Detector output).

**Implementation Notes:**
- GitHub: Use `commits`, `issues`, `events` endpoints filtered by timestamp.
- Taiga: Use `userstories`, `tasks`, `issues`, `epics` endpoints with date filters.
- Store credentials securely using `.env` or a key management system.

---

### DR2 - Retrospective Data Retrieval
**Objective:** Query past data from APIs to fill inactivity gaps.

**Tasks:**
- For each inactivity interval, request data using time filters.
- Reconstruct historical data for missing periods.
- Format and normalize the responses to match the internal schema.

**Dependencies:** `DR1`.

**Implementation Options:**
1. **Sequential Pull:** Iterate intervals and APIs sequentially.
   - Simpler but slower. Avoids rate limits

---

### DR3 - Error Control
**Objective:** Implement robust error handling and retry logic.

**Tasks:**
- Manage HTTP errors, timeouts, and API quota limits.
- Implement exponential backoff and logging for failed requests.
- Track failed intervals for manual reprocessing.

**Dependencies:** `DR2`.

**Approaches:**
1. **Retry with Backoff:** Use libraries like `tenacity` or custom retry logic.
2. **Fallback Mechanism:** Cache failed requests for later batch retry.
3. **Adaptive Scheduling:** Dynamically adjust rate limits based on API response headers.

---

### DR4 - Unit Testing
**Objective:** Validate API communication and recovery accuracy.

**Tasks:**
- Mock API responses with missing and complete data.
- Test recovery logic with varying downtime intervals.
- Verify resilience under simulated API errors.

**Dependencies:** `DR3`.

**Tools:** `pytest`, `requests-mock`, `vcrpy`.

---

## Expected Deliverables
- `DR_api.py`: API handling logic.
- `DR_recovery.py`: Retrospective retrieval implementation.
- `DR_error_control.py`: Error and retry logic.
- `test_DR.py`: Unit tests.
- `api_docs.md`: Summarized API endpoints and parameters.

---

## Hybrid Execution
Configure `data_recoverer/config.yaml` to control whether the recoverer
runs automatically when LD Connect boots or stays manual:

```yaml
data_recoverer:
  startup_run:
    enabled: true        # run automatically on startup (false = manual only)
    since_hours: 24      # optional look-back window for the first run
    limit: 5             # optional number of intervals to process
    dry_run: false       # set true to log without writing
```

When `enabled` is true the Flask app launches a one-off background thread
during startup that executes `DataRecoverer.run_once` with the configured
window. Leave it false to trigger recoveries manually via scripts/CLI.

To execute a manual run from the CLI use the runner module:

```bash
python -m data_recoverer.runner \
  --config data_recoverer/config.yaml \
  --since-hours 24 \
  --limit 5 \
  --dry-run
```

Omit `--since-hours`, `--limit`, or `--dry-run` to use the defaults.
