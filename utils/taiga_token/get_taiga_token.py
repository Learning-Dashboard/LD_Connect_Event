import requests
from config.settings import TAIGA_AUTH_URL


def get_token(payload:dict) -> str: 
    """
    Using a POST request of the API, this function retrieves the authentication token from Taiga.
    The payload must contain the username and password of the user.
    
    """
    # Define the login endpoint URL and payload
    login_url = f"{TAIGA_AUTH_URL}/auth"


    # Send the POST request to log in
    response = requests.post(login_url, json=payload)
    response.raise_for_status()  # Will raise an error if the response status is not 200

    # Parse the JSON response
    data = response.json()
    # Extract the token; 
    token = data.get("auth_token")

    if token:
        print("Login successful, token retrieved:")
    else:
        print("Login failed or token not found in the response.")
    
    return token


