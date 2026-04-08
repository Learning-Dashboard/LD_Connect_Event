import requests
from datetime import datetime, timedelta
from utils.taiga_token.taiga_auth import get_taiga_token
from config.credentials_loader import resolve
from config.settings import TAIGA_API_URL

_CACHE = {}                 # key = (project_id, milestone_id) -> (timestamp, stats)
_DETAILS_CACHE = {}         # key = (project_id, milestone_id) -> (timestamp, details)
_USERSTORY_CACHE = {}       # key = (project_id, userstory_id) -> (timestamp, details)
TTL    = timedelta(minutes=1) # Cache time-to-live, set to 5 minutes. Means that if the same request is made within 5 minutes, it will return the cached result instead of making a new API call.


def _build_taiga_headers(prj: str):
    """Return the Taiga headers needed for public and private deployments."""
    if "api.taiga.io" in TAIGA_API_URL:
        user = resolve(prj, "taiga_user")
        psw = resolve(prj, "taiga_password")
        if user and psw:
            token = get_taiga_token(user, psw)
            return {"Authorization": f"Bearer {token}"}
    return {}


def milestone_details(project_id: str, milestone_id: str, prj: str):
    """
    Fetches the milestone metadata from Taiga.
    Returns the raw milestone fields needed to enrich recovery documents.
    """
    if not project_id or not milestone_id:
        return {}

    key = (project_id, milestone_id)
    now = datetime.utcnow()
    if key in _DETAILS_CACHE and now - _DETAILS_CACHE[key][0] < TTL:
        return _DETAILS_CACHE[key][1]

    headers = _build_taiga_headers(prj)
    url = f"{TAIGA_API_URL}/milestones/{milestone_id}"
    r = requests.get(url, params={"project": project_id}, headers=headers, timeout=(1, 5))
    r.raise_for_status()

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
    """
    if not project_id or not userstory_id:
        return {}

    key = (project_id, userstory_id)
    now = datetime.utcnow()
    if key in _USERSTORY_CACHE and now - _USERSTORY_CACHE[key][0] < TTL:
        return _USERSTORY_CACHE[key][1]

    headers = _build_taiga_headers(prj)
    url = f"{TAIGA_API_URL}/userstories/{userstory_id}"
    r = requests.get(url, params={"project": project_id}, headers=headers, timeout=(1, 5))
    r.raise_for_status()

    js = r.json()
    details = {
        "userstory_is_closed": (js.get("status_extra_info") or {}).get("is_closed"),
    }
    _USERSTORY_CACHE[key] = (now, details)
    return details

def milestone_stats(project_id: str, milestone_id: str, prj: str):
    '''
    Fetches the statistics of a milestone in a Taiga project. 
    Uses caching to avoid frequent API calls to get the taiga token.
    It refreshes the cache every 5 minutes.
    '''
    if not project_id or not milestone_id:
        return {}

    key = (project_id, milestone_id)
    now = datetime.utcnow()
    if key in _CACHE and now - _CACHE[key][0]< TTL:
        return _CACHE[key][1]

    headers = _build_taiga_headers(prj)
    
    url = f"{TAIGA_API_URL}/milestones/{milestone_id}/stats"
    r   = requests.get(url, params={"project": project_id}, headers=headers, timeout=(1, 5))
    r.raise_for_status()  # Raises an exception if the request failed
    
    js  = r.json()
    stats = {
        "milestone_total_points"         : sum(js.get("total_points", {}).values()),
        "milestone_closed_points"        : sum(js.get("completed_points", 0)),
        "milestone_total_userstories"    : js.get("total_userstories", 0),
        "milestone_completed_userstories": js.get("completed_userstories", 0),
        "milestone_total_tasks"          : js.get("total_tasks", 0),
        "milestone_completed_tasks"      : js.get("completed_tasks", 0),
    }
    _CACHE[key] = (now, stats)
    return stats