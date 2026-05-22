from concurrent.futures import ThreadPoolExecutor
from datetime import timezone
from urllib.parse import urlparse

import logging
from flask import Blueprint, jsonify, request

from utils.recovery.github_recovery import collect_github, parse_dt, get_organization_repos
from utils.recovery.taiga_recovery import main as taiga_recovery_main
from utils.recovery.job_store import create_job, append_step, finish_job, get_job
from config.settings import GITHUB_TOKEN

logger = logging.getLogger(__name__)

recovery_bp = Blueprint("recovery_bp", __name__)

_recovery_executor = ThreadPoolExecutor(max_workers=3)


def _parse_github_url(value: str) -> tuple[str, str | None]:
    if not value:
        raise ValueError("github_url is required")

    raw = value.strip()
    if raw.endswith(".git"):
        raw = raw[:-4]

    if "://" not in raw:
        parts = [part for part in raw.split("/") if part]
        if len(parts) >= 2:
            return parts[0], parts[1]
        if len(parts) == 1:
            return parts[0], None
        raise ValueError("github_url must contain organization (and optionally repository)")

    parsed = urlparse(raw)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 1:
        raise ValueError("github_url must contain organization (and optionally repository)")

    if parts[0] == "repos" and len(parts) >= 3:
        return parts[1], parts[2]

    if len(parts) == 1:
        return parts[0], None

    return parts[0], parts[1]


def _parse_taiga_slug(value: str) -> str:
    if not value:
        raise ValueError("taiga_url is required")

    raw = value.strip()
    if "://" not in raw:
        return raw.strip("/")

    parsed = urlparse(raw)
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        raise ValueError("taiga_url does not contain a project slug")

    if "project" in parts:
        project_index = parts.index("project")
        if project_index + 1 < len(parts):
            return parts[project_index + 1]

    return parts[-1]


