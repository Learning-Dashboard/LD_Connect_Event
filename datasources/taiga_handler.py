from typing import Dict
import re

from datasources.requests.taiga_api_call import milestone_stats
from utils.datetime_utils import to_madrid_local


def parse_taiga_event(raw_payload: Dict, prj: str) -> Dict:
    """
    Parse a taiga event payload into a more detailed structure.
    The webhook has tells you the type of event.
    We can handle "issues", "epics", "tasks" and "userstories" events.
    """
    event_type = raw_payload.get("type")
    if event_type == "issue":
        return parse_taiga_issue_event(raw_payload)
    elif event_type == "epic":
        return parse_taiga_epic_event(raw_payload, prj)
    elif event_type == "task":
        return parse_taiga_task_event(raw_payload, prj)
    elif event_type == "userstory":
        return parse_taiga_userstory_event(raw_payload, prj)
    elif event_type == "relateduserstory":
        return parse_taiga_related_userstory_event(raw_payload, prj)
    else:
        return {"event": event_type, "error": "Unsupported event type"}


def parse_taiga_issue_event(raw_payload: Dict) -> Dict:
    """
    Function to parse a taiga issue event payload.
    """
    # Extract the relevant fields from the raw payload
    project_id = raw_payload.get("data", {}).get("project", {}).get("id", "")
    issue_id = raw_payload.get("data", {}).get("id", "")
    team_name = raw_payload.get("data", {}).get("project", {}).get("name", "")
    event_type = raw_payload.get("type", "")
    action_type = raw_payload.get("action", "")
    subject = raw_payload.get("data", {}).get("subject", "")
    due_date = to_madrid_local(raw_payload.get("data", {}).get("due_date", ""))
    description = raw_payload.get("data", {}).get("description", "")
    severity = raw_payload.get("data", {}).get("severity", {}).get("name", "")
    status = raw_payload.get("data", {}).get("status", {}).get("name", "")
    priority = raw_payload.get("data", {}).get("priority", {}).get("name", "")
    type = raw_payload.get("data", {}).get("type", {}).get("name", "")
    is_closed = raw_payload.get("is_closed", False)
    modified_date = to_madrid_local(
        raw_payload.get("data", {}).get("modified_date", "")
    )
    created_date = to_madrid_local(raw_payload.get("data", {}).get("created_date", ""))
    finished_date = to_madrid_local(
        raw_payload.get("data", {}).get("finished_date", "")
    )
    assigned_by = raw_payload.get("by", {}).get("username", "")
    # There are cases where the assigned_to field is empty, and if we request it aniways it will throw an error, so we need to check if it exists
    if raw_payload.get("data", {}).get("assigned_to", {}) is not None:
        assigned_to = (
            raw_payload.get("data", {}).get("assigned_to", {}).get("username", "")
        )
    else:
        assigned_to = None

    # Create a dictionary with all the attributes of the issue
    doc = {
        "project_id": project_id,
        "team_name": team_name,
        "event_type": event_type,
        "action_type": action_type,
        "issue_id": issue_id,
        "subject": subject,
        "description": description,
        "due_date": due_date,
        "severity": severity,
        "status": status,
        "priority": priority,
        "type": type,
        "is_closed": is_closed,
        "modified_date": modified_date,
        "created_date": created_date,
        "finished_date": finished_date,
        "assigned_by": assigned_by,
        "assigned_to": assigned_to,
    }
    # Return the parsed issue data as a dictionary
    return doc


def parse_taiga_epic_event(raw_payload: Dict, prj: str) -> Dict:
    """
    Function to parse a taiga epic event payload.
    """
    # Extract the relevant fields from the raw payload
    epic_id = raw_payload.get("data", {}).get("id", "")
    team_name = raw_payload.get("data", {}).get("project", {}).get("name", "")
    event_type = raw_payload.get("type", "")
    action_type = raw_payload.get("action", "")
    subject = raw_payload.get("data", {}).get("subject", "")
    status = raw_payload.get("data", {}).get("status", {}).get("name", "")
    is_closed = raw_payload.get("is_closed", False)
    modified_date = to_madrid_local(
        raw_payload.get("data", {}).get("modified_date", "")
    )
    created_date = to_madrid_local(raw_payload.get("data", {}).get("created_date", ""))
    assigned_by = raw_payload.get("by", {}).get("username", "")
    # We are going to use this project_id to delete the webhooks with the TAIGA API
    project_id = raw_payload.get("data", {}).get("project", {}).get("id", "")

    # Create a dictionary with all the attributes of the epic
    doc = {
        "epic_id": epic_id,
        "team_name": team_name,
        "assigned_by": assigned_by,
        "event_type": event_type,
        "action_type": action_type,
        "subject": subject,
        "is_closed": is_closed,
        "status": status,
        "modified_date": modified_date,
        "created_date": created_date,
        "project_id": project_id,
    }
    # Return the parsed epic data as a dictionary
    return doc


