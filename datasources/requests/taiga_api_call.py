import logging
import requests
from requests.adapters import HTTPAdapter
from datetime import datetime, timedelta, timezone
from utils.taiga_token.taiga_auth import auth_headers
from config.credentials_loader import (
    CredentialsConfigError,
    ProjectCredentialsNotFoundError,
    TaigaContext,
    get_taiga_context,
)

_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=5, pool_maxsize=10)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)

# Every cache key starts with the Taiga API URL: each subject can use a different
# Taiga server, and ids are only unique within one server.
_CACHE = {}                 # key = (api_url, project_id, milestone_id) -> (timestamp, stats)
_DETAILS_CACHE = {}         # key = (api_url, project_id, milestone_id) -> (timestamp, details)
_USERSTORY_CACHE = {}       # key = (api_url, project_id, userstory_id) -> (timestamp, details)
_US_CUSTOM_ATTR_NAMES_CACHE = {}  # key = (api_url, project_id) -> (timestamp, {attr_id(str): attr_name})
_TASK_CUSTOM_ATTR_NAMES_CACHE = {}  # key = (api_url, project_id) -> (timestamp, {attr_id(str): attr_name})
TTL    = timedelta(minutes=1) # Cache time-to-live, set to 5 minutes. Means that if the same request is made within 5 minutes, it will return the cached result instead of making a new API call.
log = logging.getLogger(__name__)
logger = log
TAIGA_LOOKUP_ERRORS = (requests.RequestException,)


def _empty_stats():
    return {
        "milestone_total_points": 0,
        "milestone_closed_points": 0,
        "milestone_total_userstories": 0,
        "milestone_completed_userstories": 0,
        "milestone_total_tasks": 0,
        "milestone_completed_tasks": 0,
    }


def _taiga_context(prj: str) -> TaigaContext | None:
    """Return the Taiga server of the project's subject, or None when it is not usable.

    A missing or incomplete credentials entry must not lose the event that is
    being enriched, so it is logged here and callers return empty data.
    """
    try:
        return get_taiga_context(prj)
    except (CredentialsConfigError, ProjectCredentialsNotFoundError) as exc:
        log.error("No usable Taiga credentials for project %s: %s", prj, exc)
        return None


def _get_json(ctx: TaigaContext, path: str, project_id: str):
    """GET <path> from the subject's Taiga server. Raises requests.RequestException."""
    r = _session.get(
        f"{ctx.api_url}/{path}",
        params={"project": project_id},
        headers=auth_headers(ctx),
        timeout=(1, 5),
    )
    r.raise_for_status()
    return r.json()


def _userstory_custom_attribute_names(ctx: TaigaContext, project_id: str):
    """Return map of custom attribute id -> name for userstories in a project."""
    if not project_id:
        return {}

    key = (ctx.api_url, str(project_id))
    now = datetime.now(timezone.utc)
    if key in _US_CUSTOM_ATTR_NAMES_CACHE and now - _US_CUSTOM_ATTR_NAMES_CACHE[key][0] < TTL:
        return _US_CUSTOM_ATTR_NAMES_CACHE[key][1]

    try:
        items = _get_json(ctx, "userstory-custom-attributes", project_id)
        mapping = {str(item.get("id")): item.get("name") for item in (items or []) if item.get("id") and item.get("name")}
    except requests.RequestException as exc:
        log.warning("Failed to fetch userstory custom attribute definitions for project %s: %s", project_id, exc)
        mapping = {}

    _US_CUSTOM_ATTR_NAMES_CACHE[key] = (now, mapping)
    return mapping


def _userstory_custom_values(ctx: TaigaContext, project_id: str, userstory_id: str):
    """Fetch custom attribute values for a userstory and map IDs to attribute names."""
    if not project_id or not userstory_id:
        return {}

    try:
        js = _get_json(ctx, f"userstories/custom-attributes-values/{userstory_id}", project_id)
        raw_values = (js or {}).get("attributes_values") or {}
    except requests.RequestException as exc:
        log.warning("Failed to fetch custom values for userstory %s in project %s: %s", userstory_id, project_id, exc)
        return {}

    names = _userstory_custom_attribute_names(ctx, project_id)
    mapped = {}
    for attr_id, value in raw_values.items():
        mapped[names.get(str(attr_id), str(attr_id))] = value
    return mapped


