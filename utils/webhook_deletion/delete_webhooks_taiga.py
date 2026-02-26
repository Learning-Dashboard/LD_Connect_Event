import logging
import pymongo
import requests
from config.settings import MONGO_URI, MONGO_DB, WEBHOOK_URL_TAIGA

logger = logging.getLogger(__name__)



#We define two functions to list and delete the webhooks using the API of github.
#The first function lists all the webhooks created on a repository, we need the owner and the repository name. Also a owner or admin token is needed to authenticate the request.
def list_taiga_hooks(project_id, token):
    url = f"https://api.taiga.io/api/v1/webhooks?project={project_id}"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()

#The second function deletes a webhook, we need the owner, the repository name and the id of the webhook to delete. 
# Also a owner or admin token is needed to authenticate the request.
def delete_taiga_hook(hook_id, token):
    TAIGA_API_URL = "https://api.taiga.io"
    url = f"{TAIGA_API_URL}/api/v1/webhooks/{hook_id}"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    resp = requests.delete(url, headers=headers)
    resp.raise_for_status()
    return resp





def delete_all_taiga_webhooks(token, webhook_url_taiga):
    
    mongo_client = pymongo.MongoClient(MONGO_URI) # URI to connect to the database
    db = mongo_client[MONGO_DB] # Name of the database


    # We get all collections with 'epic' in their name and store them in a list. From them we will extract the projectsid of all the taiga projects active.
    all_collections = db.list_collection_names()
    taiga_collections = [c for c in all_collections if "epic" in c]
    
    #We iterate over the collections and the repositories to delete the webhooks
    #We first get the repositories in the collection and then we get the hooks for each repository
    for col_name in taiga_collections:
        distinct_project_ids = db[col_name].distinct("project_id")
        
        for project_id in distinct_project_ids:
            hooks = list_taiga_hooks(project_id, token)

            logger.info("Found %d hooks for project %s", len(hooks), project_id)
            for hook in hooks:
                logger.debug("Hook: %s", hook)
                if hook["url"] == webhook_url_taiga:
                    try:
                        delete_taiga_hook(hook["id"], token)
                        logger.info("Deleted taiga hook %s from project %s", hook['id'], project_id)
                    except requests.HTTPError as e:
                        logger.error("Error deleting taiga hook %s: %s", hook['id'], e)