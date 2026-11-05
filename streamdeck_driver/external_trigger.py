"""Externe Steuerung von aussen (z.B. per Maustaste ueber input-remapper):
naechstes/vorheriges DECK-ONE-Profil anstossen, ohne eine der 6 Elgato-Mini-
Modus-Tasten zu druecken.

Gleiches Datei-Flag-Prinzip wie live_view.py (siehe dort): ein separater
Prozess (hier: ein kleines Shell-Script, von input-remapper per Maustaste
ausgeloest) kann daemon.py nicht direkt ansprechen, also ist eine Datei der
gemeinsame Schaltpunkt. NEXT_PROFILE_FLAG_PATH wird einmalig angelegt
("touch"), die UnifiedDaemon-Hauptschleife pollt sie (siehe dort) und loescht
sie direkt nach dem Verarbeiten wieder - ein Fire-and-forget-Trigger, kein
Dauerzustand wie bei live_view.enabled.
"""
from __future__ import annotations

import logging

from .paths import app_root

logger = logging.getLogger("streamdeck_driver.external_trigger")

NEXT_PROFILE_FLAG_PATH = app_root() / "config" / "next_profile.request"
PREVIOUS_PROFILE_FLAG_PATH = app_root() / "config" / "previous_profile.request"
GOTO_PROFILE_DIR = app_root() / "config"
GOTO_PROFILE_PREFIX = "goto_"
GOTO_PROFILE_SUFFIX = ".request"


def _consume(path) -> bool:
    if not path.exists():
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return True


def sync_with_flag_files(deckone) -> None:
    """Von der UnifiedDaemon-Hauptschleife regelmaessig aufgerufen (siehe
    live_view.sync_with_flag_file() fuer dasselbe Prinzip): wechselt das
    DECK-ONE-Profil, wenn eine der beiden Trigger-Dateien existiert."""
    if _consume(NEXT_PROFILE_FLAG_PATH):
        _switch_relative(deckone, +1)
    if _consume(PREVIOUS_PROFILE_FLAG_PATH):
        _switch_relative(deckone, -1)
    _sync_goto_profile_flags(deckone)


def _sync_goto_profile_flags(deckone) -> None:
    """Direktwahl eines Profils (z.B. 'goto_gaming.request' -> Profil 'gaming'),
    ausgeloest von einer DPI-Taste+Grid-Taste-Kombination der Scimitar (siehe
    streamdeck-goto-*.sh). Anders als _switch_relative springt das direkt zum
    genannten Profil, unabhaengig vom aktuell aktiven."""
    if not GOTO_PROFILE_DIR.is_dir():
        return
    for path in sorted(GOTO_PROFILE_DIR.glob(f"{GOTO_PROFILE_PREFIX}*{GOTO_PROFILE_SUFFIX}")):
        name = path.name[len(GOTO_PROFILE_PREFIX):-len(GOTO_PROFILE_SUFFIX)]
        _consume(path)
        profile_names = deckone.config.get("profiles", {})
        if name not in profile_names:
            logger.warning("Externer Trigger: unbekanntes Profil '%s' angefragt", name)
            continue
        logger.info("Externer Trigger: Direktwahl Profil '%s'", name)
        deckone.switch_profile(name)


def _switch_relative(deckone, direction: int) -> None:
    profile_names = list(deckone.config.get("profiles", {}).keys())
    if not profile_names:
        return
    if deckone.active_profile in profile_names:
        idx = profile_names.index(deckone.active_profile)
    else:
        idx = -1  # so landet direction=+1 sauber auf Index 0
    next_name = profile_names[(idx + direction) % len(profile_names)]
    logger.info("Externer Trigger: Profilwechsel zu '%s'", next_name)
    deckone.switch_profile(next_name)
