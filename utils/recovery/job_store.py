import threading
import uuid
from datetime import datetime, timedelta, timezone

_lock = threading.Lock()
_jobs: dict = {}
_JOB_TTL = timedelta(hours=1)


def create_job() -> str:
    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {
            "status": "running",
            "steps": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    return job_id


def append_step(job_id: str, step: dict) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["steps"].append(step)


def finish_job(job_id: str, status: str) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = status


def get_job(job_id: str) -> dict | None:
    _purge_old_jobs()
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def _purge_old_jobs() -> None:
    cutoff = datetime.now(timezone.utc) - _JOB_TTL
    with _lock:
        stale = [
            jid for jid, j in _jobs.items()
            if datetime.fromisoformat(j["created_at"]) < cutoff
        ]
        for jid in stale:
            del _jobs[jid]
