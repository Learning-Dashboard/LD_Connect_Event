"""
Error handling helpers for the Data Recovery module.

Provides lightweight retry/backoff semantics and a tracker to keep
visibility over intervals that could not be recovered. The goal is to
stay close to the resilience patterns already used in LD Connect while
keeping dependencies minimal.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

import requests

LOGGER = logging.getLogger(__name__)


class RateLimitError(RuntimeError):
    """Raised when an upstream API signals that the rate limit was exceeded."""


def _serialize_interval(interval: Any) -> Dict[str, Any]:
    """
    Convert an interval-like object into a serializable dictionary.
    Supports the InactivityInterval dataclass from the ID module and
    generic mappings with start/end keys.
    """
    if interval is None:
        return {}
    if hasattr(interval, "start_time") and hasattr(interval, "end_time"):
        return {
            "start_time": getattr(interval, "start_time"),
            "end_time": getattr(interval, "end_time"),
            "detection_method": getattr(interval, "detection_method", None),
        }
    if isinstance(interval, dict):
        return {
            "start_time": interval.get("start_time"),
            "end_time": interval.get("end_time"),
            "detection_method": interval.get("detection_method"),
        }
    return {"interval": repr(interval)}


@dataclass
class RecoveryErrorTracker:
    """
    Aggregates failures so they can be inspected or re-processed later.
    """

    failed_intervals: List[Dict[str, Any]] = field(default_factory=list)

    def record_failure(self, interval: Any, source: str, error: Exception) -> None:
        payload = _serialize_interval(interval)
        payload.update(
            {
                "source": source,
                "error": repr(error),
                "recorded_at": datetime.now(timezone.utc),
            }
        )
        self.failed_intervals.append(payload)
        LOGGER.error(
            "Recovery failure for source=%s interval=%s -> %s",
            source,
            payload.get("start_time"),
            error,
        )


@dataclass
class RetryPolicy:
    """
    Simple exponential backoff retry policy.
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    backoff_factor: float = 2.0
    max_delay: float = 30.0
    retriable_statuses: Iterable[int] = (429, 500, 502, 503, 504)

    def run(self, func: Callable, *args, **kwargs):
        """
        Execute `func` with retries. Retries on network errors, HTTP errors
        in `retriable_statuses`, and RateLimitError.
        """
        delay = self.base_delay
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except RateLimitError as exc:
                last_error = exc
            except requests.HTTPError as exc:
                last_error = exc
                status = exc.response.status_code if exc.response is not None else None
                if status not in self.retriable_statuses:
                    raise
            except requests.RequestException as exc:
                last_error = exc
            except Exception as exc:
                last_error = exc
                raise

            if attempt >= self.max_attempts:
                if last_error:
                    raise last_error
                raise RuntimeError("Retry policy exhausted without an error object.")
            LOGGER.warning(
                "Retrying after error (%s/%s): %s", attempt, self.max_attempts, last_error
            )
            time.sleep(delay)
            delay = min(self.max_delay, delay * self.backoff_factor)


def raise_for_status(response: requests.Response) -> None:
    """
    Wrapper around Response.raise_for_status that also surfaces rate-limit
    errors as RateLimitError so the retry policy can handle them uniformly.
    """
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:  # pragma: no cover - exercised via RetryPolicy
        status = response.status_code
        text = response.text.lower()
        if status in (403, 429) and "rate limit" in text:
            raise RateLimitError(f"Rate limit exceeded ({status})") from exc
        raise
