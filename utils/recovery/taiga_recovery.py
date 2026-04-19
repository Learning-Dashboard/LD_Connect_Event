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

from config.settings import TAIGA_API_URL

from utils.pattern_detector import PatternDetector
from datasources.requests.taiga_api_call import milestone_details, milestone_stats, userstory_details

setup_logging()
logger = logging.getLogger(__name__)


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
    h = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{TAIGA_API_URL}/users/me", headers=h, timeout=10)
    r.raise_for_status()
    return r.json()["id"]


def get_project_id_by_slug(slug: str) -> int:
    """Resolve Taiga project ID from slug without authentication (public projects)."""
    url = f"{TAIGA_API_URL}/projects/by_slug"
    r = requests.get(url, params={"slug": slug}, timeout=10)
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
    h = {"Authorization": f"Bearer {token}"}
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
        f"https://api.taiga.io/api/v1/{endpoint_path}",
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
    userstory_info = userstory_details(project_id, userstory_id, prj) if userstory_id else {}
    doc = {
        "task_id":        j["id"],
        "action_type":    "import",
        "assigned_by":    "backfill",
        "assigned_to":    (j.get("assigned_to_extra_info") or {}).get("username"),
        "created_date":   j["created_date"],
        "custom_attributes": j.get("custom_attributes_values") or {},
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
        "userstory_is_closed": first_non_empty(us.get("is_closed"), userstory_info.get("userstory_is_closed")),
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
    desc = j.get("description") or ""
    pattern = PatternDetector.detect_pattern(desc)
    raw_points = j.get("points")          # puede ser list | "" | None
    if isinstance(raw_points, list):
        total = sum((p.get("value") or 0) for p in raw_points)
    else:
        total = 0

    doc = {
        "userstory_id": j["id"],
        "action_type": "import",
        "assigned_by": "backfill",
        "created_date": j["created_date"],
        "custom_attributes": j.get("custom_attributes_values") or {},
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
        "priority": (j.get("custom_attributes_values") or {}).get("Priority"),
        "prj": prj,
        "status": (j.get("status_extra_info") or {}).get("name"),
        "subject": j["subject"],
        "team_name": j["project_extra_info"]["name"],
        "total_points": total,
    }
    doc.update(milestone_stats_data)
    return doc


ENTITY_ENDPOINT = {
    "task": ("tasks", task_from_api, "task_id"),
    "issue": ("issues", issue_from_api, "issue_id"),
    "epic": ("epics", epic_from_api, "epic_id"),
    "userstory": ("userstories", userstory_from_api, "userstory_id"),
}


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

    ns = ap.parse_args(argv)
    events = [e.strip().lower() for e in ns.events.split(",") if e.strip()]
    start = parse_dt(ns.from_date) if ns.from_date else None
    end = parse_dt(ns.to_date) if ns.to_date else None

    # Payload with the credentials to get the token
    # payload = {
    #     "username": TAIGA_USERNAME,
    #     "password": TAIGA_PASSWORD,
    #     "type": "normal"
    #     }

    # token  = get_token(payload) #Get the token using the credentials provided in the payload
    # print(f"Using token: {token}") # Print the token to the console, this is for debugging purposes
    pid = get_project_id_by_slug(
        ns.slug
    )  # Get the project ID using the project name and the token info

    total = 0
    for event in events:  # Iterate over the events to backfill
        endpoint, converter, key = ENTITY_ENDPOINT[event]
        raw = fetch_entities(event, pid, start, end)   # Get the raw data from the Taiga API for the event
        docs = [converter(r, ns.prj) for r in raw]        # Convert the raw data to the MongoDB schema using the converter function
        # Usar el nombre plural correcto para la colección de userstories
        collection_name = f"taiga_{ns.prj}.userstories" if event == "userstory" else f"taiga_{ns.prj}.tasks" if event == "task" else f"taiga_{ns.prj}.epics" if event == "epic" else f"taiga_{ns.prj}.{event}"
        coll = get_collection(collection_name)  # Get the MongoDB collection for the event
        n    = upsert(coll, docs, key)                        # Upsert the documents
        total += n
        logger.info(" • %s → %d documents", event, n)

        # COMMUNICATION WITH LD_EVAL USING API
        logger.info(
            f"Notifying LD_EVAL about event: {event} for team with external_id: {ns.prj} with quality_model: {ns.quality_model}"
        )
        try:
            notify_eval_push(event, ns.prj, "backfill", ns.quality_model)
        except Exception as e:
            logger.error(f"Error notifying LD_EVAL: {e}")

    span = (
        "all time"
        if not (start or end)
        else f"from {ns.from_date or '…'} to {ns.to_date or '…'}"
    )
    logger.info("%d documents inserted (%s)", total, span)


if __name__ == "__main__":
    main()

# In order to execute this script: python -m recovery.taiga_recovery --project LD_Test_Project --prj LD_Test_Project
