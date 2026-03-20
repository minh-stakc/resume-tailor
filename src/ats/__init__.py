"""ATS adapter registry — detects platform from URL and returns the right adapter."""

from src.ats.base import ATSAdapter
from src.ats.greenhouse import GreenhouseAdapter
from src.ats.lever import LeverAdapter
from src.ats.workday import WorkdayAdapter
from src.ats.ashby import AshbyAdapter
from src.ats.generic import GenericAdapter

_ADAPTERS: list[type[ATSAdapter]] = [
    GreenhouseAdapter,
    LeverAdapter,
    WorkdayAdapter,
    AshbyAdapter,
]


def detect_ats(url: str) -> ATSAdapter:
    """Return the best adapter for the given URL, falling back to GenericAdapter."""
    for cls in _ADAPTERS:
        if cls.matches(url):
            print(f"[ATS] Detected platform: {cls.__name__.replace('Adapter', '')}")
            return cls()
    print("[ATS] No platform match — using generic Claude-vision adapter")
    return GenericAdapter()