def parse_taiga_task_event(raw_payload: Dict, prj: str) -> Dict:
    """
    Function to parse a taiga task event payload.
    """
    # Extract the relevant fields from the raw payload
    project_id = raw_payload.get("data", {}).get("project", {}).get("id", "")
    team_name = raw_payload.get("data", {}).get("project", {}).get("name", "")
    event_type = raw_payload.get("type", "")
    action_type = raw_payload.get("action", "")
    task_id = raw_payload.get("data", {}).get("id", "")
    subject = raw_payload.get("data", {}).get("subject", "")
    userstory_id = raw_payload.get("data", {}).get("user_story", {}).get("id", "")
    userstory_is_closed = (
        raw_payload.get("data", {}).get("user_story", {}).get("is_closed", "")
    )
    is_closed = raw_payload.get("data", {}).get("status", {}).get("is_closed", "")
    status = raw_payload.get("data", {}).get("status", {}).get("name", "")
    created_date = to_madrid_local(raw_payload.get("data", {}).get("created_date", ""))
    modified_date = to_madrid_local(
        raw_payload.get("data", {}).get("modified_date", "")
    )
    finished_date = to_madrid_local(
        raw_payload.get("data", {}).get("finished_date", "")
    )
    reference = raw_payload.get("data", {}).get("ref", "")
    milestone_id = raw_payload.get("data", {}).get("milestone", {}).get("id", "")
    milestone_name = raw_payload.get("data", {}).get("milestone", {}).get("name", "")
    milestone_closed = (
        raw_payload.get("data", {}).get("milestone", {}).get("closed", "")
    )
    milestone_created_date = (
        raw_payload.get("data", {}).get("milestone", {}).get("created_date", "")
    )
    milestone_created_date = (
        to_madrid_local(milestone_created_date) if milestone_created_date else ""
    )
    milestone_modified_date = (
        raw_payload.get("data", {}).get("milestone", {}).get("modified_date", "")
    )
    milestone_modified_date = (
        to_madrid_local(milestone_modified_date) if milestone_modified_date else ""
    )
    estimated_start = to_madrid_local(
        raw_payload.get("data", {}).get("milestone", {}).get("estimated_start", "")
    )
    estimated_finish = to_madrid_local(
        raw_payload.get("data", {}).get("milestone", {}).get("estimated_finish", "")
    )
    assigned_by = raw_payload.get("by", {}).get("username", "")

    milestone_data = milestone_stats(project_id, milestone_id, prj)
    # If someone defines a new metric, if it isnt listed in the handler, we wont get it. To solve we can get all the custom attributes as an object and store it in mongo
    custom_attributes = raw_payload.get("data", {}).get("custom_attributes_values", {})
    if custom_attributes is None:
        custom_attributes = {}

    # There are cases where the assigned_to field is empty, and if we request it aniways it will throw an error, so we need to check if it exists
    if raw_payload.get("data", {}).get("assigned_to", {}) is not None:
        assigned_to = (
            raw_payload.get("data", {}).get("assigned_to", {}).get("username", "")
        )
    else:
        assigned_to = None

    # Create a dictionary with all the attributes of the task
    doc = {
        "project_id": project_id,
        "team_name": team_name,
        "event_type": event_type,
        "action_type": action_type,
        "subject": subject,
        "task_id": task_id,
        "userstory_id": userstory_id,
        "userstory_is_closed": userstory_is_closed,
        "is_closed": is_closed,
        "status": status,
        "assigned_to": assigned_to,
        "assigned_by": assigned_by,
        "created_date": created_date,
        "modified_date": modified_date,
        "finished_date": finished_date,
        "reference": reference,
        "milestone_id": milestone_id,
        "milestone_name": milestone_name,
        "milestone_closed": milestone_closed,
        "milestone_created_date": milestone_created_date,
        "milestone_modified_date": milestone_modified_date,
        "estimated_start": estimated_start,
        "estimated_finish": estimated_finish,
        # We can get all the custom attributes like an object, but in mongo they will have the name defined in taiga.
        "custom_attributes": custom_attributes,
    }
    doc.update(milestone_data)
    # Return the parsed task data as a dictionary
    return doc


