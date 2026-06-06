"""Persist seen listing IDs to avoid duplicate alerts."""
from __future__ import annotations

import json
import os
from typing import Set

SEEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen_listings.json")


def load_seen(path: str = SEEN_PATH) -> Set[str]:
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return set(json.load(fh))
    except (json.JSONDecodeError, ValueError):
        # Corrupt file — start fresh rather than crashing the monitor.
        return set()


def save_seen(seen: Set[str], path: str = SEEN_PATH) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(sorted(seen), fh, ensure_ascii=False, indent=2)
