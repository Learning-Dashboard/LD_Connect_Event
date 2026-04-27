import logging
import requests
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from utils.taiga_token.taiga_auth import get_taiga_token
from config.credentials_loader import resolve
from config.settings import TAIGA_API_URL, TAIGA_TOKEN

_CACHE = {}                 # key = (project_id, milestone_id) -> (timestamp, stats)
_DETAILS_CACHE = {}         # key = (project_id, milestone_id) -> (timestamp, details)
_USERSTORY_CACHE = {}       # key = (project_id, userstory_id) -> (timestamp, details)
_US_CUSTOM_ATTR_NAMES_CACHE = {}  # key = project_id -> (timestamp, {attr_id(str): attr_name})
_TASK_CUSTOM_ATTR_NAMES_CACHE = {}  # key = project_id -> (timestamp, {attr_id(str): attr_name})
TTL    = timedelta(minutes=1) # Cache time-to-live, set to 5 minutes. Means that if the same request is made within 5 minutes, it will return the cached result instead of making a new API call.
log = logging.getLogger(__name__)
logger = log
TAIGA_LOOKUP_ERRORS = (requests.RequestException,)
_TAIGA_TOKEN_OVERRIDE: ContextVar[str | None] = ContextVar("taiga_token_override", default=None)


def push_taiga_token_override(token: str | None):
    """Temporarily override Taiga bearer token for the current request context."""
    normalized = token.strip() if isinstance(token, str) and token.strip() else None
    return _TAIGA_TOKEN_OVERRIDE.set(normalized)


def pop_taiga_token_override(token_handle):
    _TAIGA_TOKEN_OVERRIDE.reset(token_handle)


def _empty_stats():
    return {
        "milestone_total_points": 0,
        "milestone_closed_points": 0,
        "milestone_total_userstories": 0,
        "milestone_completed_userstories": 0,
        "milestone_total_tasks": 0,
        "milestone_completed_tasks": 0,
    }


def _build_taiga_headers(prj: str):
    """Return Taiga headers for public, private and SSO deployments."""
    token_override = _TAIGA_TOKEN_OVERRIDE.get()
    if token_override:
        return {"Authorization": f"Bearer {token_override}"}

    if TAIGA_TOKEN:
        return {"Authorization": f"Bearer {TAIGA_TOKEN}"}

    try:
        user = resolve(prj, "taiga_user")
        psw = resolve(prj, "taiga_password")
    except KeyError:
        log.warning("No Taiga credentials configured for project %s; using anonymous requests.", prj)
        return {}

    if user and psw:
        try:
            token = get_taiga_token(user, psw)
            return {"Authorization": f"Bearer {token}"}
        except requests.RequestException as exc:
            log.warning("Failed to fetch Taiga token for project %s: %s", prj, exc)
            return {}

    log.warning("Incomplete Taiga credentials for project %s; using anonymous requests.", prj)
    return {}


def _userstory_custom_attribute_names(project_id: str, prj: str):
    """Return map of custom attribute id -> name for userstories in a project."""
    if not project_id:
        return {}

    key = str(project_id)
    now = datetime.now(timezone.utc)
    if key in _US_CUSTOM_ATTR_NAMES_CACHE and now - _US_CUSTOM_ATTR_NAMES_CACHE[key][0] < TTL:
        return _US_CUSTOM_ATTR_NAMES_CACHE[key][1]

    headers = _build_taiga_headers(prj)
    url = f"{TAIGA_API_URL}/userstory-custom-attributes"
    try:
        r = requests.get(url, params={"project": project_id}, headers=headers, timeout=(1, 5))
        r.raise_for_status()
        mapping = {str(item.get("id")): item.get("name") for item in (r.json() or []) if item.get("id") and item.get("name")}
    except requests.RequestException as exc:
        log.warning("Failed to fetch userstory custom attribute definitions for project %s: %s", project_id, exc)
        mapping = {}

    _US_CUSTOM_ATTR_NAMES_CACHE[key] = (now, mapping)
    return mapping


