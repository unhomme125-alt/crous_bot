"""User filter input + save/load JSON config with multi-config support.

Configs are stored in configs/ directory, e.g., configs/Paris.json, configs/Lyon.json.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import List, Optional

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.prompt import IntPrompt, Prompt

console = Console(legacy_windows=False)

CONFIGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs")
LEGACY_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Ensure configs dir exists
os.makedirs(CONFIGS_DIR, exist_ok=True)

# --- Exact CROUS filter vocabularies (do not add/remove filters) --------------
COHABITATION = {
    "individuel": "alone",
    "colocation": "house_sharing",
    "couple": "couple",
}
ANNEE_TO_TOOL_ID = {
    "2025-2026": 42,
    "2026-2027": 45,
}


@dataclass
class Config:
    ville: str = "Paris"
    prix_max: int = 400
    surface_min: int = 9
    type_cohabitation: str = "individuel"
    annee: str = "2026-2027"
    interval_seconds: int = 300
    bounds: Optional[dict] = field(default=None)

    @property
    def tool_id(self) -> int:
        return ANNEE_TO_TOOL_ID[self.annee]

    @property
    def occupation_mode(self) -> str:
        return COHABITATION[self.type_cohabitation]

    def validate(self) -> None:
        if self.type_cohabitation not in COHABITATION:
            raise ValueError(
                f"type_cohabitation must be one of {list(COHABITATION)}, "
                f"got {self.type_cohabitation!r}"
            )
        if self.annee not in ANNEE_TO_TOOL_ID:
            raise ValueError(
                f"annee must be one of {list(ANNEE_TO_TOOL_ID)}, got {self.annee!r}"
            )
        if self.prix_max <= 0 or self.surface_min < 0:
            raise ValueError("prix_max must be > 0 and surface_min >= 0")
        if self.interval_seconds < 60:
            console.print(
                "[yellow]interval_seconds < 60 is unsafe (ban risk); "
                "clamping to 60.[/yellow]"
            )
            self.interval_seconds = 60


def _get_config_path(name: str) -> str:
    """Get the full path for a named config (no extension needed)."""
    # Sanitize: only alphanumeric + - _
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return os.path.join(CONFIGS_DIR, f"{safe_name}.json")


def list_configs() -> List[str]:
    """Return list of config names (without .json extension) sorted alphabetically."""
    if not os.path.exists(CONFIGS_DIR):
        return []
    return sorted(
        f[:-5] for f in os.listdir(CONFIGS_DIR) if f.endswith(".json")
    )


def load_config(name: Optional[str] = None) -> Optional[Config]:
    """Load a config by name. If name is None, try legacy root config.json."""
    if name:
        path = _get_config_path(name)
    else:
        path = LEGACY_CONFIG_PATH

    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    cfg = Config(**{k: data[k] for k in data if k in Config.__dataclass_fields__})
    cfg.validate()
    return cfg


def save_config(cfg: Config, name: str) -> None:
    """Save a config with the given name."""
    path = _get_config_path(name)
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(asdict(cfg), fh, ensure_ascii=False, indent=2)
    console.print(f"[green]Config « {name} » sauvegardée[/green]")


def delete_config(name: str) -> None:
    """Delete a config by name."""
    path = _get_config_path(name)
    if os.path.exists(path):
        os.remove(path)
        console.print(f"[yellow]Config « {name} » supprimée[/yellow]")


def setup_config(name: Optional[str] = None) -> tuple[Config, str]:
    """Interactive filter setup. Returns (config, name)."""
    if name is None:
        name = Prompt.ask("[bold]Nom de la configuration[/bold]", default="Paris")

    console.rule(f"[bold]CROUS housing monitor — nouvelle config « {name} »")
    existing = load_config(name)

    ville = Prompt.ask(
        "Ville / résidence / lieu d'études",
        default=existing.ville if existing else "Paris",
    )
    prix_max = IntPrompt.ask(
        "Prix max (€ / mois)",
        default=existing.prix_max if existing else 400,
    )
    surface_min = IntPrompt.ask(
        "Surface min (m²)",
        default=existing.surface_min if existing else 9,
    )
    type_cohabitation = Prompt.ask(
        "Type de cohabitation",
        choices=list(COHABITATION.keys()),
        default=existing.type_cohabitation if existing else "individuel",
    )
    annee = Prompt.ask(
        "Année universitaire",
        choices=list(ANNEE_TO_TOOL_ID.keys()),
        default=existing.annee if existing else "2026-2027",
    )
    interval_seconds = IntPrompt.ask(
        "Intervalle de vérification (secondes, min 60)",
        default=existing.interval_seconds if existing else 300,
    )

    cfg = Config(
        ville=ville,
        prix_max=prix_max,
        surface_min=surface_min,
        type_cohabitation=type_cohabitation,
        annee=annee,
        interval_seconds=interval_seconds,
        bounds=None,
    )
    cfg.validate()
    save_config(cfg, name)
    return cfg, name