# Most fields dont appear when creating the user story from zero, they appear once we link it to an epic
def parse_taiga_userstory_event(raw_payload: Dict, prj: str) -> Dict:
    """
    Function to parse a taiga userstory event payload.
    """
    # Extract the relevant fields from the raw payload
    project_id = raw_payload.get("data", {}).get("project", {}).get("id", "")
    userstory_id = raw_payload.get("data", {}).get("id", "")
    team_name = raw_payload.get("data", {}).get("project", {}).get("name", "")
    event_type = raw_payload.get("type", "")
    action_type = raw_payload.get("action", "")
    subject = raw_payload.get("data", {}).get("subject", "")
    status = raw_payload.get("data", {}).get("status", {}).get("name", "")
    is_closed = raw_payload.get("is_closed", False)
    modified_date = to_madrid_local(
        raw_payload.get("data", {}).get("modified_date", "")
    )
    created_date = to_madrid_local(raw_payload.get("data", {}).get("created_date", ""))
    assigned_by = raw_payload.get("by", {}).get("username", "")
    # Extract all the custom attributes from the payload, if they exist
    custom_attributes = raw_payload.get("data", {}).get("custom_attributes_values", {})
    if custom_attributes is None:
        custom_attributes = {}

    description = raw_payload.get("data", {}).get("description", "")
    # If the pattern "AS - A - I WANT - SO THAT" is used in the description, the vañue of pattern will be True, if not, it will be False
    pattern = r"as\s+(.*?)\s+i want\s+(.*?)\s+so that\s+(.*)"
    match = re.search(pattern, description, re.IGNORECASE)
    if match:
        pattern_in_description = True
    else:
        pattern_in_description = False

    # If the userstory has a milestone associated while created, we will get the values, if not, we will set them to None
    if raw_payload.get("data", {}).get("milestone", {}) is not None:

        milestone_id = raw_payload.get("data", {}).get("milestone", {}).get("id", "")
        milestone_name = (
            raw_payload.get("data", {}).get("milestone", {}).get("name", "")
        )
        milestone_closed = (
            raw_payload.get("data", {}).get("milestone", {}).get("closed", "")
        )
        milestone_created_date = to_madrid_local(
            raw_payload.get("data", {}).get("milestone", {}).get("created_date", "")
        )
        milestone_modified_date = to_madrid_local(
            raw_payload.get("data", {}).get("milestone", {}).get("modified_date", "")
        )
        milestone_modified_date = (
            to_madrid_local(milestone_modified_date) if milestone_modified_date else ""
        )
        estimated_start = to_madrid_local(
            raw_payload.get("data", {}).get("milestone", {}).get("estimated_start", "")
        )
        estimated_finish = to_madrid_local(
            raw_payload.get("data", {}).get("milestone", {}).get("estimated_finish", "")
        )

        milestone_data = milestone_stats(project_id, milestone_id, prj)

    else:
        milestone_id = ""
        milestone_name = ""
        milestone_closed = ""
        milestone_created_date = ""
        milestone_modified_date = ""
        estimated_start = ""
        estimated_finish = ""
        milestone_data = {}

    priority = custom_attributes.get("Priority", "")
    points_list = raw_payload.get("data", {}).get("points", [])
    sum_points = sum(p.get("value") or 0 for p in points_list)

    # Create a dictionary with all the attributes of the user story
    doc = {
        "project_id": project_id,
        "team_name": team_name,
        "event_type": event_type,
        "action_type": action_type,
        "subject": subject,
        "userstory_id": userstory_id,
        "is_closed": is_closed,
        "status": status,
        "created_date": created_date,
        "modified_date": modified_date,
        "total_points": sum_points,
        "assigned_by": assigned_by,
        "milestone_id": milestone_id,
        "milestone_name": milestone_name,
        "milestone_closed": milestone_closed,
        "milestone_created_date": milestone_created_date,
        "milestone_modified_date": milestone_modified_date,
        "estimated_start": estimated_start,
        "estimated_finish": estimated_finish,
        # We can get all the custom attributes like an object, but in mongo they will have the name defined in taiga.
        "custom_attributes": custom_attributes,
        # "acceptance_criteria": acceptance_criteria, #TRUE IF THE USER STORY HAS ACCEPTANCE CRITERIA
        "pattern": pattern_in_description,
        "priority": priority,
    }

    doc.update(milestone_data)
    # Return the parsed user story data as a dictionary
    return doc


def parse_taiga_related_userstory_event(raw_payload: Dict, prj: str) -> Dict:
    """
    Function to parse a taiga related userstory event payload.
    This related userstory event is triggered when a user story is linked to an epic.
    """
    # Extract the relevant fields from the raw payload
    userstory_id = raw_payload.get("data", {}).get("user_story", {}).get("id", "")
    team_name = (
        raw_payload.get("data", {}).get("epic", {}).get("project", {}).get("name", "")
    )
    event_type = raw_payload.get("type", "")
    finished_date = to_madrid_local(
        raw_payload.get("data", {}).get("finished_date", "")
    )
    assigned_to = raw_payload.get("data", {}).get("assigned_to", {}).get("username", "")
    epic_id = raw_payload.get("data", {}).get("epic", {}).get("id", "")
    epic_name = raw_payload.get("data", {}).get("epic", {}).get("subject", "")
    reference = raw_payload.get("data", {}).get("epic", {}).get("ref", "")
    assigned_by = raw_payload.get("by", {}).get("username", "")

    # Create a dictionary with all the attributes of the user story
    doc = {
        "id": userstory_id,
        "team_name": team_name,
        "event_type": event_type,
        "epic_id": epic_id,
        "epic_name": epic_name,
        "reference": reference,
        "finished_date": finished_date,
        "assigned_to": assigned_to,
        "assigned_by": assigned_by,
    }
    # Return the parsed user story data as a dictionary
    return doc
