"""Uebersetzt die vorhandenen Windows-Profil-Manifeste (Elgato ProfilesV3-JSON,
DECK-ONE sdProfile-JSON) in das eigene, einheitliche config/profiles.yaml-Schema.

Ausfuehren: python3 -m streamdeck_driver.manifest_parser
(siehe SETUP.md fuer Details / bekannte Luecken der Uebersetzung)

WICHTIGE EINSCHRAENKUNG: Von den 10 Seiten des Elgato "Default Profile" liegen
nur Seite 5 (Modi-Auswahl) und Seite 6 (Studium-Zusatzknopf) als Manifest-JSON
vor (siehe dokumentation/README.md - nur die tatsaechlich befuellten Seiten
wurden kopiert). Die anderen 8 Seiten werden hier NICHT uebersetzt, weil ihr
Inhalt nicht bekannt ist. Das passt aber zur tatsaechlichen Architektur: die
Elgato Mini fungiert als reiner "Moduswahl-Fernbedienung" (zeigt immer Seite 5/6),
waehrend die eigentlichen 15-Tasten-Belegungen auf der DECK ONE liegen (siehe
usb-protokoll-analyse.md: Seitenwechsel auf der Elgato loest 0 USB-Pakete aus).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from .action_translation import KNOWN_TRANSLATIONS, VOLUME_SCRIPT_NOTE

logger = logging.getLogger(__name__)

DOKU_DIR = Path(__file__).resolve().parent.parent.parent / "dokumentation"
ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
OUT_PATH = Path(__file__).resolve().parent.parent / "config" / "profiles.yaml"

# KORRIGIERT 2026-08-21: DECK ONE hat 5 Spalten x 3 Zeilen (empirisch am
# echten Geraet bestaetigt, siehe devices/deckone.py GRID_ROWS/GRID_COLS) -
# vorher faelschlich 3 (von Elgato uebernommen), was Tasten in der 4./5.
# Spalte falsch platziert hat (z.B. "Naechste Seite" landete unten links
# statt unten rechts).
DECKONE_COLS = 5
ELGATO_COLS = 3

# DECK-ONE Profil-UUID -> unser interner Profilname (siehe dokumentation/README.md)
PROFILE_UUID_TO_NAME = {
    "WLOKF4HL-FOTW-X6YR-7G4T-273SDVQSPFZ8": "streaming",
    "MW24LPIA-T3XI-8CW7-F3S9-G2SAV63PB1L6": "nachhilfe",
    "WA2KV1K2-DD2V-JMA5-IJYM-HACTE1JOV391": "studium",
    "EADSZCV6-7K4R-EASH-9ASX-XGYSCA9AFR5V": "kreativ",
    "SV7A3JT3-MJ42-FHR8-094S-NUW8MVQZCV1Q": "audio",
}
PROFILE_COLORS = {
    "streaming": None,
    "nachhilfe": "#FF6B00",
    "studium": "#0078D4",
    "kreativ": "#9B30FF",
    "audio": "#00C851",
}

MODI_ICON_DIR = ASSETS_DIR / "modi-icons"
MODI_ICON_BY_PROFILE = {
    "streaming": MODI_ICON_DIR / "streaming.png",
    "nachhilfe": MODI_ICON_DIR / "nachhilfe.png",
    "studium": MODI_ICON_DIR / "studium.png",
    "kreativ": MODI_ICON_DIR / "kreativ.png",
    "audio": MODI_ICON_DIR / "audio.png",
}


def _rc_to_index(rc: str, cols: int) -> Optional[int]:
    # KORRIGIERT 2026-08-20: Die Elgato/DECK-ONE-Manifest-Keys sind im Format
    # "col,row" (bestaetigt gegen die rohe modi-seite5.json: Schluessel "2,0"
    # ist "Kreativ", die 3. Spalte in Reihe 0) - die vorherige Version hat
    # row/col vertauscht zugewiesen, wodurch Tasten aus der letzten Spalte
    # (Index >= NUM_KEYS) stillschweigend verworfen und andere Tasten auf
    # falsche Positionen gemappt wurden (z.B. "Kreativ" fehlte komplett,
    # "Nachhilfe"/"Vorige Seite" landeten vertauscht).
    m = re.match(r"^(\d+),(\d+)$", rc)
    if not m:
        return None
    col, row = int(m.group(1)), int(m.group(2))
    return row * cols + col


# Freundliche Anzeigenamen, wenn das Original-Manifest nur den generischen
# Aktionsnamen ("Open") als Titel gesetzt hat statt eines eigenen Tastentitels.
DISPLAY_NAME = {
    "firefox.exe": "Firefox",
    "WINWORD.EXE": "Word",
    "POWERPNT.EXE": "PowerPoint",
    "ms-teams.exe": "Teams",
    "blender-launcher.exe": "Blender",
    "anki.exe": "Anki",
    "FusionLauncher.exe": "Fusion 360",
    "pepakura5.exe": "Pepakura",
    "open-geogebra.vbs": "GeoGebra",
    "open-cas-rechner.vbs": "GeoGebra CAS",
    "open-geometrie.vbs": "GeoGebra Geometrie",
    "open-grafikrechner.vbs": "GeoGebra Grafik",
    "open-mathe-aufgaben.vbs": "Mathe-Aufgaben",
    "open-whiteboard.vbs": "Whiteboard",
    "open-calc-suite.vbs": "Calculator Suite",
    "open-claude-app.vbs": "Claude",
}

_GENERIC_TITLES = {"", "open", "website"}

# KI-generierte Icons (ComfyUI/Z-Image, siehe tools/generate_app_icons.py) -
# der Nutzer wollte explizit generierte Artwork statt echter System-Icons.
GENERATED_ICON_DIR = ASSETS_DIR / "generated-icons"
APP_ICON = {
    "firefox.exe": GENERATED_ICON_DIR / "firefox.png",
    "WINWORD.EXE": GENERATED_ICON_DIR / "word.png",
    "POWERPNT.EXE": GENERATED_ICON_DIR / "powerpoint.png",
    "ms-teams.exe": GENERATED_ICON_DIR / "teams.png",
    "open-geogebra.vbs": GENERATED_ICON_DIR / "geogebra.png",
    "open-cas-rechner.vbs": GENERATED_ICON_DIR / "geogebra.png",
    "open-geometrie.vbs": GENERATED_ICON_DIR / "geogebra.png",
    "open-grafikrechner.vbs": GENERATED_ICON_DIR / "geogebra.png",
    "open-whiteboard.vbs": GENERATED_ICON_DIR / "whiteboard.png",
    "open-claude-app.vbs": GENERATED_ICON_DIR / "claude.png",
    "anki.exe": GENERATED_ICON_DIR / "anki.png",
    "blender-launcher.exe": GENERATED_ICON_DIR / "blender.png",
}


def _resolved_title(title: str, action: dict[str, Any]) -> str:
    """Ersetzt einen generischen Manifest-Titel ("Open"/leer) durch einen
    freundlicheren Namen, falls das erkannte Ziel einen kennt (siehe
    DISPLAY_NAME) - z.B. "Open" -> "Firefox" statt der reinen Aktionsbezeichnung."""
    if title.strip().lower() not in _GENERIC_TITLES:
        return title
    return action.get("display_name") or title


def _basename_from_windows_path(path: str) -> str:
    path = path.strip().strip('"')
    return path.replace("\\", "/").rstrip("/").split("/")[-1]


def _translate_open_action(path: str) -> dict[str, Any]:
    path = path.strip().strip('"')
    basename = _basename_from_windows_path(path)

    # switch-*.vbs -> Profilwechsel (ProfileId per Regex aus dem Skriptinhalt,
    # hier aber direkt aus dem bekannten Dateinamen-Schema abgeleitet, da wir
    # die deck-scripts/switch-*.vbs-Dateien kennen)
    m = re.match(r"^switch-(\w+)\.(vbs|bat)$", basename, re.IGNORECASE)
    if m:
        profile = m.group(1).lower()
        if profile in PROFILE_UUID_TO_NAME.values():
            return {"type": "switch_profile", "profile": profile}

    if basename.lower() in ("start-nachhilfe.vbs",):
        return {
            "type": "open_sequence",
            "needs_review": True,
            "note": (
                "urspruengliches Skript startete Firefox + MS Whiteboard + "
                "Explorer-Ordner 'Z:/Nachhilfe/Themen' nacheinander - Z:-Laufwerk "
                "ist unter Linux nicht gemountet, Whiteboard-Ersatz unverifiziert"
            ),
            "steps": [
                {"linux_command": "firefox", "verified": True},
                {"linux_command": "xdg-open https://excalidraw.com", "verified": False},
            ],
        }
    if basename.lower() in ("start-studium.vbs",):
        return {
            "type": "open_sequence",
            "needs_review": True,
            "note": (
                "urspruengliches Skript startete Firefox + Anki + Word + PowerPoint "
                "+ Explorer-Ordner 'Z:/Studium IU' nacheinander - Z:-Laufwerk ist "
                "unter Linux nicht gemountet"
            ),
            "steps": [
                {"linux_command": "firefox", "verified": True},
                {"linux_command": "anki", "verified": False},
                {"linux_command": "libreoffice --writer", "verified": True},
                {"linux_command": "libreoffice --impress", "verified": True},
            ],
        }

    if basename.lower().startswith("vol-"):
        # KORRIGIERT 2026-08-21: jetzt implementiert (siehe actions.py
        # run_app_volume(), nutzt wpctl/PipeWire) statt nur dokumentiertem
        # Nicht-Ersatz. Dateiname-Schema: vol-<app>-<up|down>.vbs
        m = re.match(r"^vol-(.+)-(up|down)\.vbs$", basename, re.IGNORECASE)
        if m:
            return {
                "type": "app_volume",
                "app_name": m.group(1),
                "direction": m.group(2).lower(),
                "original_path": path,
            }
        return {
            "type": "unmapped",
            "original_path": path,
            "needs_review": True,
            "note": VOLUME_SCRIPT_NOTE,
        }

    translation = KNOWN_TRANSLATIONS.get(basename)
    if translation is not None:
        icon_path = APP_ICON.get(basename)
        return {
            "type": "open",
            "linux_command": translation.linux_command,
            "needs_review": not translation.verified or translation.linux_command is None,
            "note": translation.note,
            "original_path": path,
            "display_name": DISPLAY_NAME.get(basename),
            "icon_asset": str(icon_path.relative_to(ASSETS_DIR.parent)) if icon_path and icon_path.exists() else None,
        }

    if path.startswith(("Z:", "Y:")):
        return {
            "type": "open",
            "linux_command": None,
            "needs_review": True,
            "note": "Netzlaufwerk/-pfad ist unter Linux nicht gemountet",
            "original_path": path,
        }

    return {
        "type": "open",
        "linux_command": None,
        "needs_review": True,
        "note": "keine bekannte Uebersetzung fuer diesen Pfad",
        "original_path": path,
    }


def _translate_hotkey(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "hotkey",
        "vkeycode": settings.get("VKeyCode"),
        "ctrl": bool(settings.get("KeyCtrl", False)),
        "shift": bool(settings.get("KeyShift", False)),
        "alt": bool(settings.get("KeyAlt", False)),
    }


def _translate_action(uuid: str, name: str, settings: dict[str, Any]) -> dict[str, Any]:
    if uuid.endswith(".system.hotkey"):
        return _translate_hotkey(settings)
    if uuid.endswith(".system.open"):
        path = settings.get("path", "")
        return _translate_open_action(path)
    if uuid.endswith(".system.website"):
        return {
            "type": "website",
            "url": settings.get("path", ""),
            "open_in_browser": settings.get("openInBrowser", True),
        }
    if uuid.endswith(".page.next"):
        return {"type": "page_next"}
    if uuid.endswith(".page.previous"):
        return {"type": "page_previous"}
    return {"type": "unmapped", "needs_review": True, "note": f"unbekannter Aktionstyp {uuid}"}


def parse_deckone_page(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    keys: dict[int, Any] = {}
    for rc, action_def in data.get("Actions", {}).items():
        idx = _rc_to_index(rc, DECKONE_COLS)
        if idx is None or not (0 <= idx < 15):
            continue
        uuid = action_def.get("UUID", "")
        name = action_def.get("Name", "")
        settings = action_def.get("Settings", {}) or {}
        title = ""
        states = action_def.get("States") or [{}]
        if states:
            title = states[0].get("Title", "") or ""
        action = _translate_action(uuid, name, settings)
        keys[idx] = {
            "name": name,
            "title": _resolved_title(title, action),
            "action": action,
        }
    return {"name": data.get("Name", path.stem), "keys": keys}


def parse_elgato_page(path: Path, cols: int = ELGATO_COLS) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    controllers = data.get("Controllers", [])
    keys: dict[int, Any] = {}
    if controllers:
        for rc, action_def in controllers[0].get("Actions", {}).items():
            idx = _rc_to_index(rc, cols)
            if idx is None or not (0 <= idx < 6):
                continue
            uuid = action_def.get("UUID", "")
            name = action_def.get("Name", "")
            settings = action_def.get("Settings", {}) or {}
            title = ""
            states = action_def.get("States") or [{}]
            if states:
                title = states[0].get("Title", "") or ""
            action = _translate_action(uuid, name, settings)
            keys[idx] = {
                "name": name,
                "title": _resolved_title(title.strip(), action),
                "action": action,
            }
    return {"keys": keys}


def build_config() -> dict[str, Any]:
    config: dict[str, Any] = {
        "version": 1,
        "generated_by": "streamdeck_driver.manifest_parser",
        "elgato": {"pages": {}},
        "deckone": {"active_profile": "nachhilfe", "profiles": {}},
    }

    # --- Elgato Mini: Modi-Seiten (Seite5 + Seite6) ---
    modi5 = DOKU_DIR / "elgato-mini-manifests" / "modi-seite5.json"
    modi6 = DOKU_DIR / "elgato-mini-manifests" / "modi-seite6-studium.json"
    if modi5.exists():
        page = parse_elgato_page(modi5)
        # switch-*.vbs Open-Aktionen -> switch_profile mit passendem Icon
        for idx, key in page["keys"].items():
            act = key["action"]
            if act.get("type") == "switch_profile":
                icon_path = MODI_ICON_BY_PROFILE.get(act["profile"])
                key["icon"] = (
                    {"type": "asset", "path": str(icon_path.relative_to(ASSETS_DIR.parent))}
                    if icon_path and icon_path.exists()
                    else {"type": "generated"}
                )
            else:
                key["icon"] = {"type": "generated"}
        config["elgato"]["pages"]["modi"] = page
    if modi6.exists():
        page = parse_elgato_page(modi6)
        for idx, key in page["keys"].items():
            act = key["action"]
            if act.get("type") == "switch_profile":
                icon_path = MODI_ICON_BY_PROFILE.get(act["profile"])
                key["icon"] = (
                    {"type": "asset", "path": str(icon_path.relative_to(ASSETS_DIR.parent))}
                    if icon_path and icon_path.exists()
                    else {"type": "generated"}
                )
            else:
                key["icon"] = {"type": "generated"}
        config["elgato"]["pages"]["modi_studium"] = page

    # --- DECK ONE: 5 Profile ---
    deckone_dir = DOKU_DIR / "deck-one-manifests"
    for profile_name in PROFILE_UUID_TO_NAME.values():
        profile_dir = deckone_dir / profile_name
        if not profile_dir.is_dir():
            continue
        page_files = sorted(profile_dir.glob("seite*.json"))
        pages = []
        for pf in page_files:
            page = parse_deckone_page(pf)
            for idx, key in page["keys"].items():
                icon_asset = key["action"].get("icon_asset")
                key["icon"] = {"type": "app_icon", "path": icon_asset} if icon_asset else {"type": "generated"}
            page["source_file"] = pf.name
            pages.append(page)
        config["deckone"]["profiles"][profile_name] = {
            "color": PROFILE_COLORS.get(profile_name),
            "pages": pages,
        }

    # --- NEU 2026-08-21: "System"-Profil (HW-Monitor CPU/RAM/GPU/Disk) ---
    # Kein Windows-Manifest-Original - synthetisch hier definiert, damit es
    # bei jeder Neu-Generierung erhalten bleibt statt in config.yaml von Hand
    # (und damit verlierbar) gepflegt zu werden. Rendering-Werte kommen zur
    # Laufzeit aus hw_monitor.py (deckone_controller.py behandelt den
    # Aktionstyp "live_stat" speziell), hier nur die Platzierung/Beschriftung.
    # KORRIGIERT 2026-08-21 (zweiter Durchgang): VRAM gehoert in dieselbe
    # Spalte wie GPU-Last/GPU-Temp (3 Zeilen fuer die GPU-Spalte), Disk
    # ruetscht dafuer in die freie Spalte 3 (Zeile 0). key_index = zeile*5+spalte.
    system_keys = {
        0: {"metric": "cpu", "label": "CPU"},            # Spalte 0, Zeile 0
        5: {"metric": "cpu_temp", "label": "CPU Temp"},  # Spalte 0, Zeile 1
        1: {"metric": "ram", "label": "RAM"},            # Spalte 1, Zeile 0
        6: {"metric": "ram_gb", "label": "RAM GB"},      # Spalte 1, Zeile 1
        2: {"metric": "gpu_load", "label": "GPU"},       # Spalte 2, Zeile 0
        7: {"metric": "gpu_vram", "label": "VRAM"},      # Spalte 2, Zeile 1
        12: {"metric": "gpu_temp", "label": "GPU Temp"}, # Spalte 2, Zeile 2
        3: {"metric": "disk", "label": "Disk /"},        # Spalte 3, Zeile 0
    }
    config["deckone"]["profiles"]["system"] = {
        "color": "#00C8FF",
        "pages": [
            {
                "name": "System-Monitor",
                "source_file": "synthetic",
                "keys": {
                    idx: {
                        "name": info["label"],
                        "title": info["label"],
                        "action": {"type": "live_stat", "metric": info["metric"]},
                        "icon": {"type": "generated"},
                    }
                    for idx, info in system_keys.items()
                },
            }
        ],
    }

    # Elgato-Schalter dafuer: freie Taste 1 auf der Studium-Seite.
    modi_studium_page = config["elgato"]["pages"].get("modi_studium")
    if modi_studium_page is not None and 1 not in modi_studium_page["keys"]:
        modi_studium_page["keys"][1] = {
            "name": "System",
            "title": "System",
            "action": {"type": "switch_profile", "profile": "system"},
            "icon": {"type": "generated"},
        }

    return config


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = build_config()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8-sig") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    logger.info("Config geschrieben nach %s", OUT_PATH)

    # kurze Statistik ueber needs_review-Aktionen
    total = 0
    needs_review = 0

    def walk(obj):
        nonlocal total, needs_review
        if isinstance(obj, dict):
            if obj.get("type") in ("hotkey", "open", "website", "page_next", "page_previous",
                                     "switch_profile", "open_sequence", "unmapped"):
                total += 1
                if obj.get("needs_review"):
                    needs_review += 1
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(config)
    logger.info("%s Aktionen uebersetzt, davon %s mit needs_review=True", total, needs_review)


if __name__ == "__main__":
    main()