def _task_custom_attribute_names(ctx: TaigaContext, project_id: str):
    """Return map of custom attribute id -> name for tasks in a project."""
    if not project_id:
        return {}

    key = (ctx.api_url, str(project_id))
    now = datetime.now(timezone.utc)
    if key in _TASK_CUSTOM_ATTR_NAMES_CACHE and now - _TASK_CUSTOM_ATTR_NAMES_CACHE[key][0] < TTL:
        return _TASK_CUSTOM_ATTR_NAMES_CACHE[key][1]

    try:
        items = _get_json(ctx, "task-custom-attributes", project_id)
        mapping = {str(item.get("id")): item.get("name") for item in (items or []) if item.get("id") and item.get("name")}
    except requests.RequestException as exc:
        log.warning("Failed to fetch task custom attribute definitions for project %s: %s", project_id, exc)
        mapping = {}

    _TASK_CUSTOM_ATTR_NAMES_CACHE[key] = (now, mapping)
    return mapping


def _task_custom_values(ctx: TaigaContext, project_id: str, task_id: str):
    """Fetch custom attribute values for a task and map IDs to attribute names."""
    if not project_id or not task_id:
        return {}

    try:
        js = _get_json(ctx, f"tasks/custom-attributes-values/{task_id}", project_id)
        raw_values = (js or {}).get("attributes_values") or {}
    except requests.RequestException as exc:
        log.warning("Failed to fetch custom values for task %s in project %s: %s", task_id, project_id, exc)
        return {}

    names = _task_custom_attribute_names(ctx, project_id)
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

    ctx = _taiga_context(prj)
    if ctx is None:
        return {}

    key = (ctx.api_url, project_id, milestone_id)
    now = datetime.now(timezone.utc)
    if key in _DETAILS_CACHE and now - _DETAILS_CACHE[key][0] < TTL:
        return _DETAILS_CACHE[key][1]

    try:
        js = _get_json(ctx, f"milestones/{milestone_id}", project_id)
    except TAIGA_LOOKUP_ERRORS as exc:
        logger.warning(
            "Failed to fetch milestone details for project %s milestone %s: %s",
            project_id,
            milestone_id,
            exc,
        )
        return {}

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

    ctx = _taiga_context(prj)
    if ctx is None:
        return {}

    key = (ctx.api_url, project_id, userstory_id)
    now = datetime.now(timezone.utc)
    if key in _USERSTORY_CACHE and now - _USERSTORY_CACHE[key][0] < TTL:
        return _USERSTORY_CACHE[key][1]

    try:
        js = _get_json(ctx, f"userstories/{userstory_id}", project_id)
    except TAIGA_LOOKUP_ERRORS as exc:
        logger.warning(
            "Failed to fetch user story details for project %s user story %s: %s",
            project_id,
            userstory_id,
            exc,
        )
        return {}

    custom_values = js.get("custom_attributes_values") or _userstory_custom_values(ctx, project_id, userstory_id)
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

    ctx = _taiga_context(prj)
    if ctx is None:
        return {}

    try:
        js = _get_json(ctx, f"tasks/{task_id}", project_id)
    except requests.RequestException as exc:
        log.warning("Failed to fetch task %s in project %s: %s", task_id, project_id, exc)
        return {}

    custom_values = js.get("custom_attributes_values") or _task_custom_values(ctx, project_id, task_id)
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

    ctx = _taiga_context(prj)
    if ctx is None:
        return _empty_stats()

    key = (ctx.api_url, project_id, milestone_id)
    now = datetime.now(timezone.utc)
    if key in _CACHE and now - _CACHE[key][0] < TTL:
        return _CACHE[key][1]

    try:
        js = _get_json(ctx, f"milestones/{milestone_id}/stats", project_id)
    except TAIGA_LOOKUP_ERRORS as exc:
        logger.warning(
            "Failed to fetch milestone stats for project %s milestone %s: %s",
            project_id,
            milestone_id,
            exc,
        )
        return _empty_stats()

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
