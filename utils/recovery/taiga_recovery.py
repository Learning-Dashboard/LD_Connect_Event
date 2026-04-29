import argparse
import requests
from pymongo import UpdateOne
from datetime import datetime, timezone
from typing import Optional, Dict, List
from dateutil import tz, parser as dtparser  # pip install python-dateutil
import logging

from database.mongo_client import get_collection
from routes.API_publisher.API_event_publisher import notify_eval_push
from config.logger_config import setup_logging

from config.settings import TAIGA_API_URL, TAIGA_TOKEN, TAIGA_USERNAME, TAIGA_PASSWORD
from utils.taiga_token.taiga_auth import get_taiga_token

from utils.pattern_detector import PatternDetector
from datasources.requests.taiga_api_call import milestone_details, milestone_stats, userstory_details, task_details
from datasources.requests.taiga_api_call import push_taiga_token_override, pop_taiga_token_override, _auth_header

setup_logging()
logger = logging.getLogger(__name__)
ACCEPTANCE_CRITERIA_KEY = "Acceptance Criteria"


def collection_name_for_event(prj: str, event: str) -> str:
    if event == "userstory":
        return f"taiga_{prj}.userstories"
    if event == "task":
        return f"taiga_{prj}.tasks"
    if event == "epic":
        return f"taiga_{prj}.epics"
    return f"taiga_{prj}.{event}"


def first_non_empty(*values, default=""):
    for value in values:
        if value not in (None, ""):
            return value
    return default



def parse_dt(s: str) -> datetime:
    """Accepts ‘2025-05-01’, ‘2025-05-01T14:30’, etc. And returns the datetime tz-aware (Madrid)."""
    d = dtparser.isoparse(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=tz.gettz("Europe/Madrid"))
    return d


# Functions to interact with Taiga API
def get_username_id(token: str) -> int:
    """
    Given a Taiga API token, return the user ID of the authenticated user.
    With this ID we canfind the projects that the user is a member of.
    """
    h = _auth_header(token)
    r = requests.get(f"{TAIGA_API_URL}/users/me", headers=h, timeout=10)
    r.raise_for_status()
    return r.json()["id"]


def get_project_id_by_slug(slug: str, token: Optional[str] = None) -> int:
    """Resolve Taiga project ID from slug without authentication (public projects)."""
    url = f"{TAIGA_API_URL}/projects/by_slug"
    headers = _auth_header(token) if token else {}
    r = requests.get(url, params={"slug": slug}, headers=headers, timeout=10)
    if r.status_code == 200:
        return r.json()["id"]
    if r.status_code in (401, 403):
        raise SystemExit(
            f"Project ‘{slug}’ is private. Provide credentials or make it public."
        )
    if r.status_code == 404:
        raise SystemExit(f"Project slug ‘{slug}’ not found.")
    r.raise_for_status()
    assert False  # pragma: no cover


def get_project_id_by_username_id(project_name: str, token: str) -> int:
    """
    Given a project name and a Taiga API token, return the project ID.
    With the projecta ID we can fetch the entities (tasks, issues, etc.) of the project.
    """
    h = _auth_header(token)
    uid = get_username_id(token)
    r = requests.get(
        f"{TAIGA_API_URL}/projects",
        headers=h,
        params={"member": uid},
        timeout=10,
    )
    r.raise_for_status()
    for p in r.json():
        if p["name"].lower() == project_name.lower():
            return p["id"]
    raise SystemExit(f"Project named «{project_name}» is not under the introduced user")


