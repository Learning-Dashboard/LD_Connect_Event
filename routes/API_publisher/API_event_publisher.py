import requests
import os
import logging

logger = logging.getLogger(__name__)


def notify_eval_push(event_type: str,prj: str ,author_login: str , quality_model: str)-> None: 
    '''
    Function used to notify Component LD_Eval about the event that has been pushed to the database.
    '''
    
    host = os.getenv("EVAL_HOST", "localhost")
    port = os.getenv("EVAL_PORT", "5001")
    url  = f"http://{host}:{port}/api/event"
    
    event_data = {
        "event_type": event_type,
        "prj": prj,
        "author_login": author_login,  # Replace with actual author login if available
        "quality_model": quality_model,  # Replace with actual quality model if available
    }

    try:
        resp = requests.post(url, json=event_data, timeout=5)
        resp.raise_for_status()
        print(f"LD_Eval responded with {resp.status_code}: {resp.json()}")
    except requests.RequestException as e:
        print(f"Error al notificar a LD_Eval en {url}: {e}")