import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from config import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE_ENV = "CREDENTIALS_FILE"
DEFAULT_CONFIG_FILE = Path("config_files/credentials_config.json")

_cache_lock = threading.Lock()
# (path, (mtime_ns, size), parsed config) of the last file read by load()
_cache: Optional[tuple[Path, tuple[int, int], dict[str, Any]]] = None


class CredentialsConfigError(RuntimeError):
    """Base error for credentials configuration issues."""


class CredentialsConfigNotFoundError(FileNotFoundError, CredentialsConfigError):
    """Raised when the credentials config file cannot be found."""


class CredentialsConfigInvalidError(CredentialsConfigError, ValueError):
    """Raised when the credentials config file cannot be parsed."""


class SubjectCredentialsError(CredentialsConfigError):
    """Raised when a subject entry does not yield usable credentials."""


class ProjectCredentialsNotFoundError(KeyError):
    """Raised when a team/project is not present in the credentials config."""


@dataclass(frozen=True)
class TaigaContext:
    """Taiga server and credentials that apply to one subject.

    Either `token` is set (static token) or `username` and `password` are set
    (login at `auth_url`).
    """

    api_url: str
    auth_url: str
    token: str = field(default="", repr=False)
    username: str = ""
    password: str = field(default="", repr=False)


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
    """Return the parsed credentials config, re-reading the file only when it changes."""
    global _cache

    config_path = validate_config_file()
    stat = config_path.stat()
    stamp = (stat.st_mtime_ns, stat.st_size)

    with _cache_lock:
        if _cache is not None and _cache[0] == config_path and _cache[1] == stamp:
            return _cache[2]

    try:
        with config_path.open("r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except json.JSONDecodeError as exc:
        raise CredentialsConfigInvalidError(
            f"Credentials config file at {config_path} contains invalid JSON: "
            f"{exc.msg}"
        ) from exc

    if not isinstance(cfg, dict):
        raise CredentialsConfigInvalidError(
            f"Credentials config file at {config_path} must contain a JSON object "
            "with one entry per subject."
        )

    with _cache_lock:
        _cache = (config_path, stamp, cfg)
    return cfg


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _url(value: Any) -> str:
    return _text(value).rstrip("/")


def _teams(props: Any) -> list:
    teams = props.get("teams") if isinstance(props, dict) else None
    return teams if isinstance(teams, list) else []


def _find_subject(prj: str) -> tuple[str, dict[str, Any]]:
    for subject, props in load().items():
        if prj in _teams(props):
            return subject, props

    raise ProjectCredentialsNotFoundError(
        f"Project {prj!r} not found in credentials config {get_config_path()}"
    )


def _github_token(subject: str, props: dict[str, Any]) -> str:
    token = _text(props.get("github_token"))
    if not token:
        raise SubjectCredentialsError(f"Subject {subject!r} has no github_token.")
    return token


def _taiga_context(subject: str, props: dict[str, Any]) -> TaigaContext:
    api_url = _url(props.get("taiga_api_url"))
    auth_url = _url(props.get("taiga_auth_url"))
    if bool(api_url) != bool(auth_url):
        raise SubjectCredentialsError(
            f"Subject {subject!r} must set both taiga_api_url and taiga_auth_url, "
            "or leave both empty to use the fallback Taiga."
        )

    uses_fallback = not api_url
    if uses_fallback:
        api_url = _url(settings.TAIGA_FALLBACK_API_URL)
        auth_url = _url(settings.TAIGA_FALLBACK_AUTH_URL)
        if not api_url or not auth_url:
            raise SubjectCredentialsError(
                f"Subject {subject!r} uses the fallback Taiga, but "
                "TAIGA_FALLBACK_API_URL and TAIGA_FALLBACK_AUTH_URL are not both set."
            )

    token = _text(props.get("taiga_token"))
    if token:
        return TaigaContext(api_url=api_url, auth_url=auth_url, token=token)

    username = _text(props.get("taiga_user"))
    password = props.get("taiga_password")
    if username and isinstance(password, str) and password:
        return TaigaContext(
            api_url=api_url, auth_url=auth_url, username=username, password=password
        )

    if not uses_fallback:
        raise SubjectCredentialsError(
            f"Subject {subject!r} has its own Taiga server but neither taiga_token "
            "nor taiga_user and taiga_password."
        )

    username = _text(settings.TAIGA_FALLBACK_USERNAME)
    password = settings.TAIGA_FALLBACK_PASSWORD
    if not username or not password:
        raise SubjectCredentialsError(
            f"Subject {subject!r} uses the fallback Taiga without credentials of its "
            "own, but TAIGA_FALLBACK_USERNAME and TAIGA_FALLBACK_PASSWORD are not "
            "both set."
        )
    return TaigaContext(
        api_url=api_url, auth_url=auth_url, username=username, password=password
    )


def get_subject(prj: str) -> str:
    """Return the subject whose `teams` list contains <prj>."""
    return _find_subject(prj)[0]


def get_github_token(prj: str) -> str:
    """Return the GitHub token of the subject that <prj> belongs to."""
    return _github_token(*_find_subject(prj))


def get_taiga_context(prj: str) -> TaigaContext:
    """Return the Taiga server and credentials of the subject that <prj> belongs to."""
    return _taiga_context(*_find_subject(prj))


def validate_config() -> list[str]:
    """Return every problem found in the credentials config (empty when valid)."""
    problems: list[str] = []
    team_owner: dict[str, str] = {}

    for subject, props in load().items():
        if not isinstance(props, dict):
            problems.append(f"Subject {subject!r} must be a JSON object.")
            continue

        if not isinstance(props.get("teams"), list):
            problems.append(f"Subject {subject!r} must have a 'teams' list.")

        for team in _teams(props):
            owner = team_owner.setdefault(team, subject)
            if owner != subject:
                problems.append(
                    f"Team {team!r} is listed under subjects {owner!r} and "
                    f"{subject!r}; only {owner!r} is used."
                )

        for check in (_github_token, _taiga_context):
            try:
                check(subject, props)
            except SubjectCredentialsError as exc:
                problems.append(str(exc))

    return problems
