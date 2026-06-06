"""Entry point: CLI setup + scheduler loop for the CROUS housing monitor.

Usage:
    python main.py                    # interactive config selection menu
    python main.py --config Paris     # use config named "Paris"
    python main.py --new-config       # create a new config
    python main.py --setup            # legacy: create new config (prompts for name)
    python main.py --once             # single check with selected/default config
    python main.py --interval 600     # override interval (seconds)
    python main.py --list             # list all configs
    python main.py --delete Lyon      # delete a config
    python main.py --history          # show saved history for every config
    python main.py --history Paris    # show saved history for one config
"""
from __future__ import annotations

import argparse
import random
import sys
import time

import config as config_mod
import history as history_mod
import notifier
import seen as seen_mod
from scraper import CaptchaDetected, CrousScraper

INTERVAL_JITTER = (0, 30)


def select_config() -> tuple[config_mod.Config, str]:
    """Interactive menu to select or create a config."""
    configs = config_mod.list_configs()

    if not configs:
        notifier.info("[yellow]Aucune config trouvée. Création d'une nouvelle…[/yellow]")
        return config_mod.setup_config()

    notifier.info("[bold]Configurations disponibles :[/bold]")
    for i, name in enumerate(configs, 1):
        cfg = config_mod.load_config(name)
        if cfg:
            notifier.info(
                f"  {i}. [cyan]{name}[/cyan] — "
                f"{cfg.ville}, {cfg.prix_max}€, {cfg.surface_min}m², "
                f"{cfg.type_cohabitation}"
            )

    from rich.prompt import Prompt

    choice = Prompt.ask(
        "\n[bold]Sélectionner une config (numéro ou nom) ou créer une nouvelle[/bold]",
        choices=list(map(str, range(1, len(configs) + 1))) + configs + ["nouveau"],
    )

    if choice == "nouveau":
        return config_mod.setup_config()

    try:
        idx = int(choice) - 1
        name = configs[idx]
    except ValueError:
        name = choice

    cfg = config_mod.load_config(name)
    if cfg is None:
        notifier.info(f"[red]Config « {name} » introuvable[/red]")
        sys.exit(1)

    return cfg, name


def run_cycle(
    scraper: CrousScraper,
    cfg: config_mod.Config,
    bounds: dict,
    seen: set,
    config_name: str,
) -> None:
    """One poll cycle: warmup (first time) -> search -> record history -> alert."""
    try:
        scraper.warmup()
        listings = scraper.search(cfg, bounds)
    except CaptchaDetected as exc:
        notifier.captcha_alert(str(exc))
        raise SystemExit(2)
    except Exception as exc:
        notifier.info(f"[yellow]Cycle ignoré (erreur): {exc}[/yellow]")
        return

    # Record every current match in this config's history (deduped by id),
    # independent of the global seen-set used for alert dedupe.
    history_mod.record(config_name, listings)

    new = [lst for lst in listings if lst.id not in seen]
    notifier.info(
        f"[dim]{time.strftime('%H:%M:%S')} — {len(listings)} résultat(s), "
        f"{len(new)} nouveau(x).[/dim]"
    )
    if new:
        notifier.alert_new_listings(new)
        for lst in new:
            seen.add(lst.id)
        seen_mod.save_seen(seen)


def resolve_bounds(scraper: CrousScraper, cfg: config_mod.Config) -> dict:
    """Geocode `ville` once and cache the bounding box in config."""
    if cfg.bounds:
        return cfg.bounds
    notifier.info(f"[cyan]Géolocalisation de « {cfg.ville} »…[/cyan]")
    bounds = scraper.geocode(cfg.ville)
    cfg.bounds = bounds
    # We need the config name to save it — this is a bit awkward since we don't
    # have it here, but it's passed from main, so we just return bounds.
    return bounds


def main() -> None:
    parser = argparse.ArgumentParser(description="CROUS housing monitor bot")
    parser.add_argument("--config", type=str, default=None,
                        help="config name to use (from configs/ directory)")
    parser.add_argument("--new-config", action="store_true",
                        help="create a new config")
    parser.add_argument("--setup", action="store_true",
                        help="legacy: create a new config (prompts for name)")
    parser.add_argument("--once", action="store_true",
                        help="single check, no loop")
    parser.add_argument("--list", action="store_true",
                        help="list all available configs")
    parser.add_argument("--delete", type=str, default=None,
                        help="delete a config by name")
    parser.add_argument("--history", type=str, nargs="?", const="", default=None,
                        help="afficher l'historique enregistré (toutes les "
                             "configs, ou --history <nom> pour une seule)")
    parser.add_argument("--interval", type=int, default=None,
                        help="override poll interval in seconds (min 60)")
    args = parser.parse_args()

    if args.list:
        configs = config_mod.list_configs()
        if not configs:
            notifier.info("[yellow]Aucune config trouvée[/yellow]")
        else:
            notifier.info("[bold]Configurations disponibles :[/bold]")
            for name in configs:
                cfg = config_mod.load_config(name)
                if cfg:
                    notifier.info(
                        f"  • [cyan]{name}[/cyan] — "
                        f"{cfg.ville}, {cfg.prix_max}€, {cfg.surface_min}m², "
                        f"{cfg.type_cohabitation}"
                    )
        return

    if args.delete:
        config_mod.delete_config(args.delete)
        return

    if args.history is not None:
        if args.history:
            names = [args.history]
        else:
            names = config_mod.list_configs()
        if not names:
            notifier.info("[yellow]Aucune config trouvée[/yellow]")
        for name in names:
            notifier.show_history(name, history_mod.load_history(name))
        return

    if args.new_config or args.setup:
        cfg, config_name = config_mod.setup_config()
    elif args.config:
        cfg = config_mod.load_config(args.config)
        config_name = args.config
        if cfg is None:
            notifier.info(f"[red]Config « {args.config} » introuvable[/red]")
            sys.exit(1)
    else:
        cfg, config_name = select_config()

    if args.interval is not None:
        cfg.interval_seconds = args.interval
        cfg.validate()

    scraper = CrousScraper()
    seen = seen_mod.load_seen()

    notifier.info(
        f"[bold cyan]Config « {config_name} »[/bold cyan] — "
        f"ville={cfg.ville}, prix_max={cfg.prix_max}€, "
        f"surface_min={cfg.surface_min}m², cohabitation={cfg.type_cohabitation}, "
        f"année={cfg.annee} (tool_id={cfg.tool_id})"
    )

    try:
        bounds = resolve_bounds(scraper, cfg)
        # Save the bounds back to the config file
        config_mod.save_config(cfg, config_name)
    except Exception as exc:
        notifier.info(f"[red]Échec géolocalisation: {exc}[/red]")
        sys.exit(1)

    if args.once:
        run_cycle(scraper, cfg, bounds, seen, config_name)
        return

    notifier.info(
        f"[green]Surveillance démarrée — intervalle {cfg.interval_seconds}s "
        f"(+ jitter). Ctrl+C pour arrêter.[/green]"
    )
    try:
        while True:
            run_cycle(scraper, cfg, bounds, seen, config_name)
            sleep_for = cfg.interval_seconds + random.randint(*INTERVAL_JITTER)
            notifier.info(f"[dim]Prochaine vérification dans {sleep_for}s…[/dim]")
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        notifier.info("\n[bold]Arrêt demandé. À bientôt ![/bold]")


if __name__ == "__main__":
    main()
