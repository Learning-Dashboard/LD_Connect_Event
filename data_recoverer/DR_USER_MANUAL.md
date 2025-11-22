# Data Recovery (DR) User Manual

This guide walks newcomers through configuring, running, and monitoring the
Data Recovery module. Keep it open when onboarding teammates to DR.

---

## 1. Purpose
When LD Connect is offline, incoming GitHub/Taiga webhooks may be missed.
The DR module replay-retrieves those events by:
1. Reading downtime windows from `inactivity_intervals`.
2. Querying GitHub/Taiga REST APIs for everything that changed during those windows (starting from the last heartbeat).
3. Upserting the normalized documents into the usual MongoDB collections.
4. Logging each processed interval in `data_recovery_runs`.

---

## 2. Prerequisites
- Python environment with repo dependencies (`pip install -r requirements.txt`).
- MongoDB accessible using the credentials in `.env`.
- GitHub/Taiga API tokens defined either in `.env` (`GITHUB_TOKEN`, `TAIGA_USERNAME`, `TAIGA_PASSWORD`) or in `config_files/credentials_config.json`.
- Inactivity detector producing records in `inactivity_intervals`.

---

## 3. Configuration (`data_recoverer/config.yaml`)
```yaml
data_recoverer:
  inactivity_collection: inactivity_intervals
  run_log_collection: data_recovery_runs
  startup_run:
    enabled: false          # true to run automatically when app.py starts
    since_hours: null       # look-back window (optional)
    limit: null             # max intervals per run (optional)
    dry_run: false          # true to log without writing to Mongo
  projects:
    - project_id: my_team
      github:
        repositories:
          - org/repo
        events: [commits, issues, pull_requests]
      taiga:
        slug: my-taiga-slug
        events: [tasks, issues, userstories, epics]
```
Key notes:
- `projects.project_id` must match the `prj` field used by the ingestion pipeline.
- `startup_run` controls whether LD Connect triggers DR at startup; otherwise runs are manual.
- Omit `since_hours` or `limit` if you want to process every pending interval.

---

## 4. Running the Recoverer

### 4.1 Manual CLI runs
Use the runner module for one-off executions:
```bash
python -m data_recoverer.runner \
  --config data_recoverer/config.yaml \
  --since-hours 24 \
  --limit 5 \
  --dry-run
```
Flags:
- `--config` (optional): alternative YAML path.
- `--since-hours`: restrict intervals to a recent window (omit for all).
- `--limit`: maximum number of intervals (omit for all).
- `--dry-run`: fetch + log without writing to Mongo; remove flag for real runs.

### 4.2 Automatic startup run
Set `startup_run.enabled: true` in the config file and start the Flask app (`python app.py`). During startup, LD Connect will spawn a background thread that invokes DR with the configured `since_hours`, `limit`, and `dry_run`. This is a one-time run per process.

---

## 5. How Recovery Windows Are Selected
- Each interval’s `start_time` and `end_time` come from the inactivity detector.
- The recoverer automatically extends the query window back to `metadata.heartbeat.last_heartbeat` (when available) so the entire gap since the last heartbeat is covered.
- If an interval has already been processed (logged as `status: "success"` in `data_recovery_runs`), it is skipped; otherwise it is reprocessed.

---

## 6. Verifying a Run
1. Inspect console/log output – a summary dictionary is printed after each run with `processed_intervals`, `batches`, and `documents`.
2. Check Mongo collections (`github_<team>.commits`, `taiga_<team>.tasks`, etc.) for new/updated records.
3. Look at `data_recovery_runs` for a new document with `status: "success"` and matching interval start/end.

---

## 7. Error Handling & Rate Limits
- All HTTP requests use the shared `RetryPolicy` with exponential backoff on 429/5xx responses.
- Taiga/GitHub failures are recorded in `RecoveryErrorTracker.failed_intervals` (only in-memory today) and logged at ERROR level.
- If a run fails mid-interval, the recoverer logs it as `status: "failed"`; rerun the module to retry.

---

## 8. Best Practices
1. **Start small** – When testing, run with `--dry-run` and a small `limit`.
2. **Monitor detectors** – Ensure the inactivity detector is stable; DR will only fill intervals it sees in Mongo.
3. **Sort data on read** – Mongo doesn’t preserve chronological order; downstream code should sort by timestamp fields.
4. **Beware rate limits** – Large windows may require staggering runs; adjust `RetryPolicy` or split intervals if needed.
5. **Audit runs** – Periodically review `data_recovery_runs` to confirm no intervals are stuck in `failed`.

---

## 9. Troubleshooting
| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| `ModuleNotFoundError: pymongo` | venv not active | `pip install -r requirements.txt` |
| DR runs but no data appears | No intervals pending or wrong `project_id` | Check `inactivity_intervals` / config |
| Taiga 429 / IP blocks | API overload | Re-run later, lower `limit`, or split windows |
| Duplicate documents | DR is idempotent; duplicates shouldn’t appear | Confirm `_id`/key fields align; DR uses upserts |

---

## 10. Need Help?
- Check the source files: `data_recoverer/DR_recovery.py`, `data_recoverer/DR_api.py`, `data_recoverer/DR_error_control.py`.
- Unit tests: `python -m pytest data_recoverer/test_DR.py`.
- Reach out on the LD Connect Slack `#data-recovery` channel (or your team’s equivalent).

Keep this manual versioned with the code so newcomers always have the latest instructions. Happy recovering!
