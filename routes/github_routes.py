from flask import Blueprint, request, jsonify
from datasources.github_handler import parse_github_event
from database.mongo_client import get_collection
from config.settings import GITHUB_SIGNATURE_KEY
from routes.API_publisher.API_event_publisher import notify_eval_push
from routes.verify_signature.verify_signature_github import verify_github_signature
from config.logger_config import setup_logging
import logging

setup_logging()
logger = logging.getLogger(__name__)

github_bp = Blueprint("github_bp", __name__)

@github_bp.route("/webhook/github", methods=["POST"])
def github_webhook():
    
    logger.info("Received Github webhook request.")
    
    # Signature verfication, in the definition of the webhook we must have the same value as in the .env file 
    secret=GITHUB_SIGNATURE_KEY.encode() 
    if not verify_github_signature(request, secret):
        logger.warning("Invalid Github webhook signature.")
        return jsonify({"error": "Invalid Signature"}), 403  
    
    # Get the raw JSON payload from the request
    raw_payload = request.get_json()
    if not raw_payload:
        logger.warning("Github webhook called without JSON payload.")
        return {"error": "No JSON received"}, 400
    
    
    # Read the query parameters from the request
    prj   = request.args.get("prj", type=str)
    quality_model = request.args.get("quality_model", type=str)  # otional, if not provided, we have to  use the default one
    if not prj:
        logger.warning("Missing required query param: prj")
        return jsonify({"error": "prj is required as query parameter"}), 400
    
    
    # We read the event name from the GitHub header, not in the JSON
    event_name = request.headers.get("X-GitHub-Event")
    raw_payload["X-GitHub-Event"] = event_name  # Put it in the JSON so parse function sees it

    # Parse the raw JSON payload using the parse_github_event function
    parsed_data = parse_github_event(raw_payload, prj)
    logger.info(f"Github webhook request processed successfully for team {prj}.")    
    
    if parsed_data.get("ignored"):
        return {"status": "ignored", "event": parsed_data["event"]}, 200
    if "error" in parsed_data:
        return parsed_data, 400


    team_name = parsed_data["team_name"] #We wont use this, we will use the external_id instead as its a CENTRALIZED ID
    event_label = parsed_data["event"] #This is either "commit" or "issue"   
    author_login = parsed_data["sender_info"]["login"] #username of the author of the commit or issue
    
    # Decide the name of the MongoDB collection to write to, depending on the event type
    if event_label == "commit":
        collection_name = f"github_{prj}.commits"
    elif event_label == "issue":
        collection_name = f"{prj}_issues"
    elif event_label == "pull_request":
        collection_name = f"github_{prj}.pull_requests"
    
    coll = get_collection(collection_name)

    # # COMMUNICATION WITH LD_EVAL USING API
    logger.info(f"Notifying LD_EVAL about event: {event_name} for team with external_id: {prj} with quality_model: {quality_model}")
    try:
        notify_eval_push(event_name, prj, author_login, quality_model)
    except Exception as e:
        logger.error(f"Error notifying LD_EVAL: {e}")
        return {"status": "error", "message": str(e)}, 500
    

    # If it's a commit push, we may have multiple commits. We need to insert each one separately.
    if "commits" in parsed_data:
        for commit_doc in parsed_data["commits"]:
            # add top-level fields to each commit if you want
            commit_doc["team_name"] = parsed_data["team_name"]
            commit_doc["prj"] = prj
            commit_doc["sender_info"] = parsed_data["sender_info"]
            commit_doc["event"] = parsed_data["event"]
            commit_doc["repo_name"] = parsed_data["repo_name"]

            logger.debug(f"Inserting commit document: {commit_doc}")
            coll.insert_one(commit_doc)
            logger.info(f"Inserting in MongoDB Github commit for team {prj}")

        return {"status": "ok", "message": "Commits inserted"}, 200

    # If it's an issue event, we insert the issue document
    elif "issue" in parsed_data:
        parsed_data["prj"] = prj
        coll.insert_one(parsed_data)
        logger.info(f"Inserting in MongoDB Github issue for team {prj}")
        return {"status": "ok", "message": "Issue inserted"}, 200
    
    
    elif "pull_request" in parsed_data:
        parsed_data["prj"] = prj
        coll.insert_one(parsed_data)
        logger.info(f"Inserting in MongoDB Github closed pull request for team {prj}")
        return {"status": "ok", "message": "Pull request inserted"}, 200

    #If its neither a commit or a issue
    coll.insert_one(parsed_data)
    return {"status": "ok", "message": "Stored event doc"}, 200