def _to_iso_utc(value: str | None) -> str | None:
    if not value:
        return None
    return (
        parse_dt(value)
        .astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ── Background tasks ──────────────────────────────────────────────────────────

def _bg_team_recovery(
    job_id, prj, org, repo, slug,
    since, until, github_events, taiga_events,
    quality_model, github_token, from_date, to_date, taiga_token,
):
    try:
        headers = {"Accept": "application/vnd.github+json"}
        effective_github_token = github_token or GITHUB_TOKEN
        if effective_github_token:
            headers["Authorization"] = f"Bearer {effective_github_token}"

        try:
            repos_to_recover = [repo] if repo else get_organization_repos(org, headers)
            if not repos_to_recover:
                raise ValueError(f"No repositories found for organization '{org}'")
            for repo_name in repos_to_recover:
                logger.info("GitHub recovery: team=%s repo=%s/%s", prj, org, repo_name)
                collect_github(
                    org=org, repo=repo_name, prj=prj,
                    events=list(github_events), since=since, until=until,
                    quality_model=quality_model, github_token=effective_github_token,
                )
            append_step(job_id, {"source": "github", "status": "ok"})
        except Exception as exc:
            logger.exception("GitHub recovery failed for team %s", prj)
            append_step(job_id, {"source": "github", "status": "error", "error": str(exc)})

        try:
            taiga_args = [
                "--slug", slug, "--prj", prj,
                "--events", ",".join(taiga_events),
                "--quality-model", quality_model,
            ]
            if from_date:
                taiga_args.extend(["--from-date", from_date])
            if to_date:
                taiga_args.extend(["--to-date", to_date])
            if taiga_token:
                taiga_args.extend(["--taiga-token", taiga_token])

            logger.info("Taiga recovery: team=%s slug=%s", prj, slug)
            taiga_recovery_main(taiga_args)
            append_step(job_id, {"source": "taiga", "status": "ok"})
        except BaseException as exc:
            logger.exception("Taiga recovery failed for team %s", prj)
            append_step(job_id, {"source": "taiga", "status": "error", "error": str(exc)})

    except Exception as exc:
        logger.exception("Unexpected error in team recovery job %s", job_id)
        append_step(job_id, {"source": "unknown", "status": "error", "error": str(exc)})

    finally:
        job = get_job(job_id)
        steps = job["steps"] if job else []
        final = "error" if any(s["status"] == "error" for s in steps) else "done"
        finish_job(job_id, final)


def _bg_github_recovery(
    job_id, prj, org, repo,
    since, until, github_events, quality_model, github_token,
):
    try:
        headers = {"Accept": "application/vnd.github+json"}
        effective_github_token = github_token or GITHUB_TOKEN
        if effective_github_token:
            headers["Authorization"] = f"Bearer {effective_github_token}"

        try:
            repos_to_recover = [repo] if repo else get_organization_repos(org, headers)
            if not repos_to_recover:
                raise ValueError(f"No repositories found for organization '{org}'")
            for repo_name in repos_to_recover:
                logger.info("GitHub recovery: team=%s repo=%s/%s", prj, org, repo_name)
                collect_github(
                    org=org, repo=repo_name, prj=prj,
                    events=list(github_events), since=since, until=until,
                    quality_model=quality_model, github_token=effective_github_token,
                )
            append_step(job_id, {"source": "github", "status": "ok"})
        except Exception as exc:
            logger.exception("GitHub recovery failed for team %s", prj)
            append_step(job_id, {"source": "github", "status": "error", "error": str(exc)})

    except Exception as exc:
        logger.exception("Unexpected error in github recovery job %s", job_id)
        append_step(job_id, {"source": "unknown", "status": "error", "error": str(exc)})

    finally:
        job = get_job(job_id)
        steps = job["steps"] if job else []
        final = "error" if any(s["status"] == "error" for s in steps) else "done"
        finish_job(job_id, final)


def _bg_taiga_recovery(
    job_id, prj, slug, taiga_events, quality_model,
    from_date, to_date, taiga_token,
):
    try:
        try:
            taiga_args = [
                "--slug", slug, "--prj", prj,
                "--events", ",".join(taiga_events),
                "--quality-model", quality_model,
            ]
            if from_date:
                taiga_args.extend(["--from-date", from_date])
            if to_date:
                taiga_args.extend(["--to-date", to_date])
            if taiga_token:
                taiga_args.extend(["--taiga-token", taiga_token])

            logger.info("Taiga recovery: team=%s slug=%s", prj, slug)
            taiga_recovery_main(taiga_args)
            append_step(job_id, {"source": "taiga", "status": "ok"})
        except BaseException as exc:
            logger.exception("Taiga recovery failed for team %s", prj)
            append_step(job_id, {"source": "taiga", "status": "error", "error": str(exc)})

    except Exception as exc:
        logger.exception("Unexpected error in taiga recovery job %s", job_id)
        append_step(job_id, {"source": "unknown", "status": "error", "error": str(exc)})

    finally:
        job = get_job(job_id)
        steps = job["steps"] if job else []
        final = "error" if any(s["status"] == "error" for s in steps) else "done"
        finish_job(job_id, final)


# ── Routes ────────────────────────────────────────────────────────────────────

@recovery_bp.route("/admin/recovery/status/<job_id>", methods=["GET"])
def get_recovery_status(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job), 200


@recovery_bp.route("/admin/recovery/team", methods=["POST"])
def run_team_recovery():
    payload = request.get_json(silent=True) or {}

    prj = (payload.get("prj") or "").strip()
    github_url = (payload.get("github_url") or "").strip()
    taiga_url = (payload.get("taiga_url") or "").strip()

    if not prj:
        return jsonify({"error": "prj is required"}), 400
    if not github_url:
        return jsonify({"error": "github_url is required"}), 400
    if not taiga_url:
        return jsonify({"error": "taiga_url is required"}), 400

    quality_model = (payload.get("quality_model") or "default").strip() or "default"
    from_date = payload.get("from_date")
    to_date = payload.get("to_date")
    github_events = payload.get("github_events") or ["commits", "issues", "pull_requests"]
    taiga_events = payload.get("taiga_events") or ["task", "userstory", "issue", "epic"]
    github_token = (payload.get("github_token") or "").strip() or None
    taiga_token = (payload.get("taiga_token") or "").strip() or None

    try:
        org, repo = _parse_github_url(github_url)
        slug = _parse_taiga_slug(taiga_url)
        since = _to_iso_utc(from_date)
        until = _to_iso_utc(to_date)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    job_id = create_job()
    _recovery_executor.submit(
        _bg_team_recovery,
        job_id, prj, org, repo, slug,
        since, until, github_events, taiga_events,
        quality_model, github_token, from_date, to_date, taiga_token,
    )
    return jsonify({"job_id": job_id, "status": "running"}), 202


@recovery_bp.route("/admin/recovery/github", methods=["POST"])
def run_github_recovery():
    payload = request.get_json(silent=True) or {}

    prj = (payload.get("prj") or "").strip()
    github_url = (payload.get("github_url") or "").strip()

    if not prj:
        return jsonify({"error": "prj is required"}), 400
    if not github_url:
        return jsonify({"error": "github_url is required"}), 400

    quality_model = (payload.get("quality_model") or "default").strip() or "default"
    from_date = payload.get("from_date")
    to_date = payload.get("to_date")
    github_events = payload.get("github_events") or ["commits", "issues", "pull_requests"]
    github_token = (payload.get("github_token") or "").strip() or None

    try:
        org, repo = _parse_github_url(github_url)
        since = _to_iso_utc(from_date)
        until = _to_iso_utc(to_date)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    job_id = create_job()
    _recovery_executor.submit(
        _bg_github_recovery,
        job_id, prj, org, repo,
        since, until, github_events, quality_model, github_token,
    )
    return jsonify({"job_id": job_id, "status": "running"}), 202


@recovery_bp.route("/admin/recovery/taiga", methods=["POST"])
def run_taiga_recovery():
    payload = request.get_json(silent=True) or {}

    prj = (payload.get("prj") or "").strip()
    taiga_url = (payload.get("taiga_url") or "").strip()

    if not prj:
        return jsonify({"error": "prj is required"}), 400
    if not taiga_url:
        return jsonify({"error": "taiga_url is required"}), 400

    quality_model = (payload.get("quality_model") or "default").strip() or "default"
    from_date = payload.get("from_date")
    to_date = payload.get("to_date")
    taiga_events = payload.get("taiga_events") or ["task", "userstory", "issue", "epic"]
    taiga_token = (payload.get("taiga_token") or "").strip() or None

    try:
        slug = _parse_taiga_slug(taiga_url)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    job_id = create_job()
    _recovery_executor.submit(
        _bg_taiga_recovery,
        job_id, prj, slug, taiga_events, quality_model,
        from_date, to_date, taiga_token,
    )
    return jsonify({"job_id": job_id, "status": "running"}), 202
