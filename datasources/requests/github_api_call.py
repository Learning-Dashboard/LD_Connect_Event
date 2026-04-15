# helpers/github_stats.py
from typing import Dict
import requests
from config.credentials_loader import resolve


def fetch_commit_stats(repo_full_name: str, commit_sha: str, prj: str) -> Dict[str, int]:
    """
    Gets 'additions', 'deletions' y 'total' of a commit using GitHub's REST API v3.
    """
    
    token = resolve(prj, "github_token")
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}"
    }


    url = f"https://api.github.com/repos/{repo_full_name}/commits/{commit_sha}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        stats = response.json().get("stats", {})
        return {
            "total": stats.get("total", 0),
            "additions": stats.get("additions", 0),
            "deletions": stats.get("deletions", 0)
        }
    except Exception as exc:
            return {"total": 0, "additions": 0, "deletions": 0}
