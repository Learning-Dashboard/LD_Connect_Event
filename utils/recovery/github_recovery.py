import argparse, requests
from typing import Dict, Iterable, Optional, List
from datetime import datetime, timezone
from pymongo import UpdateOne
from dateutil import parser as dtp, tz
import logging

from database.mongo_client import get_collection
from datasources.github_handler import parse_github_event
from config.logger_config import setup_logging
from routes.API_publisher.API_event_publisher import notify_eval_push
from config.settings import GITHUB_TOKEN

setup_logging()
logger = logging.getLogger(__name__)

def parse_dt(s: str | None) -> Optional[datetime]:
    '''
    Accepts ‘2025-05-01’, ‘2025-05-01T14:30’, etc. And returns the datetime tz-aware (Madrid).
    '''
    if not s:
        return None
    d = dtp.isoparse(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=tz.gettz("Europe/Madrid"))
    return d


def get_organization_repos(org: str, headers: Dict[str, str]) -> List[str]:
    """
    Returns a list of repository names for a given GitHub organization.
    """
    url = f"https://api.github.com/orgs/{org}/repos?per_page=100&type=all"
    return [repo["name"] for repo in gh_paginated(url, headers)]


def gh_paginated(url: str, headers: Dict[str, str]) -> Iterable[Dict]:
    '''
    Gets paginated results from a GitHub API endpoint. With this each call to the API returns a suitable JSON
    '''
    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        yield from r.json()
        url = r.links.get("next", {}).get("url")


def upsert(coll, docs: list[dict], key: str) -> int:
    '''
    Upserts a list of documents into a MongoDB collection.	
    '''
    if not docs:
        return 0
    operations = [UpdateOne({key: d[key]}, {"$set": d}, upsert=True) for d in docs] #Create a list of UpdateOne operations for each document in the list, using the key to identify the document
    res = coll.bulk_write(operations, ordered=False)
    return res.matched_count + len(res.upserted_ids)




def collect_github(org: str,  repo: str, prj: str, events: list[str], since: Optional[str], until: Optional[str], quality_model: str):
    '''
    Collects data from a GitHub repository and inserts it into MongoDB. Follows the schema of the LD-Connect project.
    '''
    repo_full = f"{org}/{repo}"          # Full name of the repository, e.g. "LD-Connect/ld-connect"
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}" # Authentication with GitHub API using a token

    counters = {"commits": 0, "issues": 0, "pull_requests": 0} #Counter to display the number of documents inserted of each event type
    author_login = "backfill" # The author login is always "backfill" for backfilling
    
    for ev in events: # Start iterating over the events to collect
        
        if ev == "commits": #First commits
            event_name= "push" # The event name for commits is always "push"
            
            log_url = f"https://api.github.com/repos/{repo_full}/commits?per_page=100"
            if since: log_url += f"&since={since}" # If a SINCE date is proviaded, add it to the URL
            if until: log_url += f"&until={until}" # If a UNTIL date is proviaded, add it to the URL

            payloads = [] #List to store the payloads of the commits
            for c in gh_paginated(log_url, headers): # Iterate over the paginated results of the commits and store them in the payloads list under the schema
                payloads.append({
                    "X-GitHub-Event": "push",
                    "repository": {"full_name": repo_full},
                    "organization": {"login": org},
                    "sender": c["author"] or {},
                    "commits": [{
                        "id": c["sha"],
                        "url": c["url"],
                        "message": c["commit"]["message"],
                        "timestamp": c["commit"]["author"]["date"],
                        "author": {
                            "username": (c["author"] or {}).get("login", ""),
                            "name":     c["commit"]["author"]["name"],
                            "email":    c["commit"]["author"]["email"],
                        },
                    }],
                })

            coll = get_collection(f"github_{prj}.commits") # Collection name to store 
            for raw in payloads: # All the raw payloads, parse them and insert in collection
                doc = parse_github_event(raw,prj)
                for c in doc["commits"]:
                    c.update({"team_name": doc["team_name"],
                              "repo_name": doc["repo_name"],
                              "sender_info": doc["sender_info"],
                              "prj": prj})
                    counters["commits"] += upsert(coll, [c], "sha")
             #COMMUNICATION WITH LD_EVAL USING API
            logger.info(f"Notifying LD_EVAL about event: {event_name} for team with external_id: {prj} with quality_model: {quality_model}")
            try:
                notify_eval_push(event_name, prj, author_login, quality_model)
            except Exception as e:
                logger.error(f"Error notifying LD_EVAL: {e}")
                
        
        
        elif ev == "issues": # Issue event
            event_name = "issues" # The event name for issues is always "issues"
            url = f"https://api.github.com/repos/{repo_full}/issues?state=all&per_page=100"
            if since: url += f"&since={since}"
            raw_issues = list(gh_paginated(url, headers))

            coll = get_collection(f"github_{prj}.issues") #Collection name to store
            for i in raw_issues: # All the raw payloads, parse them and insert in collection
                payload = {
                    "X-GitHub-Event": "issues",
                    "action": i["state"],
                    "repository": {"full_name": repo_full},
                    "organization": {"login": org},
                    "sender": i["user"],
                    "issue": i,
                }
                doc = parse_github_event(payload, prj)
                doc["prj"] = prj
                doc["issue_id"] = doc["issue"]["number"]
                counters["issues"] += upsert(coll, [doc], "issue_id")
            #COMMUNICATION WITH LD_EVAL USING API
            logger.info(f"Notifying LD_EVAL about event: {event_name} for team with external_id: {prj} with quality_model: {quality_model}")
            try:
                notify_eval_push(event_name, prj, author_login, quality_model)
            except Exception as e:
                logger.error(f"Error notifying LD_EVAL: {e}")
                
            
        elif ev == "pull_requests": #Pull request event
            event_name = "pull_requests" # The event name for pull requests is always "pull_requests"
            url = f"https://api.github.com/repos/{repo_full}/pulls?state=closed&per_page=100"
            raw_prs = list(gh_paginated(url, headers))
            coll = get_collection(f"github_{prj}.pull_requests") # All the raw payloads, parse them and insert in collection
            for p in raw_prs:
                payload = {
                    "X-GitHub-Event": "pull_request",
                    "action": "closed",
                    "repository": {"full_name": repo_full},
                    "organization": {"login": org},
                    "sender": p["user"],
                    "pull_request": p,
                }
                doc = parse_github_event(payload, prj)
                doc["prj"] = prj
                counters["pull_requests"] += upsert(coll, [doc], "pr_number")
            #COMMUNICATION WITH LD_EVAL USING API
            logger.info(f"Notifying LD_EVAL about event: {event_name} for team with external_id: {prj} with quality_model: {quality_model}")
            try:
                notify_eval_push(event_name, prj, author_login, quality_model)
            except Exception as e:
                logger.error(f"Error notifying LD_EVAL: {e}")
                
            
        else:
            print(f"Event {ev} not suported.")

    for k in ("commits", "issues", "pull_requests"): # Print the counters of each event type
        if k in events:
            print(f" • {k.replace('_', ' '):<14} → {counters[k]:>4} documents")
    print(f"{sum(counters.values())} documents inserted.")




