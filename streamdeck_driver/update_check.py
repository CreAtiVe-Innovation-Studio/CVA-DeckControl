"""Einfacher Update-Check: vergleicht die installierte Version (siehe
streamdeck_driver/__init__.py::__version__) gegen den neuesten GitHub-
Release des Projekts. Rein informativ, kein Zwang, kein Auto-Update - laeuft
einmal beim Daemon-Start in einem Hintergrund-Thread (blockiert nichts) und
schlaegt bei fehlendem Internet oder noch nicht existierenden Releases
lautlos fehl (nur ein Log-Eintrag). Das Ergebnis landet in einem
Modul-Zustand, den die Settings-GUI abfragen kann (siehe
gui/server.py::/api/update-check) um es dem Nutzer sichtbar zu machen."""
from __future__ import annotations

import logging
import re
import threading

import requests

from . import __version__

logger = logging.getLogger("streamdeck_driver.update_check")

GITHUB_REPO = "CreAtiVe-Innovation-Studio/CVA-DeckControl"
CHECK_TIMEOUT_S = 5

_state: dict = {"checked": False, "current": __version__, "latest": None, "update_available": False, "url": None}
_lock = threading.Lock()


def _parse_version(v: str) -> tuple[int, ...]:
    """'v1.2.3' oder '1.2.3' -> (1,2,3) fuer den numerischen Vergleich -
    Pre-Release-Suffixe wie '-beta' werden ignoriert (nur Ziffern gezaehlt)."""
    parts = re.findall(r"\d+", v)
    return tuple(int(p) for p in parts) or (0,)


def check_now() -> dict:
    """Blockierender Check - schreibt das Ergebnis in den Modul-Zustand und
    gibt ihn zusaetzlich zurueck. Fuer den Hintergrund-Start siehe
    check_in_background(); die Settings-GUI kann das hier auch direkt
    synchron aufrufen (siehe gui/server.py)."""
    result = {"checked": True, "current": __version__, "latest": None, "update_available": False, "url": None}
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json"},
            timeout=CHECK_TIMEOUT_S,
        )
        if resp.status_code == 404:
            logger.info("Update-Check: noch keine Releases auf GitHub vorhanden")
        else:
            resp.raise_for_status()
            data = resp.json()
            latest_tag = data.get("tag_name", "")
            result["latest"] = latest_tag
            result["url"] = data.get("html_url")
            if _parse_version(latest_tag) > _parse_version(__version__):
                result["update_available"] = True
                logger.info("Update verfuegbar: %s -> %s (%s)", __version__, latest_tag, result["url"])
            else:
                logger.info("Update-Check: aktuell (%s, neuestes Release: %s)", __version__, latest_tag)
    except requests.RequestException as exc:
        logger.debug("Update-Check fehlgeschlagen (kein Internet o.ae.): %s", exc)
    with _lock:
        _state.clear()
        _state.update(result)
    return result


def get_last_result() -> dict:
    with _lock:
        return dict(_state)


def check_in_background() -> None:
    threading.Thread(target=check_now, name="update-check", daemon=True).start()
