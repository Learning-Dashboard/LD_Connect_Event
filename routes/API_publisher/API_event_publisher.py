import requests
from requests.adapters import HTTPAdapter
import os
import logging

logger = logging.getLogger(__name__)

_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=2, pool_maxsize=5)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)


def notify_eval_push(
    event_type: str, prj: str, author_login: str, quality_model: str
) -> None:
    """
    Function used to notify Component LD_Eval about the event that has been pushed to the database.
    """

    host = os.getenv("EVAL_HOST", "localhost")
    port = os.getenv("EVAL_PORT", "5001")
    url = f"http://{host}:{port}/api/event"

    event_data = {
        "event_type": event_type,
        "prj": prj,
        "author_login": author_login,  # Replace with actual author login if available
        "quality_model": quality_model,  # Replace with actual quality model if available
    }

    try:
        resp = _session.post(url, json=event_data, timeout=5)
        resp.raise_for_status()
        logger.info("LD_Eval responded with %s: %s", resp.status_code, resp.json())
    except requests.RequestException as e:
        logger.error("Error notifying LD_Eval at %s: %s", url, e)
