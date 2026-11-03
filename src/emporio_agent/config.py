"""Paths and the reference clock.

The dataset is historical (orders end in 2026-03), so "now" must be injectable: return-window and
opening-hours answers depend on it, and the example conversations need a fixed date to be reproducible.
"""
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
STORE_TZ = ZoneInfo("America/Campo_Grande")


def store_now() -> datetime:
    """Current store time; `STORE_NOW` (ISO 8601, e.g. 2026-03-10T14:30) overrides the real clock."""
    override = os.environ.get("STORE_NOW")
    if override:
        return datetime.fromisoformat(override).replace(tzinfo=STORE_TZ)
    return datetime.now(STORE_TZ)


def store_today() -> date:
    return store_now().date()
