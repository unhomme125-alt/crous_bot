"""Per-config history of matched listings (full details, not just IDs).

Unlike seen_listings.json — a single *global* set of IDs used purely to avoid
re-alerting — the history keeps the **full Listing details, separately for each
config**, so it can be displayed later with:

    python main.py --history            # every config
    python main.py --history Paris      # one config

Each config's history lives in history/<config>.json as a list of listing
dicts, deduped by id and ordered by first discovery.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from typing import List

HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history")


def _safe_name(name: str) -> str:
    """Mirror config.py's sanitization so history files line up with configs."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def _path(config_name: str) -> str:
    return os.path.join(HISTORY_DIR, f"{_safe_name(config_name)}.json")


def load_history(config_name: str) -> List[dict]:
    """Return the saved listings for a config (empty list if none/corrupt)."""
    path = _path(config_name)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, ValueError):
        return []


def record(config_name: str, listings) -> None:
    """Append listings to the config's history, deduped by id.

    Accepts Listing dataclasses or plain dicts. Existing entries keep their
    original first_seen timestamp; only genuinely new ids are appended.
    """
    if not listings:
        return
    os.makedirs(HISTORY_DIR, exist_ok=True)
    existing = load_history(config_name)
    known = {row.get("id") for row in existing}
    changed = False
    for lst in listings:
        row = asdict(lst) if is_dataclass(lst) else dict(lst)
        if row.get("id") not in known:
            existing.append(row)
            known.add(row.get("id"))
            changed = True
    if changed:
        with open(_path(config_name), "w", encoding="utf-8") as fh:
            json.dump(existing, fh, ensure_ascii=False, indent=2)
