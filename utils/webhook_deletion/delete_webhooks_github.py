import logging
import pymongo
import requests
from config.credentials_loader import (
    CredentialsConfigError,
    ProjectCredentialsNotFoundError,
    get_github_token,
)
from config.settings import (
    MONGO_URI,
    MONGO_DB,
    GITHUB_API_URL,
)

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 10
COLLECTION_PREFIX = "github_"
COLLECTION_SUFFIX = ".commits"


def _headers(token) -> dict:
    return {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}",
    }


def list_github_hooks(owner, repo, token) -> list:
    """
    The function lists all the webhooks created on a specific repository, we need the owner and the repository name.
    Also a owner or admin token is needed to authenticate the request: the GitHub token of the subject the team belongs to.

    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/hooks"
    resp = requests.get(url, headers=_headers(token), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def delete_github_hook(owner, repo, hook_id, token):
    """
    This function deletes a specific webhook, we need the owner, the repository name and the id of the webhook to delete.
    Also a owner or admin token is needed to authenticate the request: the GitHub token of the subject the team belongs to.
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/hooks/{hook_id}"
    resp = requests.delete(url, headers=_headers(token), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp


def delete_all_github_webhooks(webhook_url_github):
    """
    This function deletes all the webhooks created on the repositories of the database.
    """
    mongo_client = pymongo.MongoClient(MONGO_URI)  # URI to connect to the database
    db = mongo_client[MONGO_DB]  # Name of the database
    # We get the commits collection of every team (github_<prj>.commits). From them we will extract the repositories names and owners.
    all_collections = db.list_collection_names()
    github_commit_collections = [
        c
        for c in all_collections
        if c.startswith(COLLECTION_PREFIX) and c.endswith(COLLECTION_SUFFIX)
    ]

    # We iterate over the collections and the repositories to delete the webhooks
    # Each subject has its own GitHub token, so we resolve the token of the team first
    for col_name in github_commit_collections:
        prj = col_name[len(COLLECTION_PREFIX) : -len(COLLECTION_SUFFIX)]
        try:
            token = get_github_token(prj)
        except (CredentialsConfigError, ProjectCredentialsNotFoundError) as e:
            logger.warning("Skipping github hooks of team %s: %s", prj, e)
            continue

        distinct_repos = db[col_name].distinct("repository")

        for repo_full_name in distinct_repos:
            owner, repo = repo_full_name.split("/")
            try:
                hooks = list_github_hooks(owner, repo, token)
                logger.info("Found %d hooks for %s/%s", len(hooks), owner, repo)
            except requests.HTTPError as e:
                logger.error("Error listing hooks for %s/%s: %s", owner, repo, e)
                continue

            for hook in hooks:
                config_url = hook.get("config", {}).get("url", "")
                hook_id = hook.get("id")

                if config_url == webhook_url_github:
                    # Delete it
                    try:
                        delete_github_hook(owner, repo, hook_id, token)
                        logger.info("Deleted hook %s for %s/%s", hook_id, owner, repo)
                    except requests.HTTPError as e:
                        logger.error(
                            "Error deleting hook %s for %s/%s: %s",
                            hook_id,
                            owner,
                            repo,
                            e,
                        )
