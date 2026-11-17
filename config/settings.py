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

# GitHub tokens and Taiga servers are configured per subject in the credentials
# config file (see config/credentials_loader.py), not here.
GITHUB_SIGNATURE_KEY = _require_env("GITHUB_SIGNATURE_KEY")
GITHUB_API_URL = os.getenv("GITHUB_API_URL", "https://api.github.com")

TAIGA_SIGNATURE_KEY = _require_env("TAIGA_SIGNATURE_KEY")

# Taiga used by subjects whose taiga_api_url / taiga_auth_url are empty in the
# credentials config. Only required when at least one subject falls back.
# TAIGA_FALLBACK_AUTH_URL is the full login endpoint (…/api/v1/auth).
TAIGA_FALLBACK_API_URL = os.getenv("TAIGA_FALLBACK_API_URL", "")
TAIGA_FALLBACK_AUTH_URL = os.getenv("TAIGA_FALLBACK_AUTH_URL", "")
TAIGA_FALLBACK_USERNAME = os.getenv("TAIGA_FALLBACK_USERNAME", "")
TAIGA_FALLBACK_PASSWORD = os.getenv("TAIGA_FALLBACK_PASSWORD", "")


# Load the webhook URLs from the environment to enable the deletion of webhooks
WEBHOOK_URL_GITHUB = os.getenv("WEBHOOK_URL_GITHUB", "")
WEBHOOK_URL_TAIGA = os.getenv("WEBHOOK_URL_TAIGA", "")
