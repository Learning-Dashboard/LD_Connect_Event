"""
API-specific fetchers used by the Data Recovery module.

The classes here wrap GitHub and Taiga APIs, normalising their responses
to the same schemas used by the ingestion webhooks so recovered data can
be stored transparently in MongoDB.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

import requests

from config.credentials_loader import resolve
from config.settings import GITHUB_TOKEN, TAIGA_PASSWORD, TAIGA_USERNAME
from data_recoverer.DR_error_control import RetryPolicy, raise_for_status
from datasources.github_handler import parse_github_event
from datasources.taiga_handler import to_madrid_local
from utils.taiga_token.taiga_auth import get_taiga_token

MADRID_TZ = ZoneInfo("Europe/Madrid")
LOGGER = logging.getLogger(__name__)


def _to_utc_iso(dt_value: Optional[datetime]) -> Optional[str]:
    if dt_value is None:
        return None
    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=MADRID_TZ)
    return dt_value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class RecoveryBatch:
    collection: str
    key_field: str
    documents: List[Dict[str, Any]]


class GitHubAPIClient:
    """
    Fetches GitHub data in a time window and shapes it like the webhook payloads.
    """

    def __init__(
        self,
        *,
        retry_policy: Optional[RetryPolicy] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.retry = retry_policy or RetryPolicy()
        self.session = session or requests.Session()

    def _headers(self, prj: str) -> Dict[str, str]:
        token = None
        try:
            token = resolve(prj, "github_token")
        except Exception:
            token = None
        if not token:
            token = GITHUB_TOKEN or None
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _paginate(self, url: str, headers: Dict[str, str]) -> Iterable[Dict[str, Any]]:
        while url:
            def _do_request() -> requests.Response:
                resp = self.session.get(url, headers=headers, timeout=30)
                raise_for_status(resp)
                return resp

            resp = self.retry.run(_do_request)
            yield from resp.json()
            url = resp.links.get("next", {}).get("url")

    def collect_batches(
        self,
        *,
        prj: str,
        repositories: List[str],
        since: Optional[datetime],
        until: Optional[datetime],
        event_types: Iterable[str] = ("commits", "issues", "pull_requests"),
    ) -> List[RecoveryBatch]:
        headers = self._headers(prj)
        batches: List[RecoveryBatch] = []
        event_set = set(event_types)
        for repo_full in repositories:
            owner, _, repo_name = repo_full.partition("/")
            if "commits" in event_set:
                commit_docs = self._fetch_commits(repo_full, owner or repo_full, prj, headers, since, until)
                if commit_docs:
                    batches.append(
                        RecoveryBatch(
                            collection=f"github_{prj}.commits",
                            key_field="sha",
                            documents=commit_docs,
                        )
                    )
            if "issues" in event_set:
                issue_docs = self._fetch_issues(repo_full, owner or repo_full, prj, headers, since, until)
                if issue_docs:
                    batches.append(
                        RecoveryBatch(
                            collection=f"github_{prj}.issues",
                            key_field="issue_id",
                            documents=issue_docs,
                        )
                    )
            if "pull_requests" in event_set:
                pr_docs = self._fetch_pull_requests(repo_full, owner or repo_full, prj, headers, since, until)
                if pr_docs:
                    batches.append(
                        RecoveryBatch(
                            collection=f"github_{prj}.pull_requests",
                            key_field="pr_number",
                            documents=pr_docs,
                        )
                    )
        return batches

    def _fetch_commits(
        self,
        repo_full: str,
        org: str,
        prj: str,
        headers: Dict[str, str],
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> List[Dict[str, Any]]:
        url = f"https://api.github.com/repos/{repo_full}/commits?per_page=100"
        since_iso = _to_utc_iso(since)
        until_iso = _to_utc_iso(until)
        if since_iso:
            url += f"&since={since_iso}"
        if until_iso:
            url += f"&until={until_iso}"
        docs: List[Dict[str, Any]] = []
        for commit in self._paginate(url, headers):
            payload = {
                "X-GitHub-Event": "push",
                "repository": {"full_name": repo_full},
                "organization": {"login": org},
                "sender": commit.get("author") or {},
                "commits": [
                    {
                        "id": commit.get("sha"),
                        "url": commit.get("url"),
                        "message": commit.get("commit", {}).get("message", ""),
                        "timestamp": commit.get("commit", {}).get("author", {}).get("date"),
                        "author": {
                            "username": (commit.get("author") or {}).get("login", ""),
                            "name": commit.get("commit", {}).get("author", {}).get("name", ""),
                            "email": commit.get("commit", {}).get("author", {}).get("email", ""),
                        },
                    }
                ],
            }
            parsed = parse_github_event(payload, prj)
            meta = {
                "team_name": parsed["team_name"],
                "repo_name": parsed["repo_name"],
                "sender_info": parsed["sender_info"],
                "event": parsed["event"],
                "prj": prj,
            }
            for c in parsed.get("commits", []):
                c.update(meta)
                docs.append(c)
        return docs

    def _fetch_issues(
        self,
        repo_full: str,
        org: str,
        prj: str,
        headers: Dict[str, str],
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> List[Dict[str, Any]]:
        url = f"https://api.github.com/repos/{repo_full}/issues?state=all&per_page=100"
        since_iso = _to_utc_iso(since)
        if since_iso:
            url += f"&since={since_iso}"
        docs: List[Dict[str, Any]] = []
        for issue in self._paginate(url, headers):
            # GitHub's issues API returns PRs too; keep only real issues here.
            if issue.get("pull_request"):
                continue
            updated_at = issue.get("updated_at")
            if until and updated_at:
                try:
                    updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    if updated_dt.replace(tzinfo=timezone.utc) > until.astimezone(timezone.utc):
                        # allow GitHub pagination ordering; we still keep issues newer than 'until'
                        pass
                except Exception:
                    pass
            payload = {
                "X-GitHub-Event": "issues",
                "action": issue.get("state", "opened"),
                "repository": {"full_name": repo_full},
                "organization": {"login": org},
                "sender": issue.get("user") or {},
                "issue": issue,
            }
            parsed = parse_github_event(payload, prj)
            parsed["prj"] = prj
            parsed["issue_id"] = parsed.get("issue", {}).get("number")
            docs.append(parsed)
        return docs

    def _fetch_pull_requests(
        self,
        repo_full: str,
        org: str,
        prj: str,
        headers: Dict[str, str],
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> List[Dict[str, Any]]:
        url = (
            f"https://api.github.com/repos/{repo_full}/pulls"
            f"?state=all&sort=updated&direction=desc&per_page=100"
        )
        since_iso = _to_utc_iso(since)
        docs: List[Dict[str, Any]] = []
        for pr in self._paginate(url, headers):
            if pr.get("state") != "closed":
                continue
            updated_at = pr.get("updated_at")
            if since_iso and updated_at and updated_at < since_iso:
                break  # ordered by updated desc; safe to stop
            payload = {
                "X-GitHub-Event": "pull_request",
                "action": "closed",
                "repository": {"full_name": repo_full},
                "organization": {"login": org},
                "sender": pr.get("user") or {},
                "pull_request": pr,
            }
            parsed = parse_github_event(payload, prj)
            parsed["prj"] = prj
            docs.append(parsed)
        return docs


class TaigaAPIClient:
    """
    Fetches Taiga entities updated within a time window.
    """

    BASE_URL = "https://api.taiga.io/api/v1"

    def __init__(
        self,
        *,
        retry_policy: Optional[RetryPolicy] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.retry = retry_policy or RetryPolicy()
        self.session = session or requests.Session()
        self._project_cache: Dict[str, int] = {}

    def _auth_headers(self, prj: str) -> Dict[str, str]:
        user = None
        pwd = None
        try:
            user = resolve(prj, "taiga_user")
            pwd = resolve(prj, "taiga_password")
        except Exception:
            user = None
            pwd = None
        user = user or TAIGA_USERNAME
        pwd = pwd or TAIGA_PASSWORD
        headers: Dict[str, str] = {"x-disable-pagination": "True"}
        if user and pwd:
            token = get_taiga_token(user, pwd)
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _project_id(self, slug: Optional[str], explicit_id: Optional[int], headers: Dict[str, str]) -> Optional[int]:
        if explicit_id:
            return explicit_id
        if not slug:
            return None
        if slug in self._project_cache:
            return self._project_cache[slug]

        url = f"{self.BASE_URL}/projects/by_slug"

        def _do_request() -> requests.Response:
            resp = self.session.get(url, headers=headers, params={"slug": slug}, timeout=15)
            raise_for_status(resp)
            return resp

        resp = self.retry.run(_do_request)
        pid = resp.json().get("id")
        if pid:
            self._project_cache[slug] = int(pid)
        return pid

    def collect_batches(
        self,
        *,
        prj: str,
        project_slug: Optional[str],
        project_id: Optional[int],
        since: Optional[datetime],
        until: Optional[datetime],
        event_types: Iterable[str] = ("tasks", "issues", "userstories", "epics"),
    ) -> List[RecoveryBatch]:
        headers = self._auth_headers(prj)
        pid = self._project_id(project_slug, project_id, headers)
        if not pid:
            LOGGER.warning("Skipping Taiga recovery for %s: project id/slug missing.", prj)
            return []
        span = self._build_span_params(since, until)
        batches: List[RecoveryBatch] = []
        for event in event_types:
            endpoint, converter, key_field, collection_suffix = self._endpoint_map()[event]
            docs = self._fetch_entities(endpoint, pid, headers, converter, prj, span)
            if docs:
                batches.append(
                    RecoveryBatch(
                        collection=f"taiga_{prj}.{collection_suffix}",
                        key_field=key_field,
                        documents=docs,
                    )
                )
        return batches

    def _build_span_params(
        self, since: Optional[datetime], until: Optional[datetime]
    ) -> Dict[str, str]:
        params: Dict[str, str] = {}
        since_iso = _to_utc_iso(since)
        until_iso = _to_utc_iso(until)
        if since_iso:
            params["modified_date__gte"] = since_iso
        if until_iso:
            params["modified_date__lte"] = until_iso
        return params

    def _fetch_entities(
        self,
        endpoint: str,
        project_id: int,
        headers: Dict[str, str],
        converter,
        prj: str,
        extra_params: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}/{endpoint}"
        params = {"project": project_id}
        params.update(extra_params)

        def _do_request() -> requests.Response:
            resp = self.session.get(url, headers=headers, params=params, timeout=30)
            raise_for_status(resp)
            return resp

        resp = self.retry.run(_do_request)
        payloads = resp.json()
        docs: List[Dict[str, Any]] = []
        for item in payloads:
            doc = converter(item, prj)
            docs.append(doc)
        return docs

    def _endpoint_map(self):
        return {
            "tasks": ("tasks", _task_from_api, "task_id", "tasks"),
            "issues": ("issues", _issue_from_api, "issue_id", "issues"),
            "epics": ("epics", _epic_from_api, "epic_id", "epics"),
            "userstories": ("userstories", _userstory_from_api, "userstory_id", "userstories"),
        }


def _task_from_api(item: dict, prj: str) -> dict:
    m = item.get("milestone_extra_info") or {}
    return {
        "task_id": item["id"],
        "action_type": "recovered",
        "assigned_by": "recovery",
        "assigned_to": (item.get("assigned_to_extra_info") or {}).get("username"),
        "created_date": to_madrid_local(item.get("created_date", "")),
        "custom_attributes": item.get("custom_attributes_values") or {},
        "event_type": "task",
        "finished_date": to_madrid_local(item.get("finished_date", "")),
        "is_closed": (item.get("status_extra_info") or {}).get("is_closed"),
        "milestone_closed": m.get("closed"),
        "milestone_created_date": to_madrid_local(m.get("created_date", "")),
        "milestone_id": item.get("milestone"),
        "milestone_modified_date": to_madrid_local(m.get("modified_date", "")),
        "milestone_name": m.get("name"),
        "modified_date": to_madrid_local(item.get("modified_date", "")),
        "project_id": item.get("project"),
        "reference": item.get("ref"),
        "status": (item.get("status_extra_info") or {}).get("name"),
        "subject": item.get("subject", ""),
        "team_name": (item.get("project_extra_info") or {}).get("name"),
        "userstory_id": item.get("user_story"),
        "userstory_is_closed": (item.get("user_story_extra_info") or {}).get("is_closed"),
        "estimated_start": to_madrid_local(m.get("estimated_start", "")) if m else "",
        "estimated_finish": to_madrid_local(m.get("estimated_finish", "")) if m else "",
        "prj": prj,
    }


def _issue_from_api(item: dict, prj: str) -> dict:
    return {
        "issue_id": item["id"],
        "action_type": "recovered",
        "assigned_by": (item.get("owner_extra_info") or {}).get("username") or "recovery",
        "assigned_to": (item.get("assigned_to_extra_info") or {}).get("username"),
        "created_date": to_madrid_local(item.get("created_date", "")),
        "description": item.get("description", ""),
        "due_date": to_madrid_local(item.get("due_date", "")),
        "event_type": "issue",
        "finished_date": to_madrid_local(item.get("finished_date", "")),
        "is_closed": (item.get("status_extra_info") or {}).get("is_closed"),
        "modified_date": to_madrid_local(item.get("modified_date", "")),
        "priority": (item.get("priority_extra_info") or {}).get("name"),
        "project_id": item.get("project"),
        "severity": (item.get("severity_extra_info") or {}).get("name"),
        "status": (item.get("status_extra_info") or {}).get("name"),
        "subject": item.get("subject", ""),
        "team_name": (item.get("project_extra_info") or {}).get("name"),
        "type": (item.get("type_extra_info") or {}).get("name"),
        "created_by": (item.get("owner_extra_info") or {}).get("username"),
        "prj": prj,
    }


def _epic_from_api(item: dict, prj: str) -> dict:
    return {
        "epic_id": item["id"],
        "action_type": "recovered",
        "assigned_by": (item.get("owner_extra_info") or {}).get("username") or "recovery",
        "created_date": to_madrid_local(item.get("created_date", "")),
        "event_type": "epic",
        "is_closed": (item.get("status_extra_info") or {}).get("is_closed"),
        "modified_date": to_madrid_local(item.get("modified_date", "")),
        "project_id": item.get("project"),
        "status": (item.get("status_extra_info") or {}).get("name"),
        "subject": item.get("subject", ""),
        "team_name": (item.get("project_extra_info") or {}).get("name"),
        "milestone_id": item.get("milestone"),
        "milestone_name": (item.get("milestone_extra_info") or {}).get("name"),
        "prj": prj,
    }


def _userstory_from_api(item: dict, prj: str) -> dict:
    m = item.get("milestone_extra_info") or {}
    desc = item.get("description") or ""
    pattern = bool(re.search(r"as\s+.*?\s+i want\s+.*?\s+so that\s+.*", desc, re.I))
    raw_points = item.get("points")
    if isinstance(raw_points, list):
        total = sum((p.get("value") or 0) for p in raw_points)
    else:
        total = 0

    return {
        "userstory_id": item["id"],
        "action_type": "recovered",
        "assigned_by": (item.get("owner_extra_info") or {}).get("username") or "recovery",
        "created_date": to_madrid_local(item.get("created_date", "")),
        "custom_attributes": item.get("custom_attributes_values") or {},
        "estimated_finish": to_madrid_local(m.get("estimated_finish", "")) if m else "",
        "estimated_start": to_madrid_local(m.get("estimated_start", "")) if m else "",
        "event_type": "userstory",
        "is_closed": (item.get("status_extra_info") or {}).get("is_closed"),
        "milestone_closed": m.get("closed"),
        "milestone_created_date": to_madrid_local(m.get("created_date", "")),
        "milestone_id": item.get("milestone"),
        "milestone_modified_date": to_madrid_local(m.get("modified_date", "")),
        "milestone_name": m.get("name"),
        "modified_date": to_madrid_local(item.get("modified_date", "")),
        "pattern": pattern,
        "priority": (item.get("custom_attributes_values") or {}).get("Priority"),
        "project_id": item.get("project"),
        "status": (item.get("status_extra_info") or {}).get("name"),
        "subject": item.get("subject", ""),
        "team_name": (item.get("project_extra_info") or {}).get("name"),
        "total_points": total,
        "prj": prj,
    }
