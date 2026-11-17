import requests
import logging
import time

from config.credentials_loader import TaigaContext

log = logging.getLogger(__name__)
_TOKENS = {}  # key = (auth_url, username, password) -> (token, expiry)
AUTH_TIMEOUT = (5, 10)
_TOKEN_SCHEMES = ("Application", "Bearer")


def get_taiga_token(auth_url: str, username: str, password: str) -> str:
    """
    Tool to get a Taiga API token and cache it for 23 hours (In taiga documentation, says the token expires in 24h).
    If the token is about to expire (less than 60 seconds left), it will request a new one.
    This avoids making too many requests to the Taiga API for the token.
    The cache is kept per Taiga server (auth_url), since each subject can use a different one.
    """

    key = (auth_url, username, password)
    token, exp = _TOKENS.get(key, (None, 0))

    # If the token is not set or is about to expire, request a new one
    if token is None or exp - time.time() < 60:
        payload = {"username": username, "password": password, "type": "normal"}
        r = requests.post(auth_url, json=payload, timeout=AUTH_TIMEOUT)
        r.raise_for_status()

        token = r.json()["auth_token"]
        exp = time.time() + 23 * 3600
        _TOKENS[key] = (token, exp)
        log.info("New Taiga token acquired successfully from %s, expires in 23h.", auth_url)

    return token


def auth_header(token: str) -> dict:
    """Return the correct Authorization header for a Taiga token.

    ApplicationTokens contain colons (base64:timestamp:hash) and require the
    'Application' scheme; regular session tokens use 'Bearer'. A token saved
    with its scheme ("Application ..." or "Bearer ...") is not prefixed twice.
    """
    raw = token.strip()
    for scheme in _TOKEN_SCHEMES:
        if raw.startswith(f"{scheme} "):
            raw = raw[len(scheme) :].strip()
            break
    prefix = "Application" if ":" in raw else "Bearer"
    return {"Authorization": f"{prefix} {raw}"}


def auth_headers(ctx: TaigaContext) -> dict:
    """Return the Authorization header for a subject's Taiga server.

    Uses the static token when the context has one; otherwise logs in at the
    context's auth URL (raises requests.RequestException when the login fails).
    """
    if ctx.token:
        return auth_header(ctx.token)
    token = get_taiga_token(ctx.auth_url, ctx.username, ctx.password)
    return {"Authorization": f"Bearer {token}"}
