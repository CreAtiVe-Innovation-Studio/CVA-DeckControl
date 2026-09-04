"""Gemeinsame Merge-/Backup-Logik zum Einfuegen eines neuen DECK-ONE-Profils
in die bestehende config/profiles.yaml - genutzt von tools/import_deck_profile.py
(uebersetzt ein ECHTES Elgato-/Streamplify-Manifest) UND von
tools/import_native_profile.py (laedt ein bereits im eigenen YAML-Schema
vorliegendes, von jemand anderem exportiertes Profil, siehe
tools/export_profile.py) - beide brauchen exakt dieselbe
Einfuegen+Sichern+Umschalt-Knopf-Logik, nur die Herkunft der 'pages'-Liste
unterscheidet sich."""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

import yaml

logger = logging.getLogger("streamdeck_driver.profile_share")

DRIVER_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = DRIVER_ROOT / "config" / "profiles.yaml"
BACKUP_DIR = DRIVER_ROOT / "config" / "backups"


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8-sig") as f:
        return yaml.safe_load(f)


def free_elgato_slot(config: dict) -> tuple[str, int] | None:
    """Erste freie Taste (Index 0-4, Index 5 ist ueberall konventionell
    'Naechste Seite') auf irgendeiner elgato.pages-Seite - fuer den
    switch_profile-Knopf, ohne den ist ein neu importiertes Profil nicht
    erreichbar (siehe CLAUDE.md-Kochrezept 'Neues Profil')."""
    for page_name, page in config.get("elgato", {}).get("pages", {}).items():
        keys = page.get("keys", {})
        for idx in range(5):
            if idx not in keys:
                return page_name, idx
    return None


def merge_profile_into_config(
    config: dict, name: str, color: str | None, pages: list[dict], add_switch_button: bool = True,
) -> dict:
    """Fuegt EIN neues Profil unter deckone.profiles[name] ein (wirft
    ValueError falls der Name schon existiert), optional inkl. Elgato-
    Umschalt-Knopf. Speichert NICHT selbst - siehe save_config()."""
    if name in config.get("deckone", {}).get("profiles", {}):
        raise ValueError(f"Profil '{name}' existiert schon - anderen Namen waehlen oder erst in profiles.yaml entfernen.")

    config.setdefault("deckone", {}).setdefault("profiles", {})[name] = {"color": color, "pages": pages}

    added_button = False
    if add_switch_button:
        slot = free_elgato_slot(config)
        if slot:
            page_name, idx = slot
            config["elgato"]["pages"][page_name]["keys"][idx] = {
                "name": "Open",
                "title": name.capitalize(),
                "action": {"type": "switch_profile", "profile": name},
                "icon": {"type": "generated"},
            }
            added_button = True
            logger.info("Umschalt-Knopf angelegt: elgato.pages.%s Taste %s", page_name, idx)
        else:
            logger.warning(
                "Kein freier Platz fuer einen Umschalt-Knopf gefunden - Profil ist "
                "aktuell nur ueber die Settings-GUI erreichbar (dort manuell zuweisen)."
            )
    return {"added_button": added_button}


def save_config(config: dict) -> None:
    """Sichert die AKTUELLE profiles.yaml (Zeitstempel-Backup) und schreibt
    die neue Version - dieselbe Konvention wie gui/server.py::_save_config()."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(CONFIG_PATH, BACKUP_DIR / f"profiles.{stamp}.yaml")
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
