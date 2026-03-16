import os
from dotenv import load_dotenv
from pathlib import Path

# Determine the base directory (adjust if needed)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from the .env file
load_dotenv(BASE_DIR / ".env")


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Please set it in your .env file or environment."
        )
    return value


# Mongo database settings
MONGO_HOST = os.getenv("MONGO_HOST", "mongodb")
MONGO_PORT = os.getenv("MONGO_PORT", "27017")
MONGO_DB = os.getenv("MONGO_DB", "mongo")
MONGO_USER = os.getenv("MONGO_USER", "")
MONGO_PASS = os.getenv("MONGO_PASS", "")
MONGO_AUTHSRC = os.getenv("MONGO_AUTHSRC", MONGO_DB)

if MONGO_USER and MONGO_PASS:
    MONGO_URI = (
        f"mongodb://{MONGO_USER}:{MONGO_PASS}"
        f"@{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}"
        f"?authSource={MONGO_AUTHSRC}"
    )
else:
    MONGO_URI = f"mongodb://{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}"

# Load the GitHub token from the environment
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_SIGNATURE_KEY = _require_env("GITHUB_SIGNATURE_KEY")
GITHUB_API_URL = os.getenv("GITHUB_API_URL", "https://api.github.com")

TAIGA_API_URL = _require_env("TAIGA_API_URL")
TAIGA_AUTH_URL = os.getenv("TAIGA_AUTH_URL", TAIGA_API_URL)
TAIGA_TOKEN = os.getenv("TAIGA_TOKEN", "")
TAIGA_SIGNATURE_KEY = _require_env("TAIGA_SIGNATURE_KEY")
TAIGA_USERNAME = _require_env("TAIGA_USERNAME")
TAIGA_PASSWORD = _require_env("TAIGA_PASSWORD")


# Load the webhook URLs from the environment to enable the deletion of webhooks
WEBHOOK_URL_GITHUB = os.getenv("WEBHOOK_URL_GITHUB", "")
WEBHOOK_URL_TAIGA = os.getenv("WEBHOOK_URL_TAIGA", "")
