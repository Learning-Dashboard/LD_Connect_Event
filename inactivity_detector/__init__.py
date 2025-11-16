"""
Inactivity Detector package.

Exports the detector and repository so other modules can import the high-level
APIs without needing to know the internal layout.
"""

from .ID_detector import InactivityDetector, DetectorConfig
from .ID_database import InactivityInterval, InactivityRepository
from .runner import InactivityDetectorRunner

__all__ = [
    "InactivityDetector",
    "DetectorConfig",
    "InactivityInterval",
    "InactivityRepository",
    "InactivityDetectorRunner",
]
