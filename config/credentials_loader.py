import json
import os
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE_ENV = "CREDENTIALS_FILE"
DEFAULT_CONFIG_FILE = Path("config_files/credentials_config.json")


class CredentialsConfigError(RuntimeError):
    """Base error for credentials configuration issues."""


class CredentialsConfigNotFoundError(FileNotFoundError, CredentialsConfigError):
    """Raised when the credentials config file cannot be found."""


class CredentialsConfigInvalidError(CredentialsConfigError, ValueError):
    """Raised when the credentials config file cannot be parsed."""


class ProjectCredentialsNotFoundError(KeyError):
    """Raised when a team/project is not present in the credentials config."""


def _raw_config_value(config_file: Optional[str] = None) -> str:
    return config_file or os.getenv(CONFIG_FILE_ENV) or str(DEFAULT_CONFIG_FILE)


def get_config_path(config_file: Optional[str] = None) -> Path:
    raw_value = _raw_config_value(config_file)
    raw_path = Path(raw_value).expanduser()
    if raw_path.is_absolute():
        return raw_path
    return (PROJECT_ROOT / raw_path).resolve()


def validate_config_file(config_file: Optional[str] = None) -> Path:
    raw_value = _raw_config_value(config_file)
    config_path = get_config_path(raw_value)
    if config_path.is_file():
        return config_path

    raise CredentialsConfigNotFoundError(
        "Credentials config file not found. "
        f"Resolved {CONFIG_FILE_ENV}={raw_value!r} to {config_path}. "
        "Create config_files/credentials_config.json, mount ./config_files "
        f"into /app/config_files, or set {CONFIG_FILE_ENV} to an absolute path."
    )


def load() -> dict[str, Any]:
    config_path = validate_config_file()
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise CredentialsConfigInvalidError(
            f"Credentials config file at {config_path} contains invalid JSON: "
            f"{exc.msg}"
        ) from exc


def resolve(prj: str, field: str) -> Optional[str]:
    """
    Return the credential <field> (github_token, taiga_user, …)
    that corresponds to <prj>. Raise KeyError if not configured.
    """
    cfg = load()
    config_path = get_config_path()
    for props in cfg.values():
        if prj in props.get("teams", []):
            return props.get(field)

    raise ProjectCredentialsNotFoundError(
        f"Project {prj!r} not found in credentials config {config_path}"
    )