def _userstory_custom_values(project_id: str, userstory_id: str, prj: str):
    """Fetch custom attribute values for a userstory and map IDs to attribute names."""
    if not project_id or not userstory_id:
        return {}

    headers = _build_taiga_headers(prj)
    url = f"{TAIGA_API_URL}/userstories/custom-attributes-values/{userstory_id}"
    try:
        r = requests.get(url, params={"project": project_id}, headers=headers, timeout=(1, 5))
        r.raise_for_status()
        raw_values = (r.json() or {}).get("attributes_values") or {}
    except requests.RequestException as exc:
        log.warning("Failed to fetch custom values for userstory %s in project %s: %s", userstory_id, project_id, exc)
        return {}

    names = _userstory_custom_attribute_names(project_id, prj)
    mapped = {}
    for attr_id, value in raw_values.items():
        mapped[names.get(str(attr_id), str(attr_id))] = value
    return mapped


def _task_custom_attribute_names(project_id: str, prj: str):
    """Return map of custom attribute id -> name for tasks in a project."""
    if not project_id:
        return {}

    key = str(project_id)
    now = datetime.now(timezone.utc)
    if key in _TASK_CUSTOM_ATTR_NAMES_CACHE and now - _TASK_CUSTOM_ATTR_NAMES_CACHE[key][0] < TTL:
        return _TASK_CUSTOM_ATTR_NAMES_CACHE[key][1]

    headers = _build_taiga_headers(prj)
    url = f"{TAIGA_API_URL}/task-custom-attributes"
    try:
        r = requests.get(url, params={"project": project_id}, headers=headers, timeout=(1, 5))
        r.raise_for_status()
        mapping = {str(item.get("id")): item.get("name") for item in (r.json() or []) if item.get("id") and item.get("name")}
    except requests.RequestException as exc:
        log.warning("Failed to fetch task custom attribute definitions for project %s: %s", project_id, exc)
        mapping = {}

    _TASK_CUSTOM_ATTR_NAMES_CACHE[key] = (now, mapping)
    return mapping


def _task_custom_values(project_id: str, task_id: str, prj: str):
    """Fetch custom attribute values for a task and map IDs to attribute names."""
    if not project_id or not task_id:
        return {}

    headers = _build_taiga_headers(prj)
    url = f"{TAIGA_API_URL}/tasks/custom-attributes-values/{task_id}"
    try:
        r = requests.get(url, params={"project": project_id}, headers=headers, timeout=(1, 5))
        r.raise_for_status()
        raw_values = (r.json() or {}).get("attributes_values") or {}
    except requests.RequestException as exc:
        log.warning("Failed to fetch custom values for task %s in project %s: %s", task_id, project_id, exc)
        return {}

    names = _task_custom_attribute_names(project_id, prj)
    mapped = {}
    for attr_id, value in raw_values.items():
        mapped[names.get(str(attr_id), str(attr_id))] = value
    return mapped


def milestone_details(project_id: str, milestone_id: str, prj: str):
    """
    Fetches the milestone metadata from Taiga.
    Returns the raw milestone fields needed to enrich recovery documents.
    """
    if not project_id or not milestone_id:
        return {}

    key = (project_id, milestone_id)
    now = datetime.now(timezone.utc)
    if key in _DETAILS_CACHE and now - _DETAILS_CACHE[key][0] < TTL:
        return _DETAILS_CACHE[key][1]

    try:
        headers = _build_taiga_headers(prj)
        url = f"{TAIGA_API_URL}/milestones/{milestone_id}"
        r = requests.get(
            url, params={"project": project_id}, headers=headers, timeout=(1, 5)
        )
        r.raise_for_status()
    except TAIGA_LOOKUP_ERRORS as exc:
        logger.warning(
            "Failed to fetch milestone details for project %s milestone %s: %s",
            project_id,
            milestone_id,
            exc,
        )
        return {}

    js = r.json()
    details = {
        "milestone_created_date": js.get("created_date"),
        "milestone_modified_date": js.get("modified_date"),
        "milestone_name": js.get("name"),
        "estimated_start": js.get("estimated_start"),
        "estimated_finish": js.get("estimated_finish"),
        "milestone_closed": bool(js.get("closed", False)),
    }
    _DETAILS_CACHE[key] = (now, details)
    return details