if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Back-fill of GITHUB for a project, to insert it in MongoDB")
    ap.add_argument("--org",  required=True, help="Organization name on Github")
    ap.add_argument("--repo",  help="Repository name on Github, if not provided, it will backfill all repositories in the organization")
    ap.add_argument("--prj", required=True, help="External ID of the project in LD-Connect")
    ap.add_argument("--events", default="commits,issues,pull_requests",help="List separated by commas pf the events to backfill, by default: commits,issues,pull_requests")
    ap.add_argument("--from-date", help="Date FROM the backfill will be made, must be in format (YYYY-MM-DD), can also put a full date with time (2025-05-01T14:30)")
    ap.add_argument("--to-date",   help="Date UNTIL the backfill will be made, must be in format (YYYY-MM-DD), can also put a full date with time (2025-05-01T14:30)")
    ap.add_argument("--quality-model", default="default",  help="Sets the quality model to use for the evaluation, by default: default")

    ns = ap.parse_args()
    events = [e.strip() for e in ns.events.split(",") if e.strip()]
    since = parse_dt(ns.from_date).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z") if ns.from_date else None
    until = parse_dt(ns.to_date).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")  if ns.to_date   else None

    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}" # Authentication with GitHub API using a token

    if ns.repo:
        repos= [ns.repo]
    else:
        repos = get_organization_repos(ns.org, headers)
        
        if not repos:
            raise SystemExit(f"No repositories found for organization {ns.org}.")
        
    
    for repo in repos:
        collect_github( org = ns.org, repo  = repo, prj= ns.prj, events= events, since = since, until= until, quality_model=ns.quality_model)


# In order to execute this script: python -m recovery.github_recovery --org LD-Connect --repo ld-connect --prj LD_Test_Project --events commits,issues,pull_requests --from-date 2025-01-01 --to-date 2025-12-31
# Or python -m recovery.github_recovery --org LD-Connect --repo ld-connect --prj LD_Test_Project