def fetch_entities(
    entity: str,
    project: int,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    token: Optional[str] = None,
) -> List[Dict]:
    """
    Given an entity type (tasks, issues, epics, userstories), a project ID, and a token, the function fetches the entities from the Taiga API.
    The start and end parameters are optional and can be used to filter the entities by creation date.

    """
    if entity not in ENTITY_ENDPOINT:
        raise ValueError(f"Not supported type: {entity}")

    endpoint_path = ENTITY_ENDPOINT[entity][0]
    headers = {
        "x-disable-pagination": "True",
    }
    if token:
        headers.update(_auth_header(token))
    params = {"project": project}
    if start:
        params["modified_date__gte"] = (
            start.astimezone(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )  # See if there is a start date to fetch data, if there is add it to the params
    if end:
        params["modified_date__lte"] = (
            end.astimezone(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )  # See if there is a end date to fetch data, if there is add it to the params

    r = requests.get(
        f"{TAIGA_API_URL}/{endpoint_path}",
        headers=headers,
        params=params,
        timeout=30,
    )  # In the request we add the headers and params
    r.raise_for_status()
    return r.json()


def upsert(coll, docs: list[dict], key: str) -> int:
    """
    Upserts a list of documents into a MongoDB collection.
    """
    if not docs:
        return 0
    operations = [
        UpdateOne({key: d[key]}, {"$set": d}, upsert=True) for d in docs
    ]  # Create a list of UpdateOne operations for each document in the list, using the key to identify the document
    res = coll.bulk_write(operations, ordered=False)
    return res.matched_count + len(res.upserted_ids)


# Converters from API Schema to MongoDB Schema
def task_from_api(j: dict, prj: str) -> dict:
    """
    Converts a task JSON object from the Taiga API to a MongoDB document schema.
    """
    m = j.get("milestone_extra_info") or {}
    project_id = (j.get("project_extra_info") or {}).get("id")
    milestone_id = j.get("milestone")
    milestone_info = milestone_details(project_id, milestone_id, prj)
    milestone_stats_data = milestone_stats(project_id, milestone_id, prj)
    userstory_id = j.get("user_story")
    us = j.get("user_story_extra_info") or {}
    userstory_is_closed = first_non_empty(
        us.get("is_closed"),
        (us.get("status_extra_info") or {}).get("is_closed"),
        default=None,
    )
    userstory_info = {}
    if userstory_id and userstory_is_closed is None:
        userstory_info = userstory_details(project_id, userstory_id, prj)
    task_id = j.get("id")
    task_custom_attrs = j.get("custom_attributes_values") or {}
    task_info = {}
    if task_id and not task_custom_attrs:
        task_info = task_details(project_id, task_id, prj)
    doc = {
        "task_id":        j["id"],
        "action_type":    "import",
        "assigned_by":    "backfill",
        "assigned_to":    (j.get("assigned_to_extra_info") or {}).get("username"),
        "created_date":   j["created_date"],
        "custom_attributes": task_custom_attrs or task_info.get("custom_attributes_values") or {},
        "estimated_finish": first_non_empty(m.get("estimated_finish"), milestone_info.get("estimated_finish")),
        "estimated_start":  first_non_empty(m.get("estimated_start"), milestone_info.get("estimated_start")),
        "event_type":     "task",
        "finished_date":  j["finished_date"],
        "is_closed":      j["status_extra_info"]["is_closed"],
        "milestone_closed": bool(first_non_empty(m.get("closed"), milestone_info.get("milestone_closed"), False)),
        "milestone_created_date": first_non_empty(m.get("created_date"), milestone_info.get("milestone_created_date")),
        "milestone_id":   milestone_id,
        "milestone_modified_date": first_non_empty(m.get("modified_date"), milestone_info.get("milestone_modified_date")),
        "milestone_name": first_non_empty(m.get("name"), milestone_info.get("milestone_name")),
        "modified_date":  j["modified_date"],
        "prj":            prj,
        "reference":      j["ref"],
        "status":         j["status_extra_info"]["name"],
        "subject":        j["subject"],
        "team_name":      j["project_extra_info"]["name"],
        "userstory_id":   j.get("user_story"),
        "userstory_is_closed": first_non_empty(
            userstory_is_closed, userstory_info.get("userstory_is_closed")
        ),
    }
    doc.update(milestone_stats_data)
    return doc



def issue_from_api(j: dict, prj: str) -> dict:
    """
    Converts a isue JSON object from the Taiga API to a MongoDB document schema.
    """
    return {
        "issue_id": j["id"],
        "action_type": "import",
        "assigned_by": "backfill",
        "assigned_to": (j.get("assigned_to_extra_info") or {}).get("username"),
        "created_date": j["created_date"],
        "description": j.get("description"),
        "due_date": j.get("due_date"),
        "event_type": "issue",
        "finished_date": j.get("finished_date"),
        "is_closed": (j.get("status_extra_info") or {}).get("is_closed"),
        "modified_date": j["modified_date"],
        "priority": (j.get("priority_extra_info") or {}).get("name"),
        "prj": prj,
        "severity": (j.get("severity_extra_info") or {}).get("name"),
        "status": (j.get("status_extra_info") or {}).get("name"),
        "subject": j["subject"],
        "team_name": j["project_extra_info"]["name"],
        "type": (j.get("type_extra_info") or {}).get("name"),
    }


def epic_from_api(j: dict, prj: str) -> dict:
    """
    Converts an epic JSON object from the Taiga API to a MongoDB document schema.
    """
    return {
        "epic_id": j["id"],
        "action_type": "import",
        "assigned_by": "backfill",
        "created_date": j["created_date"],
        "event_type": "epic",
        "is_closed": (j.get("status_extra_info") or {}).get("is_closed"),
        "modified_date": j["modified_date"],
        "prj": prj,
        "project_id": j["project_extra_info"]["id"],
        "status": (j.get("status_extra_info") or {}).get("name"),
        "subject": j["subject"],
        "team_name": j["project_extra_info"]["name"],
    }


def userstory_from_api(j: dict, prj: str) -> dict:
    """
    Converts an userstory JSON object from the Taiga API to a MongoDB document schema.
    """
    m = j.get("milestone_extra_info") or {}
    project_id = (j.get("project_extra_info") or {}).get("id")
    milestone_id = j.get("milestone")
    milestone_info = milestone_details(project_id, milestone_id, prj)
    milestone_stats_data = milestone_stats(project_id, milestone_id, prj)
    us_info = userstory_details(project_id, j.get("id"), prj)
    
    # Use custom_attributes from API response, fallback to userstory detail
    custom_attrs = j.get("custom_attributes_values") or us_info.get("custom_attributes_values") or {}
    
    # Normalize Acceptance Criteria: if list, join as string
    if isinstance(custom_attrs.get(ACCEPTANCE_CRITERIA_KEY), list):
        custom_attrs = dict(custom_attrs)  # Make a copy
        ac_list = custom_attrs.get(ACCEPTANCE_CRITERIA_KEY, [])
        custom_attrs[ACCEPTANCE_CRITERIA_KEY] = " | ".join(str(x) for x in ac_list) if ac_list else ""
    
    desc = j.get("description") or us_info.get("description") or ""
    pattern = PatternDetector.detect_pattern(desc)
    
    raw_points = j.get("points")          # puede ser list | "" | None
    if isinstance(raw_points, list):
        total = sum((p.get("value") or 0) for p in raw_points)
    else:
        total = 0

    doc = {
        "userstory_id": j["id"],
        "action_type": "import",
        "assigned_by":   "backfill",
        "created_date":  j["created_date"],
        "custom_attributes": custom_attrs,
        "estimated_finish": first_non_empty(m.get("estimated_finish"), milestone_info.get("estimated_finish")),
        "estimated_start":  first_non_empty(m.get("estimated_start"), milestone_info.get("estimated_start")),
        "event_type":  "userstory",
        "is_closed":   (j.get("status_extra_info") or {}).get("is_closed"),
        "milestone_closed": bool(first_non_empty(m.get("closed"), milestone_info.get("milestone_closed"), False)),
        "milestone_created_date": first_non_empty(m.get("created_date"), milestone_info.get("milestone_created_date")),
        "milestone_id":   milestone_id,
        "milestone_modified_date": first_non_empty(m.get("modified_date"), milestone_info.get("milestone_modified_date")),
        "milestone_name": first_non_empty(m.get("name"), milestone_info.get("milestone_name")),
        "modified_date": j["modified_date"],
        "pattern": pattern,
        "priority": custom_attrs.get("Priority"),
        "prj":         prj,
        "status":      (j.get("status_extra_info") or {}).get("name"),
        "subject":     j["subject"],
        "team_name":   j["project_extra_info"]["name"],
        "total_points":  total,
    }
    doc.update(milestone_stats_data)
    return doc


ENTITY_ENDPOINT = {
    "task":        ("tasks",        task_from_api,        "task_id"),
    "issue":       ("issues",       issue_from_api,       "issue_id"),
    "epic":        ("epics",        epic_from_api,        "epic_id"),
    "userstory":  ("userstories",  userstory_from_api,   "userstory_id"),
    }


def sync_deleted_entities(
    event: str,
    prj: str,
    project_id: int,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    raw_api: Optional[List[Dict]] = None,
    token: Optional[str] = None,
) -> int:
    '''
    Removes from MongoDB documents that no longer exist in the Taiga API.
    This prevents "orphaned" tasks/issues/epics/userstories from inflating metrics after they've been deleted.
    
    Returns the count of deleted documents from MongoDB.
    '''
    if event not in ENTITY_ENDPOINT:
        return 0
    
    _, _, key = ENTITY_ENDPOINT[event]
    
    # Reuse pre-fetched entities when available to avoid duplicate API calls.
    if raw_api is None:
        raw_api = fetch_entities(event, project_id, start, end, token=token)
    api_ids = set(r["id"] for r in raw_api)
    
    # Get the MongoDB collection
    collection_name = f"taiga_{prj}.userstories" if event == "userstory" else f"taiga_{prj}.tasks" if event == "task" else f"taiga_{prj}.epics" if event == "epic" else f"taiga_{prj}.{event}"
    coll = get_collection(collection_name)
    
    # Find all document IDs in MongoDB
    mongo_docs = coll.find({}, {key: 1})
    mongo_ids = set(doc[key] for doc in mongo_docs if key in doc)
    
    # Identify IDs that are in MongoDB but not in the current API response
    deleted_ids = mongo_ids - api_ids
    
    if not deleted_ids:
        return 0
    
    # Delete them from MongoDB
    delete_filter = {key: {"$in": list(deleted_ids)}}
    result = coll.delete_many(delete_filter)
    
    logger.info(f"Removed {result.deleted_count} {event}(s) from MongoDB (no longer in Taiga API)")
    return result.deleted_count





def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(
        description="Back-fill of Taiga for a project, to insert it in MongoDB"
    )
    # ap.add_argument("--project", required=True, help="Name of the project in Taiga")
    ap.add_argument(
        "--slug",
        "--project",
        dest="slug",
        required=True,
        help="Slug públic del projecte a Taiga",
    )
    # ap.add_argument("--project", required=True, help="Name of the project in Taiga")
    ap.add_argument(
        "--prj", required=True, help="External ID of the project in LD-Connect"
    )
    # ap.add_argument("--taiga-user", required=True, help="Username in Taiga of the teacher with acces to all Students Projects")
    # ap.add_argument("--taiga-pass", required=True, help="Password in Taiga of the teacher with acces to all Students Projects")
    ap.add_argument(
        "--events",
        default="task,userstory,issue,epic",
        help="List separated by commas pf the events to backfill, by default: task,userstory,issue,epic",
    )
    ap.add_argument(
        "--from-date",
        help="Date FROM the backfill will be made, must be in format (2025-05-01), can also put a full date with time (2025-05-01T14:30)",
    )
    ap.add_argument(
        "--to-date",
        help="Date UNTIL the backfill will be made, must be in format (2025-05-01), can also put a full date with time (2025-05-01T14:30)",
    )
    ap.add_argument(
        "--quality-model",
        default="default",
        help="Sets the quality model to use for the evaluation, by default: default",
    )
    ap.add_argument(
        "--taiga-token",
        default="",
        help="Optional Taiga token override for private projects and API access",
    )

    ns = ap.parse_args(argv)
    events = [e.strip().lower() for e in ns.events.split(",") if e.strip()]
    start = parse_dt(ns.from_date) if ns.from_date else None
    end = parse_dt(ns.to_date) if ns.to_date else None
    effective_taiga_token = ns.taiga_token or TAIGA_TOKEN or None
    if not effective_taiga_token and TAIGA_USERNAME and TAIGA_PASSWORD:
        try:
            effective_taiga_token = get_taiga_token(TAIGA_USERNAME, TAIGA_PASSWORD)
        except Exception as exc:
            logger.warning("Could not obtain Taiga token from global credentials: %s", exc)

    pid = get_project_id_by_slug(
        ns.slug,
        token=effective_taiga_token,
    )  # Get the project ID using the project name and the token info


    total = 0
    total_deleted = 0
    token_handle = push_taiga_token_override(effective_taiga_token)
    try:
        for event in events: # Iterate over the events to backfill
            endpoint, converter, key = ENTITY_ENDPOINT[event]
            raw = fetch_entities(event, pid, start, end, token=effective_taiga_token)   # Get the raw data from the Taiga API for the event
            docs = [converter(r, ns.prj) for r in raw]        # Convert the raw data to the MongoDB schema using the converter function
            # Usar el nombre plural correcto para la colección de userstories
            collection_name = f"taiga_{ns.prj}.userstories" if event == "userstory" else f"taiga_{ns.prj}.tasks" if event == "task" else f"taiga_{ns.prj}.epics" if event == "epic" else f"taiga_{ns.prj}.{event}"
            coll = get_collection(collection_name)  # Get the MongoDB collection for the event
            n = upsert(coll, docs, key)                        # Upsert the documents
            total += n
            print(f" • {event:<12} → {n:>4} documents")          # Print total number of documments

            # Sync deletions: remove entities that no longer exist in the Taiga API
            deleted_count = sync_deleted_entities(event, ns.prj, pid, start, end, raw_api=raw, token=effective_taiga_token)
            total_deleted += deleted_count

            #COMMUNICATION WITH LD_EVAL USING API
            logger.info(f"Notifying LD_EVAL about event: {event} for team with external_id: {ns.prj} with quality_model: {ns.quality_model}")
            try:
                notify_eval_push(event, ns.prj, "backfill", ns.quality_model)
            except Exception as e:
                logger.error(f"Error notifying LD_EVAL: {e}")
    finally:
        pop_taiga_token_override(token_handle)

    span = "all time" if not (start or end) else \
           f"from {ns.from_date or '…'} to {ns.to_date or '…'}"
    print(f"{total} documents inserted ({span})")
    if total_deleted > 0:
        print(f"{total_deleted} documents deleted (orphaned, no longer in Taiga API)")




if __name__ == "__main__":
    main()

# In order to execute this script: python -m recovery.taiga_recovery --project LD_Test_Project --prj LD_Test_Project
