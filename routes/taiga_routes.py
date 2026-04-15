from flask import Blueprint, request, jsonify
from datasources.taiga_handler import parse_taiga_event
from database.mongo_client import get_collection
from config.settings import TAIGA_SIGNATURE_KEY
from routes.API_publisher.API_event_publisher import notify_eval_push
from routes.verify_signature.verify_signature_taiga import verify_taiga_signature
import logging

logger = logging.getLogger(__name__) 

taiga_bp = Blueprint("taiga_bp", __name__)


@taiga_bp.route("/webhook/taiga", methods=["POST"])
def taiga_webhook():
    
    logger.info("Received Taiga webhook request.")
    
    # Signature verfication, in the definition of the webhook we must have the same value as in the .env file 
    secret=TAIGA_SIGNATURE_KEY.encode()
    if not verify_taiga_signature(request, secret):
        logger.warning("Invalid Taiga webhook signature.")
        return jsonify({"error": "Invalid Signature"}), 403  
    
    # Get the raw JSON payload from the request
    raw_payload = request.json
    if not raw_payload:
        logger.warning("Taiga webhook called without JSON payload.")
        return jsonify({"error": "No JSON"}), 400

    
    # Read the query parameters from the request
    prj = request.args.get("prj", type=str)
    quality_model = request.args.get("quality_model", type=str)  # otional, if not provided, we have to  use the default one


    # Get important values from the payload
    event_type= raw_payload.get("type","")
    action_type= raw_payload.get("action","")
    id = raw_payload.get("data",{}).get("id", "")
    team_name = raw_payload.get("data",{}).get("project", {}).get("name", "")
    

    # Decide the Mongo collection name to write to, depending on the event type
    if event_type in ["userstory", "relateduserstory"]:
        collection_name = f"taiga_{prj}.userstories"
    elif event_type == "issue":
        collection_name = f"taiga_{prj}.issues"
    elif event_type == "task":
        collection_name = f"taiga_{prj}.tasks"
    elif event_type == "epic":
        collection_name = f"taiga_{prj}.epics"
    else:
        return jsonify({"status": "ignored", "reason": "unsupported type"}), 200

    coll = get_collection(collection_name)

    #Handle the deletion of a document before we parse the payload, to avoid data errors
    if action_type == "delete":
        logger.info(f"Deleting document from {collection_name}. ID={id}")
        if not id:
            return jsonify({"error": "No object ID"}), 400
        coll.delete_one({f"{event_type}_id": id})
        logger.info(f"Document with {event_type}={id} has been deleted.")
        return jsonify({"status": "ok"}), 200
    
    

    # Parse the raw JSON payload using the parse_taiga_event function 
    parsed_data = parse_taiga_event(raw_payload, prj)
    logger.info("Taiga webhook request processed successfully.")

    author_login = parsed_data["assigned_by"] #username of the author of the commit or issue  

    #If the event is a user story, identify the user story ID and upsert/insert it in the collection
    if event_type in ["userstory", "relateduserstory"]:
        # UP-SERT user stories in the same collection
        user_story_id = parsed_data.get("userstory_id")
        if not user_story_id:
            return jsonify({"error": "No user story ID"}), 400

        logger.info(f"Upserting user story with ID: {user_story_id}")
        parsed_data["prj"] = prj
        result = coll.update_one(
            {"userstory_id": user_story_id},
            {"$set": parsed_data},
            upsert=True
        )
        logger.info(f"Inserting in MongoDB Taiga userstory for team {prj}")
    
    
    #If the event is a taks , identify the task ID and upsert/insert it in the collection
    elif event_type == "task":
        
        #if in the parsed data is_closed is true, means the task is closed, so we have to update the points of the user story
        #if parsed_data.get("is_closed") == True and parsed_data.get("userstory_is_closed") == True:
            
        
        
        
        coll = get_collection(collection_name)
        task_id = parsed_data.get("task_id")
        if not task_id:
            return jsonify({"error": "No task ID"}), 400

        logger.info(f"Upserting task with ID: {task_id}")
        # Upsert instead of insert
        parsed_data["prj"] = prj
        result = coll.update_one(
            {"task_id": task_id},
            {"$set": parsed_data},
            upsert=True
    )
        logger.info(f"Inserting in MongoDB Taiga task for team {prj}")
     
     
     #If the event is an epic, identify the epic ID and upsert/insert it in the collection   
    elif event_type == "epic":
        coll = get_collection(collection_name)
        epic_id = parsed_data.get("epic_id")
        if not epic_id:
            return jsonify({"error": "No epic ID"}), 400

        logger.info(f"Upserting epic with ID: {epic_id}")
        # Upsert instead of insert
        parsed_data["prj"] = prj
        result = coll.update_one(
            {"epic_id": epic_id},
            {"$set": parsed_data},
            upsert=True
    )
        logger.info(f"Inserting in MongoDB Taiga epic for team {prj}")
        
        
    # If the event is an issue, identify the issue ID and upsert/insert it in the collection
    elif event_type == "issue":
        coll = get_collection(collection_name)
        issue_id = parsed_data.get("issue_id")
        if not issue_id:
            return jsonify({"error": "No issue ID"}), 400

        logger.info(f"Upserting issue with ID: {issue_id}")
        parsed_data["prj"] = prj
        # Upsert instead of insert
        result = coll.update_one(
            {"issue_id": issue_id},
            {"$set": parsed_data},
            upsert=True
    )
        logger.info(f"Inserting in MongoDB Taiga issue for team {prj}")
        
        
    else:
        # If the event is not one of the above, we will insert it as a new document
        parsed_data["prj"] = prj
        inserted_id = coll.insert_one(parsed_data).inserted_id


    #COMMUNICATION WITH LD_EVAL USING API
    logger.info(f"Notifying LD_EVAL about event: {event_type} for team with external_id: {prj} with quality_model: {quality_model}")
    try:
        notify_eval_push(event_type, prj, author_login, quality_model)
    except Exception as e:
        logger.error(f"Error notifying LD_EVAL: {e}")
        return jsonify({"error": "Failed to notify LD_EVAL"}), 500
    
    
    return jsonify({"status": "ok"}), 200
