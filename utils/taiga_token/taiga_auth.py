import requests
import logging
import time
from config.settings import TAIGA_AUTH_URL

log = logging.getLogger(__name__)
_TOKENS = {}  # key = (username, password) -> token
AUTH_TIMEOUT = (5, 10)


def get_taiga_token(username: str, password: str) -> str:
    """
    Tool to get a Taiga API token and cache it for 23 hours (In taiga documentation, says the token expires in 24h).
    If the token is about to expire (less than 60 seconds left), it will request a new one.
    This avoids making too many requests to the Taiga API for the token.
    """

    key = (username, password)
    token, exp = _TOKENS.get(key, (None, 0))

    # If the token is not set or is about to expire, request a new one
    if token is None or exp - time.time() < 60:
        payload = {"username": username, "password": password, "type": "normal"}
        r = requests.post(TAIGA_AUTH_URL, json=payload, timeout=AUTH_TIMEOUT)
        r.raise_for_status()

        token = r.json()["auth_token"]
        exp = time.time() + 23 * 3600
        _TOKENS[key] = (token, exp)
        log.info("New Taiga token acquired successfully, expires in 23h.")

    return token
