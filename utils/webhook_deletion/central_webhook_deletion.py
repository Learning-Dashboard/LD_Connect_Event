from utils.webhook_deletion.delete_webhooks_github import delete_all_github_webhooks
from utils.webhook_deletion.delete_webhooks_taiga import delete_all_taiga_webhooks
from config.settings import WEBHOOK_URL_GITHUB, WEBHOOK_URL_TAIGA


if __name__ == "__main__":
    # Each team is handled with the GitHub token and the Taiga server of its
    # subject (credentials config), so no global login is needed here.

    # Delete webhooks from GitHub
    delete_all_github_webhooks(WEBHOOK_URL_GITHUB)

    # Delete webhooks from Taiga
    delete_all_taiga_webhooks(WEBHOOK_URL_TAIGA)
