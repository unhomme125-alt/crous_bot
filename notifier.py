"""Terminal (rich) + optional desktop (plyer) notifications."""
from __future__ import annotations

import sys
from typing import List

# Ensure UTF-8 output so €, m², accents and emoji render on Windows consoles
# (the legacy cp1252 console otherwise crashes on non-cp1252 characters).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

try:  # plyer is optional — degrade gracefully if unavailable.
    from plyer import notification as _desktop
except Exception:  # pragma: no cover
    _desktop = None

# legacy_windows=False forces the standard (UTF-8) renderer instead of the
# win32 console path that strict-encodes to cp1252.
console = Console(legacy_windows=False)


def info(msg: str) -> None:
    console.print(msg)


def alert_new_listings(listings: List, desktop: bool = True) -> None:
    """Display all required fields for each new listing."""
    if not listings:
        return

    table = Table(
        title=f"🏠 {len(listings)} nouveau(x) logement(s) CROUS !",
        show_lines=True,
        title_style="bold green",
    )
    table.add_column("Titre", style="bold cyan", overflow="fold")
    table.add_column("Prix", justify="right", style="yellow")
    table.add_column("Surface", justify="right")
    table.add_column("Ville", style="magenta")
    table.add_column("Type")
    table.add_column("Lien", style="blue", overflow="fold")

    for lst in listings:
        table.add_row(
            lst.title,
            f"{lst.price:.0f} €",
            f"{lst.surface:.0f} m²",
            lst.city,
            lst.type,
            lst.url,
        )
    console.print(table)

    if desktop and _desktop is not None:
        try:
            first = listings[0]
            extra = f" (+{len(listings) - 1} autre(s))" if len(listings) > 1 else ""
            _desktop.notify(
                title="CROUS : nouveau logement !",
                message=f"{first.title} — {first.price:.0f}€ — {first.city}{extra}",
                app_name="CROUS bot",
                timeout=10,
            )
        except Exception:
            # Desktop notifications are best-effort; never break the loop.
            pass


def captcha_alert(url: str) -> None:
    console.print(
        Panel.fit(
            f"[bold red]CAPTCHA / anti-bot challenge détecté[/bold red]\n"
            f"URL: {url}\n\n"
            "Le bot s'arrête pour éviter un bannissement. "
            "Réessayez plus tard ou depuis une autre IP.",
            border_style="red",
        )
    )