def userstory_details(project_id: str, userstory_id: str, prj: str):
    """
    Fetches the userstory metadata from Taiga.
    Used as a fallback when task payloads do not include the nested userstory state.
    Also returns custom_attributes and description for recovery backfill.
    """
    if not project_id or not userstory_id:
        return {}

    key = (project_id, userstory_id)
    now = datetime.now(timezone.utc)
    if key in _USERSTORY_CACHE and now - _USERSTORY_CACHE[key][0] < TTL:
        return _USERSTORY_CACHE[key][1]

    try:
        headers = _build_taiga_headers(prj)
        url = f"{TAIGA_API_URL}/userstories/{userstory_id}"
        r = requests.get(
            url, params={"project": project_id}, headers=headers, timeout=(1, 5)
        )
        r.raise_for_status()
    except TAIGA_LOOKUP_ERRORS as exc:
        logger.warning(
            "Failed to fetch user story details for project %s user story %s: %s",
            project_id,
            userstory_id,
            exc,
        )
        return {}

    js = r.json()
    custom_values = js.get("custom_attributes_values") or _userstory_custom_values(project_id, userstory_id, prj)
    details = {
        "userstory_is_closed": (js.get("status_extra_info") or {}).get("is_closed"),
        "custom_attributes_values": custom_values or {},
        "description": js.get("description") or "",
    }
    _USERSTORY_CACHE[key] = (now, details)
    return details

def task_details(project_id: str, task_id: str, prj: str):
    """
    Fetches the task metadata from Taiga.
    Returns custom_attributes with fallback to dedicated endpoint if empty.
    """
    if not project_id or not task_id:
        return {}

    headers = _build_taiga_headers(prj)
    url = f"{TAIGA_API_URL}/tasks/{task_id}"
    try:
        r = requests.get(url, params={"project": project_id}, headers=headers, timeout=(1, 5))
        r.raise_for_status()
        js = r.json()
    except requests.RequestException as exc:
        log.warning("Failed to fetch task %s in project %s: %s", task_id, project_id, exc)
        return {}

    custom_values = js.get("custom_attributes_values") or _task_custom_values(project_id, task_id, prj)
    details = {
        "custom_attributes_values": custom_values or {},
    }
    return details

def milestone_stats(project_id: str, milestone_id: str, prj: str):
    """
    Fetches the statistics of a milestone in a Taiga project.
    Uses caching to avoid frequent API calls to get the taiga token.
    It refreshes the cache every 5 minutes.
    """
    if not project_id or not milestone_id:
        return {}

    key = (project_id, milestone_id)
    now = datetime.now(timezone.utc)
    if key in _CACHE and now - _CACHE[key][0] < TTL:
        return _CACHE[key][1]

    try:
        headers = _build_taiga_headers(prj)
        url = f"{TAIGA_API_URL}/milestones/{milestone_id}/stats"
        r = requests.get(
            url, params={"project": project_id}, headers=headers, timeout=(1, 5)
        )
        r.raise_for_status()
    except TAIGA_LOOKUP_ERRORS as exc:
        logger.warning(
            "Failed to fetch milestone stats for project %s milestone %s: %s",
            project_id,
            milestone_id,
            exc,
        )
        return _empty_stats()

    js = r.json()
    stats = {
        "milestone_total_points": sum((js.get("total_points") or {}).values()),
        "milestone_closed_points": sum(js.get("completed_points") or []),
        "milestone_total_userstories": js.get("total_userstories", 0),
        "milestone_completed_userstories": js.get("completed_userstories", 0),
        "milestone_total_tasks": js.get("total_tasks", 0),
        "milestone_completed_tasks": js.get("completed_tasks", 0),
    }
    _CACHE[key] = (now, stats)
    return stats
