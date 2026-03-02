from typing import Dict
import re
from datasources.requests.github_api_call import fetch_commit_stats
from config.credentials_loader import resolve
from utils.datetime_utils import to_madrid_local


def parse_github_event(raw_payload: Dict, prj: str) -> Dict:
    """
    Parse a GitHub event payload into a more detailed structure.
    The webhook has a header "X-GitHub-Event" that tells you the type of event.
    We can handle "push" and "issues" events.
    """
    event_type = raw_payload.get("X-GitHub-Event")
    if event_type == "push":
        return parse_github_push_event(raw_payload, prj)
    elif event_type == "issues":
        return parse_github_issue_event(raw_payload, prj)
    elif event_type == "pull_request":
        return parse_github_pullrequest_event(raw_payload, prj)
    else:
        return {"event": event_type, "ignored": True}


def parse_github_push_event(raw_payload: Dict, prj: str) -> Dict:
    """
    Function to parse a GitHub push event payload.
    """
    event_type = (
        "commit"  # The event type is "push" but we will call it "commit" in our system
    )

    # Retrieve the team name and repo name from the payload
    team_name = raw_payload.get("organization", {}).get("login", "UnknownTeam")
    repo_name = raw_payload["repository"].get("full_name", "unknown-repo")

    # The 'sender' object is at the top level
    sender = raw_payload.get("sender", {})
    sender_info = {
        "id": sender.get("id", ""),
        "login": sender.get("login", ""),
        "url": sender.get("url", ""),
        "type": sender.get("type", ""),
        "site_admin": sender.get("site_admin", False),
    }

    commits_info = []
    # The push event typically has a "commits" array
    for c in raw_payload.get("commits", []):
        # Basic fields from the commit
        commit_sha = c.get("id")
        commit_url = c.get("url", "")
        message = c.get("message", "")
        # get timestamp of comit in the hour in spain
        date = to_madrid_local(c.get("timestamp"))

        # Built author information
        author_login = c.get("author", {}).get("username", "")
        author_name = c.get("author", {}).get("name", "")
        author_email = c.get("author", {}).get("email", "")

        # Compute message stats
        message_char_count = len(message)
        message_word_count = len(message.split())

        # Check if the commit message contains a task reference, it can be in english or catalan, ¿spanish¿ (e.g., "task #123")
        pattern = r"(?i)\b(?:task|tasca)\b(?:\s*#?\s*(\d+))?"
        match = re.search(pattern, message)
        if match:
            task_is_written = True
            task_reference = match.group(1)
            if task_reference is not None:
                task_reference = int(task_reference)
        else:
            task_is_written = False
            task_reference = None

        verified = "false"
        verified_reason = "unsigned"

        commit_stats = fetch_commit_stats(repo_name, commit_sha, prj)

        # Build a final doc for this commit.
        commit_doc = {
            "sha": commit_sha,
            "url": commit_url,
            "user": {
                "login": author_login,
                "name": author_name,
                "email": author_email,
            },
            "repository": repo_name,
            "date": date,  # Local date in Spain
            "message": message,
            "message_char_count": message_char_count,
            "message_word_count": message_word_count,
            "task_is_written": task_is_written,
            "task_reference": task_reference,
            "verified": verified,
            "verified_reason": verified_reason,
            "stats": commit_stats,
        }

        commits_info.append(commit_doc)

    # Finally, return a dict containing the full structure
    return {
        "event": event_type,
        "repo_name": repo_name,
        "team_name": team_name,
        "sender_info": sender_info,
        "commits": commits_info,
    }


def parse_github_issue_event(raw_payload: Dict, prj: str) -> Dict:
    """
    Function to parse a GitHub issue event payload.
    """
    # Retrieve the event information from the payload
    action = raw_payload.get("action", "unknown-action")  # e.g. "issue_opened"
    event_type = "issue"

    # Retrieve the team name and repo name from the payload
    team_name = raw_payload.get("organization", {}).get("login", "UnknownTeam")
    repo_name = raw_payload["repository"].get("full_name", "unknown-repo")

    # sender is the user who performed the action, retrieve their info
    sender = raw_payload.get("sender", {})
    sender_info = {
        "id": sender.get("id", ""),
        "login": sender.get("login", ""),
        "url": sender.get("url", ""),
        "type": sender.get("type", ""),
        "site_admin": sender.get("site_admin", False),
    }

    # The "issue" object is typically raw_payload["issue"]
    issue_data = raw_payload.get("issue", {})
    issue_number = issue_data.get("number", 0)
    issue_title = issue_data.get("title", "")
    issue_state = issue_data.get("state", "")
    issue_body = issue_data.get("body", "")
    issue_user = issue_data.get("user", {})
    issue_user_login = issue_user.get("login", "")
    issue_user_id = issue_user.get("id", "")

    # We can store relevant info about the issue as a dictionary
    issue_obj = {
        "number": issue_number,
        "title": issue_title,
        "state": issue_state,
        "body": issue_body,
        "user": {"login": issue_user_login, "id": issue_user_id},
    }

    # Finally, return a dict containing the full structure
    return {
        "event": event_type,
        "action": action,
        "repo_name": repo_name,
        "team_name": team_name,
        "sender_info": sender_info,
        "issue": issue_obj,
    }


def parse_github_pullrequest_event(raw_payload: Dict, prj: str) -> Dict:
    """
    Function to parse a GitHub pull request event payload.
    """

    action = raw_payload.get("action")

    if action != "closed":  # we only want to process closed pull requests
        return {"event": "pull_request", "ignored": True}

    event_type = "pull_request"  # The event type is "pull request" but we will call it "commit" in our system

    # The 'sender' object is at the top level
    sender = raw_payload.get("sender", {})
    sender_info = {
        "id": sender.get("id", ""),
        "login": sender.get("login", ""),
        "url": sender.get("url", ""),
        "type": sender.get("type", ""),
        "site_admin": sender.get("site_admin", False),
    }

    # Get the information about the pull request
    pr_info = raw_payload.get("pull_request", {})

    pr_number = pr_info.get("number", 0)
    pr_title = pr_info.get("title", "")
    pr_created_at = to_madrid_local(pr_info.get("created_at", ""))
    pr_closed_at = to_madrid_local(pr_info.get("closed_at", ""))
    pr_merged_at = pr_info.get("merged", False)
    merged_by = pr_info.get("merged_by", {}).get("login", "")

    pr_assignee = ((pr_info.get("assignee") or {}).get("login"),)
    pr_reviewers = [r["login"] for r in pr_info.get("requested_reviewers", [])]

    team_name = raw_payload.get("organization", {}).get("login", "UnknownTeam")
    repo_name = raw_payload["repository"].get("full_name", "unknown-repo")

    # Build a final doc for this commit.
    pr_doc = {
        "event": event_type,
        "action": action,  # always "closed"
        "pr_number": pr_number,
        "title": pr_title,
        "created_at": pr_created_at,
        "closed_at": pr_closed_at,
        "merged_at": pr_merged_at,
        "merged_by": merged_by,
        "assignee": pr_assignee,
        "reviewers": pr_reviewers,
        "repo_name": repo_name,
        "team_name": team_name,
        "sender_info": sender_info,
    }

    # Finally, return a dict containing the full structure
    return pr_doc
