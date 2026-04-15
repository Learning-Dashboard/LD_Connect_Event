from flask import Blueprint, request, jsonify
from datasources.excel_handler import parse_excel_event
from database.mongo_client import get_collection
from routes.API_publisher.API_event_publisher import notify_eval_push
from config.logger_config import setup_logging
import logging

setup_logging()
logger = logging.getLogger(__name__)



excel_bp = Blueprint("excel_bp", __name__)


@excel_bp.route("/webhook/excel", methods=["POST"])
def excel_webhook():
    
    logger.info("Received Excel webhook request.")
    
    # Get the raw JSON payload from the request
    raw_json = request.get_json()
    if not raw_json:
        logger.warning("Excel webhook called without JSON payload.")
        return {"error": "No JSON received"}, 400
        
    # Read the query parameters from the request
    prj   = request.args.get("prj", type=str)
    quality_model = request.args.get("quality_model", type=str)  # otional, if not provided, we have to  use the default one
    
    if not prj:
        logger.warning("Missing required query param: prj")
        return jsonify({"error": "prj is required as query parameter"}), 400


    # Parse the raw JSON payload using the parse_excel_event function
    parsed_data = parse_excel_event(raw_json, prj, quality_model)    
    if "error" in parsed_data:
        return parsed_data, 400
    logger.info("Excel webhook request processed successfully.")

    # Create the collection name based on the project ID 
    collection_name = f"{prj}_sheets"
    event_name = "sheets_activity"
    author_login = '' #username of the author 
    
    coll = get_collection(collection_name)

    # #COMMUNICATION WITH LD_EVAL USING API
    # logger.info(f"Notifying LD_EVAL about event: {event_name} for team with external_id: {prj} with quality_model: {quality_model}")
    # try:
    #     notify_eval_push(event_name, prj, author_login, quality_model)
    # except Exception as e:
    #     logger.error(f"Error notifying LD_EVAL: {e}")
    #     return {"status": "error", "message": str(e)}, 500
    
    
    logger.info(f"Inserting Excel activity document for team {prj}")
    # Insert the parsed data into the MongoDB collection
    coll.insert_one(parsed_data)
    
    return jsonify({"status": "OK"})

    

