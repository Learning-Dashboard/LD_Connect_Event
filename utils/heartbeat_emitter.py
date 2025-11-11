"""
Heartbeat emitter that writes 'alive' records into Mongo so the inactivity
detector can observe real health signals.
"""

from __future__ import annotations

import atexit
import logging
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from database.mongo_client import get_collection

LOGGER = logging.getLogger("heartbeat_emitter")


@dataclass(frozen=True)
class HeartbeatSettings:
    collection: str = "system_heartbeats"
    timestamp_field: str = "emitted_at"
    status_field: str = "status"
    ok_value: str = "alive"
    interval_seconds: int = 60
    startup_delay_seconds: int = 0


class HeartbeatEmitter:
    """
    Emits heartbeat documents at a fixed cadence using the same configuration
    consumed by the inactivity detector.
    """

    def __init__(
        self,
        *,
        config_path: Path | str = Path("inactivity_detector/config.yaml"),
        interval_override: Optional[int] = None,
        startup_delay_override: Optional[int] = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.requested_interval = interval_override
        self.requested_startup_delay = startup_delay_override
        self._settings: Optional[HeartbeatSettings] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._collection = None
        self._atexit_registered = False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="HeartbeatEmitter", daemon=True)
        self._thread.start()
        if not self._atexit_registered:
            atexit.register(self.stop)
            self._atexit_registered = True
        LOGGER.info(
            "Heartbeat emitter started (collection=%s, period=%ss).",
            self._load_settings().collection,
            self._load_settings().interval_seconds,
        )

    def stop(self) -> None:
        if not self.is_running:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        LOGGER.info("Heartbeat emitter stopped.")

    def _load_settings(self) -> HeartbeatSettings:
        if self._settings:
            return self._settings
        if not self.config_path.exists():
            LOGGER.warning("Heartbeat config %s missing; using defaults.", self.config_path)
            settings = HeartbeatSettings()
        else:
            config = yaml.safe_load(self.config_path.read_text())
            section = config.get("inactivity_detector", config)
            hb = section.get("heartbeat", {})
            settings = HeartbeatSettings(
                collection=hb.get("collection", HeartbeatSettings.collection),
                timestamp_field=hb.get("timestamp_field", HeartbeatSettings.timestamp_field),
                status_field=hb.get("status_field", HeartbeatSettings.status_field),
                ok_value=hb.get("ok_value", HeartbeatSettings.ok_value),
                interval_seconds=self._resolve_interval(hb),
                startup_delay_seconds=self._resolve_startup_delay(hb),
            )
        self._settings = settings
        return settings

    def _resolve_interval(self, hb: dict) -> int:
        if self.requested_interval:
            return max(1, int(self.requested_interval))
        interval = hb.get("interval_seconds", HeartbeatSettings.interval_seconds)
        return max(1, int(interval))

    def _resolve_startup_delay(self, hb: dict) -> int:
        if self.requested_startup_delay is not None:
            return max(0, int(self.requested_startup_delay))
        delay = hb.get("startup_delay_seconds", HeartbeatSettings.startup_delay_seconds)
        return max(0, int(delay))

    def _run_loop(self) -> None:
        settings = self._load_settings()
        if self._collection is None:
            self._collection = get_collection(settings.collection)
        host = socket.gethostname()

        if settings.startup_delay_seconds > 0:
            LOGGER.info(
                "Delaying first heartbeat for %ss to allow detector to evaluate existing gap.",
                settings.startup_delay_seconds,
            )
            if self._stop_event.wait(settings.startup_delay_seconds):
                return

        while not self._stop_event.is_set():
            start = time.perf_counter()
            try:
                payload = {
                    settings.timestamp_field: datetime.now(timezone.utc),
                    settings.status_field: settings.ok_value,
                    "source": "LD_CONNECT",
                    "host": host,
                }
                self._collection.insert_one(payload)
            except Exception:
                LOGGER.exception("Failed to emit heartbeat.")
            elapsed = time.perf_counter() - start
            wait_time = max(0.0, settings.interval_seconds - elapsed)
            if self._stop_event.wait(wait_time):
                break
