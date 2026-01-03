import requests
from datetime import datetime, timedelta
from utils.taiga_token.taiga_auth import get_taiga_token
from config.credentials_loader import resolve

_CACHE = {}                 # key = (project_id, milestone_id) -> (timestamp, stats)
TTL    = timedelta(minutes=1) # Cache time-to-live, set to 5 minutes. Means that if the same request is made within 5 minutes, it will return the cached result instead of making a new API call.

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

    user = resolve(prj, "taiga_user")
    psw  = resolve(prj, "taiga_password")
    print(user, psw)
    if user and psw:
        token = get_taiga_token(user, psw)
        headers = {"Authorization": f"Bearer {token}"}
        print("Using Taiga credentials for project:", prj)
    else:
        headers = {}
        print("Warning: No Taiga credentials found for project:", prj)
    
    url = f"https://api.taiga.io/api/v1/milestones/{milestone_id}/stats"
    r   = requests.get(url, params={"project": project_id}, headers=headers, timeout=(1, 5))
    
    try:
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"Warning: Failed to fetch milestone stats (status {r.status_code}): {e}")
        # Return empty stats if we can't access the milestone
        stats = {
            "milestone_total_points"         : 0,
            "milestone_closed_points"        : 0,
            "milestone_total_userstories"    : 0,
            "milestone_completed_userstories": 0,
            "milestone_total_tasks"          : 0,
            "milestone_completed_tasks"      : 0,
        }
        _CACHE[key] = (now, stats)
        return stats
    
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