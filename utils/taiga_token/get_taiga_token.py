import logging
import requests

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = (2, 10)


def get_token(payload: dict) -> str:
    """
    Using a POST request of the API, this function retrieves the authentication token from Taiga.
    The payload must contain the username and password of the user.

    """
    # Define the login endpoint URL and payload
    login_url = "https://api.taiga.io/api/v1/auth"

    # Send the POST request to log in
    response = requests.post(login_url, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()  # Will raise an error if the response status is not 200

    # Parse the JSON response
    data = response.json()
    # Extract the token;
    token = data.get("auth_token")

    if token:
        logger.info("Login successful, token retrieved.")
    else:
        logger.error("Login failed or token not found in the response.")

    return token
