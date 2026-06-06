"""HTTP requests + listing parsing for trouverunlogement.lescrous.fr.

NOTE ON THE SITE'S REAL MECHANISM
---------------------------------
The spec's CLAUDE.md assumes an HTML <form> parsed with BeautifulSoup. In
reality the site is a Svelte single-page app: there is no server-rendered list
of listings to scrape. The search is a JSON POST to

    https://trouverunlogement.lescrous.fr/api/fr/search/{tool_id}

and the "ville" free-text field is resolved to a geographic bounding box by the
site's own Photon geocoder proxy (/photon/api) — the same call the site's
autocomplete makes. We replicate that exact mechanism, which is the faithful
way to mirror the form. BeautifulSoup is still used to clean the HTML fragments
the API returns inside residence descriptions/addresses.

Filter -> request mapping (matches the site form exactly, 5 fields):
    ville             -> location bounding box (via /photon/api geocode)
    prix_max (€)      -> price.max in cents  (prix_max * 100)
    surface_min (m²)  -> area.min
    type_cohabitation -> occupationModes token (alone/house_sharing/couple)
    annee             -> tool_id in the endpoint path (42 / 45)
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

BASE = "https://trouverunlogement.lescrous.fr"
HOMEPAGE = BASE + "/"
GEOCODE_URL = BASE + "/photon/api"
SEARCH_URL = BASE + "/api/fr/search/{tool_id}"

# Minimum spacing between consecutive network requests (anti-ban).
MIN_REQUEST_GAP = (45, 90)  # seconds, uniform
# Backoff schedule for 429 / 503.
BACKOFF_SCHEDULE = [120, 240, 480]  # seconds, max 3 retries
CONNECTION_RETRIES = 3
CONNECTION_RETRY_WAIT = 60  # seconds

# >= 10 real browser User-Agent strings, rotated per request.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
]

# --- request logging to requests.log -----------------------------------------
import os

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requests.log")
logger = logging.getLogger("crous.requests")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(_LOG_PATH, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_fh)


class CaptchaDetected(Exception):
    """Raised when the site challenges us — the bot must stop, not retry."""


@dataclass
class Listing:
    id: str
    title: str
    price: float       # monthly price in euros
    surface: float     # surface in m²
    city: str
    type: str          # individuel / colocation / couple
    url: str
    first_seen: str    # ISO timestamp


_MODE_TO_FR = {"alone": "individuel", "house_sharing": "colocation", "couple": "couple"}


def _clean_html(text: Optional[str]) -> str:
    """Strip HTML entities/tags from API text fragments via BeautifulSoup."""
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)


class CrousScraper:
    def __init__(self) -> None:
        self.session = requests.Session()
        self._warmed_up = False
        self._last_request_ts: Optional[float] = None

    # --- low-level request with all anti-ban controls -------------------------
    def _throttle(self) -> None:
        """Guarantee >= MIN_REQUEST_GAP between consecutive requests."""
        if self._last_request_ts is None:
            return  # first request of the process: no artificial wait
        target_gap = random.uniform(*MIN_REQUEST_GAP)
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < target_gap:
            wait = target_gap - elapsed
            logger.info("THROTTLE sleeping %.1fs to respect min request gap", wait)
            time.sleep(wait)

    def _headers(self, json_body: bool) -> dict:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Referer": BASE + "/tools/42/search",  # mimic navigation from the form
            "Origin": BASE,
        }
        if json_body:
            headers["Accept"] = "application/json"
            headers["Content-Type"] = "application/json"
        else:
            headers["Accept"] = (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            )
        return headers

    def _request(self, method: str, url: str, *, json_body=None, params=None) -> requests.Response:
        """Sequential request with throttle, UA rotation, backoff and logging."""
        self._throttle()
        conn_attempts = 0
        backoff_idx = 0
        while True:
            try:
                resp = self.session.request(
                    method,
                    url,
                    json=json_body,
                    params=params,
                    headers=self._headers(json_body is not None),
                    timeout=30,
                )
            except requests.ConnectionError as exc:
                conn_attempts += 1
                logger.warning("CONNECTION_ERROR %s %s attempt %d: %s",
                               method, url, conn_attempts, exc)
                if conn_attempts > CONNECTION_RETRIES:
                    raise
                time.sleep(CONNECTION_RETRY_WAIT)
                continue
            finally:
                self._last_request_ts = time.monotonic()

            logger.info("%s %s -> %s", method, url, resp.status_code)

            # CAPTCHA / bot-challenge detection — stop, do not retry.
            lowered = resp.text[:2000].lower() if resp.content else ""
            if any(tok in lowered for tok in ("captcha", "datadome", "/challenge", "are you a robot")):
                logger.error("CAPTCHA detected on %s", url)
                raise CaptchaDetected(url)

            # 429 / 503 -> exponential backoff using Retry-After when present.
            if resp.status_code in (429, 503):
                if backoff_idx >= len(BACKOFF_SCHEDULE):
                    logger.error("Backoff exhausted for %s (status %s)", url, resp.status_code)
                    resp.raise_for_status()
                retry_after = resp.headers.get("Retry-After")
                try:
                    wait = int(retry_after) if retry_after else BACKOFF_SCHEDULE[backoff_idx]
                except ValueError:
                    wait = BACKOFF_SCHEDULE[backoff_idx]
                logger.warning("HTTP %s on %s — backing off %ss (retry %d/%d)",
                               resp.status_code, url, wait, backoff_idx + 1, len(BACKOFF_SCHEDULE))
                backoff_idx += 1
                time.sleep(wait)
                self._throttle()
                continue

            resp.raise_for_status()
            return resp

    # --- high-level operations ------------------------------------------------
    def warmup(self) -> None:
        """GET the homepage once to obtain session cookies, mimicking a real user."""
        if self._warmed_up:
            return
        self._request("GET", HOMEPAGE)
        self._warmed_up = True

    def geocode(self, ville: str) -> dict:
        """Resolve free-text `ville` to a bounding box via the site's Photon proxy.

        Returns {"top_left": {lon,lat}, "bottom_right": {lon,lat}}.
        """
        resp = self._request("GET", GEOCODE_URL, params={"q": ville, "limit": 1, "lang": "fr"})
        feats = resp.json().get("features") or []
        if not feats:
            raise ValueError(f"Could not geocode ville={ville!r} (no match found)")
        props = feats[0].get("properties", {})
        geom = feats[0].get("geometry", {})
        if props.get("extent"):
            west, north, east, south = props["extent"]
        else:
            # A point result (precise address/residence): build a ~10km box.
            lon, lat = geom["coordinates"]
            d = 0.07
            west, north, east, south = lon - d, lat + d, lon + d, lat - d
        return {
            "top_left": {"lon": west, "lat": north},
            "bottom_right": {"lon": east, "lat": south},
        }

    def search(self, cfg, bounds: dict) -> List[Listing]:
        """POST the search and parse results into Listing objects."""
        body = {
            "idTool": cfg.tool_id,
            "need_aggregation": False,
            "page": 1,
            "pageSize": 100,
            "sector": None,
            "occupationModes": [cfg.occupation_mode],
            "location": [bounds["top_left"], bounds["bottom_right"]],
            "residence": None,
            "equipment": [],
            "price": {"min": 0, "max": int(cfg.prix_max) * 100},  # API uses cents
            "area": {"min": int(cfg.surface_min), "max": 10000},
            "toolMechanism": "residual",
        }
        resp = self._request("POST", SEARCH_URL.format(tool_id=cfg.tool_id), json_body=body)
        data = resp.json()
        items = data.get("results", {}).get("items", []) or []
        listings = [self._parse_item(it, cfg.tool_id) for it in items if it]
        # Server price/area filters match on overlapping ranges, so a listing
        # whose rent range merely touches the cap can leak through. Re-apply the
        # filters client-side so prix_max/surface_min are strict guarantees.
        return [
            lst for lst in listings
            if lst.price <= cfg.prix_max
            and lst.surface >= cfg.surface_min
            and lst.type == cfg.type_cohabitation
        ]

    @staticmethod
    def _parse_item(item: dict, tool_id: int) -> Listing:
        residence = item.get("residence") or {}
        entity = residence.get("entity") or {}
        modes = item.get("occupationModes") or []
        # Cheapest rent across this listing's occupation modes (cents -> euros).
        rents = [m.get("rent", {}).get("min") for m in modes if m.get("rent")]
        price = min(rents) / 100.0 if rents else 0.0
        mode_type = modes[0].get("type") if modes else ""
        area = item.get("area") or {}
        surface = float(area.get("min") or 0)

        res_label = _clean_html(residence.get("label") or "")
        kind = _clean_html(item.get("label") or "")
        title = " — ".join(p for p in (kind, res_label) if p) or "Logement CROUS"
        city = _clean_html(entity.get("name") or "") or _clean_html(residence.get("address") or "")

        return Listing(
            id=str(item.get("id")),
            title=title,
            price=price,
            surface=surface,
            city=city,
            type=_MODE_TO_FR.get(mode_type, mode_type),
            url=f"{BASE}/tools/{tool_id}/accommodations/{item.get('id')}",
            first_seen=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
