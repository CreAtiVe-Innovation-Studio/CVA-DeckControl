#!/usr/bin/env python3
"""Importiert ein von jemand anderem exportiertes Profil (siehe
tools/export_profile.py) in die eigene profiles.yaml - fuer den Fall, dass
zwei Nutzer dieses Systems sich gegenseitig fertige Tasten-Setups schicken
wollen, OHNE den Umweg ueber eine echte Elgato-/Streamplify-Exportdatei
(dafuer siehe stattdessen tools/import_deck_profile.py - der Unterschied:
dieses Skript hier erwartet die Datei schon im EIGENEN YAML-Schema dieses
Projekts, keine Uebersetzung noetig).

Ausfuehren:
  python3 tools/import_native_profile.py <exportierte-datei.yaml> [--name eigener-name] [--no-switch-button]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from streamdeck_driver import profile_share  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("import_native_profile")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path, help="mit export_profile.py erzeugte Datei")
    parser.add_argument("--name", default=None, help="eigener Profilname (Standard: der Name aus der Export-Datei)")
    parser.add_argument("--color", default=None, help="Hex-Farbe fuers Profil, ueberschreibt die aus der Export-Datei")
    parser.add_argument("--no-switch-button", action="store_true", help="keinen Elgato-Umschalt-Knopf automatisch anlegen")
    args = parser.parse_args()

    if not args.path.exists():
        parser.error(f"Pfad nicht gefunden: {args.path}")

    with args.path.open(encoding="utf-8-sig") as f:
        export_data = yaml.safe_load(f)

    if not isinstance(export_data, dict) or "pages" not in export_data:
        parser.error(
            f"'{args.path}' sieht nicht wie eine mit export_profile.py erzeugte Datei aus "
            "(erwartet ein 'pages'-Feld) - fuer echte Elgato-/Streamplify-Exporte stattdessen "
            "tools/import_deck_profile.py benutzen."
        )

    name = args.name or export_data.get("name")
    if not name:
        parser.error("Kein Profilname gefunden - mit --name einen angeben.")
    color = args.color if args.color is not None else export_data.get("color")
    pages = export_data["pages"]

    config = profile_share.load_config()
    try:
        result = profile_share.merge_profile_into_config(
            config, name, color, pages, add_switch_button=not args.no_switch_button,
        )
    except ValueError as exc:
        parser.error(str(exc))
    profile_share.save_config(config)

    total = sum(len(p.get("keys", {})) for p in pages)
    logger.info(
        "Profil '%s' importiert: %d Seite(n), %d Taste(n). config/profiles.yaml gesichert + aktualisiert.%s",
        name, len(pages), total, " Umschalt-Knopf angelegt." if result["added_button"] else "",
    )
    logger.info(
        "Tipp: Aktionen mit fremden Dateipfaden/Home-Assistant-IDs (z.B. 'open', 'ha_toggle') "
        "in der Settings-GUI pruefen und an die eigene Umgebung anpassen: python3 gui/server.py"
    )


if __name__ == "__main__":
    main()
