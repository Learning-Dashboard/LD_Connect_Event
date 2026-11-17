import logging
import pymongo
import requests
from config.credentials_loader import (
    CredentialsConfigError,
    ProjectCredentialsNotFoundError,
    TaigaContext,
    get_taiga_context,
)
from config.settings import MONGO_URI, MONGO_DB
from utils.taiga_token.taiga_auth import auth_headers

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 10
COLLECTION_PREFIX = "taiga_"
COLLECTION_SUFFIX = ".epics"


# We define two functions to list and delete the webhooks using the API of taiga.
# The first function lists all the webhooks created on a project, we need the project id
# and the Taiga context (server and credentials) of the subject the team belongs to.
def list_taiga_hooks(project_id, ctx: TaigaContext):
    url = f"{ctx.api_url}/webhooks"
    resp = requests.get(
        url,
        params={"project": project_id},
        headers=auth_headers(ctx),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# The second function deletes a webhook, we need the id of the webhook to delete
# and the Taiga context (server and credentials) of the subject the team belongs to.
def delete_taiga_hook(hook_id, ctx: TaigaContext):
    url = f"{ctx.api_url}/webhooks/{hook_id}"
    resp = requests.delete(url, headers=auth_headers(ctx), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp


def delete_all_taiga_webhooks(webhook_url_taiga):

    mongo_client = pymongo.MongoClient(MONGO_URI)  # URI to connect to the database
    db = mongo_client[MONGO_DB]  # Name of the database

    # We get the epics collection of every team (taiga_<prj>.epics). From them we will extract the projectsid of all the taiga projects active.
    all_collections = db.list_collection_names()
    taiga_collections = [
        c
        for c in all_collections
        if c.startswith(COLLECTION_PREFIX) and c.endswith(COLLECTION_SUFFIX)
    ]

    # We iterate over the collections and the projects to delete the webhooks
    # Each team can live on a different Taiga server, so we resolve the server of the team first
    for col_name in taiga_collections:
        prj = col_name[len(COLLECTION_PREFIX) : -len(COLLECTION_SUFFIX)]
        try:
            ctx = get_taiga_context(prj)
        except (CredentialsConfigError, ProjectCredentialsNotFoundError) as e:
            logger.warning("Skipping taiga hooks of team %s: %s", prj, e)
            continue

        distinct_project_ids = db[col_name].distinct("project_id")

        for project_id in distinct_project_ids:
            try:
                hooks = list_taiga_hooks(project_id, ctx)
            except requests.RequestException as e:
                logger.error(
                    "Error listing taiga hooks for project %s of team %s: %s",
                    project_id,
                    prj,
                    e,
                )
                continue

            logger.info("Found %d hooks for project %s", len(hooks), project_id)
            for hook in hooks:
                logger.debug("Hook: %s", hook)
                if hook["url"] == webhook_url_taiga:
                    try:
                        delete_taiga_hook(hook["id"], ctx)
                        logger.info(
                            "Deleted taiga hook %s from project %s",
                            hook["id"],
                            project_id,
                        )
                    except requests.HTTPError as e:
                        logger.error("Error deleting taiga hook %s: %s", hook["id"], e)
