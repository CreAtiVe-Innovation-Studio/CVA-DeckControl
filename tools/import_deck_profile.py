#!/usr/bin/env python3
"""Importiert ein bestehendes Elgato-/Streamplify-Profil (echte Export-Datei
oder -Ordner) als NEUES DECK-ONE-Profil in die bestehende config/profiles.yaml.

Generische Variante des urspruenglichen Einmal-Migrationsscripts
(manifest_parser.py, das nur die eigenen 5 Original-Profile kennt) - erkennt
das Tastenraster automatisch statt es hart zu codieren, und aendert nur die
importierten Teile statt die ganze profiles.yaml neu zu schreiben.

Akzeptiert als <pfad>:
  - eine .streamDeckProfile-Datei (ZIP-Bundle, wie "Profil exportieren" in
    der echten Elgato-Software bzw. Streamplify Link es erzeugt)
  - einen bereits entpackten Profil-Ordner (beliebige Verschachtelungstiefe)
  - eine einzelne Seiten-manifest.json

Beispiel:
  python3 tools/import_deck_profile.py ~/Downloads/MeinProfil.streamDeckProfile --name gaming2 --color '#FF6B00'

Unbekannte Aktionen (Apps, die dieses System noch nicht kennt) werden NICHT
verworfen, sondern als 'unmapped'/needs_review=True markiert - danach in der
Settings-GUI (python3 gui/server.py) nachbearbeiten statt hier zu raten."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from streamdeck_driver import profile_share  # noqa: E402
from streamdeck_driver.manifest_parser import _rc_to_index, _translate_action  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("import_deck_profile")


def _collect_manifests(path: Path) -> list[tuple[str, dict]]:
    """(Dateiname, geparstes JSON) fuer jede gefundene .json-Datei - egal ob
    path eine einzelne Datei, ein Ordner, oder ein .streamDeckProfile/.zip-
    Bundle ist. Ungueltige/nicht-JSON-Dateien werden stillschweigend
    uebersprungen (ein Bundle enthaelt auch PNGs etc., keine Fehlermeldung
    dafuer noetig)."""
    results: list[tuple[str, dict]] = []
    if path.is_file() and path.suffix.lower() in (".zip", ".streamdeckprofile"):
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if not name.lower().endswith(".json"):
                    continue
                try:
                    results.append((name, json.loads(zf.read(name).decode("utf-8-sig"))))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    logger.debug("uebersprungen (%s): %s", name, exc)
    elif path.is_dir():
        for jf in sorted(path.rglob("*.json")):
            try:
                results.append((str(jf.relative_to(path)), json.loads(jf.read_text(encoding="utf-8-sig"))))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                logger.debug("uebersprungen (%s): %s", jf, exc)
    elif path.is_file() and path.suffix.lower() == ".json":
        results.append((path.name, json.loads(path.read_text(encoding="utf-8-sig"))))
    else:
        raise ValueError(f"Unbekannter/nicht unterstuetzter Pfad: {path}")
    return results


def _is_page_manifest(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("Actions"), dict)


def _infer_cols(data: dict) -> int:
    """Erst versuchen, die Spaltenzahl aus expliziten Manifest-Feldern zu
    lesen (verschiedene Elgato-Software-Versionen nennen sie unterschiedlich
    - beide Varianten werden probiert), sonst aus den tatsaechlich benutzten
    'col,row'-Schluesseln ableiten (robuster als sich auf ein bestimmtes
    Feldnamen-Schema zu verlassen, das man ohne echtes Beispiel nicht sicher
    kennt)."""
    for cols_key in ("Columns", "DeviceColumns"):
        if cols_key in data:
            try:
                return int(data[cols_key])
            except (TypeError, ValueError):
                pass
    max_col = 0
    for rc in data.get("Actions", {}):
        try:
            c, _r = rc.split(",")
            max_col = max(max_col, int(c))
        except ValueError:
            continue
    return max_col + 1


def parse_page_manifest(data: dict, cols: int) -> dict:
    keys: dict[int, Any] = {}
    for rc, action_def in data.get("Actions", {}).items():
        idx = _rc_to_index(rc, cols)
        if idx is None or idx < 0:
            continue
        uuid = action_def.get("UUID", "")
        name = action_def.get("Name", "")
        settings = action_def.get("Settings", {}) or {}
        states = action_def.get("States") or [{}]
        title = states[0].get("Title", "") if states else ""
        action = _translate_action(uuid, name, settings)
        keys[idx] = {
            "name": name,
            "title": (title or name or "").strip(),
            "action": action,
            "icon": {"type": "generated"},
        }
    return {"name": data.get("Name", ""), "keys": keys}


def build_pages(manifests: list[tuple[str, dict]], cols_override: int | None) -> list[dict]:
    page_manifests = [(name, d) for name, d in manifests if _is_page_manifest(d)]
    if not page_manifests:
        raise ValueError(
            "Keine Seiten-Manifeste (JSON mit einem 'Actions'-Objekt) im angegebenen "
            "Pfad gefunden - falsches Bundle-Format oder falscher Pfad?"
        )
    pages = []
    for name, data in page_manifests:
        cols = cols_override or _infer_cols(data)
        page = parse_page_manifest(data, cols)
        page["source_file"] = name
        pages.append(page)
        logger.info(
            "Seite '%s' (%s): %d Taste(n), %d Spalten erkannt",
            page["name"] or name, name, len(page["keys"]), cols,
        )
    return pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path, help=".streamDeckProfile-Datei, Ordner oder einzelne manifest.json")
    parser.add_argument("--name", required=True, help="interner Profilname (z.B. 'gaming2'), keine Leerzeichen")
    parser.add_argument("--color", default=None, help="Hex-Farbe fuers Profil, z.B. '#FF6B00'")
    parser.add_argument("--cols", type=int, default=None, help="Spaltenzahl erzwingen statt automatisch erkennen")
    parser.add_argument("--no-switch-button", action="store_true", help="keinen Elgato-Umschalt-Knopf automatisch anlegen")
    args = parser.parse_args()

    if not args.path.exists():
        parser.error(f"Pfad nicht gefunden: {args.path}")

    manifests = _collect_manifests(args.path)
    pages = build_pages(manifests, args.cols)

    config = profile_share.load_config()
    try:
        result = profile_share.merge_profile_into_config(
            config, args.name, args.color, pages, add_switch_button=not args.no_switch_button,
        )
    except ValueError as exc:
        parser.error(str(exc))
    profile_share.save_config(config)
    added_button = result["added_button"]

    total = sum(len(p["keys"]) for p in pages)
    needs_review = sum(1 for p in pages for k in p["keys"].values() if k["action"].get("needs_review"))
    logger.info(
        "Profil '%s' importiert: %d Seite(n), %d Taste(n) (%d davon needs_review=True). "
        "config/profiles.yaml gesichert + aktualisiert.%s",
        args.name, len(pages), total, needs_review,
        " Umschalt-Knopf angelegt." if added_button else "",
    )
    if needs_review:
        logger.info("Offene Punkte am besten in der Settings-GUI nachbearbeiten: python3 gui/server.py")


if __name__ == "__main__":
    main()
