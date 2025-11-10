"""
Background runner that keeps the inactivity detector in sync with the LD_CONNECT
ingestion service.
"""

from __future__ import annotations

import atexit
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from .ID_detector import InactivityDetector


class InactivityDetectorRunner:
    """
    Periodically executes the detector so downtime/inactivity intervals stay fresh.
    """

    def __init__(
        self,
        *,
        config_path: Path | str = Path("inactivity_detector/config.yaml"),
        interval_seconds: Optional[int] = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.requested_interval = interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._detector: Optional[InactivityDetector] = None
        self._interval_seconds: Optional[int] = None
        self._atexit_registered = False
        self._logger = logging.getLogger("inactivity_detector.runner")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="InactivityDetectorRunner", daemon=True
        )
        self._thread.start()
        if not self._atexit_registered:
            atexit.register(self.stop)
            self._atexit_registered = True
        self._logger.info(
            "Inactivity detector background runner started (config=%s).",
            self.config_path,
        )

    def serve_forever(self) -> None:
        """
        Run the detection loop on the foreground thread. Useful for dedicated
        worker processes managed by systemd/k8s/compose where we don't want an
        extra thread or Flask dependency.
        """
        if self.is_running:
            raise RuntimeError("Runner already executing in a background thread.")
        self._stop_event.clear()
        self._logger.info(
            "Inactivity detector foreground runner started (config=%s).",
            self.config_path,
        )
        try:
            self._run_loop()
        except KeyboardInterrupt:
            self._logger.info("Inactivity detector foreground runner interrupted.")
            self._stop_event.set()
        finally:
            self._logger.info("Inactivity detector foreground runner stopped.")

    def request_stop(self) -> None:
        """Signal the loop (foreground or background) to exit."""
        self._stop_event.set()

    def stop(self) -> None:
        if not self.is_running:
            self.request_stop()
            return
        self.request_stop()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self._logger.info("Inactivity detector background runner stopped.")

    def _load_detector(self) -> InactivityDetector:
        if self._detector is None:
            self._detector = InactivityDetector.from_file(self.config_path)
            self._interval_seconds = self._resolve_interval(self._detector)
            self._logger.info(
                "Inactivity detector configured with %ds cadence.", self._interval_seconds
            )
        return self._detector

    def _resolve_interval(self, detector: InactivityDetector) -> int:
        if self.requested_interval:
            return max(1, int(self.requested_interval))
        heartbeat_interval = getattr(detector.config.heartbeat, "interval_seconds", 60)
        return max(1, int(heartbeat_interval))

    def _run_loop(self) -> None:
        detector = self._load_detector()
        interval = self._interval_seconds or 60
        while not self._stop_event.is_set():
            start = time.perf_counter()
            try:
                detector.run_once()
            except Exception:
                self._logger.exception("Inactivity detector run failed.")
            elapsed = time.perf_counter() - start
            wait_time = max(0.0, interval - elapsed)
            if self._stop_event.wait(wait_time):
                break
