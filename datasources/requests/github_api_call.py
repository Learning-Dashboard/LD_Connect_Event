# helpers/github_stats.py
import logging
from typing import Dict
import requests
from requests.adapters import HTTPAdapter
from config.credentials_loader import resolve
from config.settings import GITHUB_API_URL

logger = logging.getLogger(__name__)

_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=5, pool_maxsize=10)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)


def fetch_commit_stats(
    repo_full_name: str, commit_sha: str, prj: str
) -> Dict[str, int]:
    """
    Gets 'additions', 'deletions' y 'total' of a commit using GitHub's REST API v3.
    """

    token = resolve(prj, "github_token")

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }

    url = f"{GITHUB_API_URL}/repos/{repo_full_name}/commits/{commit_sha}"

    try:
        response = _session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        stats = data.get("stats", {})
        parents = data.get("parents", [])
        return {
            "total": stats.get("total", 0),
            "additions": stats.get("additions", 0),
            "deletions": stats.get("deletions", 0),
            "is_merge": len(parents) >= 2,
        }
    except Exception as exc:
        logger.error(
            "Error fetching commit stats for %s/%s: %s", repo_full_name, commit_sha, exc
        )
        return {"total": 0, "additions": 0, "deletions": 0, "is_merge": False}
