from utils.webhook_deletion.delete_webhooks_github import delete_all_github_webhooks
from utils.webhook_deletion.delete_webhooks_taiga import delete_all_taiga_webhooks
from utils.taiga_token.get_taiga_token import get_token
from config.settings import TAIGA_USERNAME, TAIGA_PASSWORD

WEBHOOK_URL_GITHUB="https://gessi-dashboard.essi.upc.edu/webhook/github"
WEBHOOK_URL_TAIGA= "https://gessi-dashboard.essi.upc.edu/webhook/taiga"


payload = {
    "username": TAIGA_USERNAME,
    "password": TAIGA_PASSWORD,
    "type": "normal",   
}


if __name__ == "__main__":
    # Get the token from Taiga
    token = get_token(payload)
    
    # Delete webhooks from GitHub
    delete_all_github_webhooks(WEBHOOK_URL_GITHUB)
    
    # Delete webhooks from Taiga
    delete_all_taiga_webhooks(token, WEBHOOK_URL_TAIGA)