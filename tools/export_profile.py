#!/usr/bin/env python3
"""Exportiert EIN eigenes DECK-ONE-Profil aus profiles.yaml als eigenstaendige,
teilbare YAML-Datei - zum Weitergeben an andere Nutzer dieses Systems (siehe
tools/import_native_profile.py zum Reinladen auf der Empfaenger-Seite; fuer
den Import ECHTER Elgato-/Streamplify-Exportdateien siehe stattdessen
tools/import_deck_profile.py).

Ausfuehren:
  python3 tools/export_profile.py <profilname> [--out datei.yaml]
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
logger = logging.getLogger("export_profile")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("profile", help="Name des zu exportierenden Profils (siehe deckone.profiles in profiles.yaml)")
    parser.add_argument("--out", type=Path, default=None, help="Zieldatei (Standard: <profilname>.streamdeck-profile.yaml)")
    args = parser.parse_args()

    config = profile_share.load_config()
    profile = config.get("deckone", {}).get("profiles", {}).get(args.profile)
    if profile is None:
        available = list(config.get("deckone", {}).get("profiles", {}).keys())
        parser.error(f"Profil '{args.profile}' nicht gefunden. Vorhanden: {available}")

    out_path = args.out or Path(f"{args.profile}.streamdeck-profile.yaml")
    export_data = {
        "format": "streamdeck-profile-export",
        "version": 1,
        "name": args.profile,
        "color": profile.get("color"),
        "pages": profile.get("pages", []),
    }
    with out_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(export_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    logger.info("Exportiert: %s", out_path)
    logger.warning(
        "Vor dem Weitergeben pruefen: manche Aktionen (z.B. 'open' mit eigenen Dateipfaden, "
        "'ha_toggle'/'ha_cover' mit eigenen Home-Assistant-Entity-IDs) sind nur bei DIR lauffaehig "
        "und muessen der/die Empfaenger:in ggf. anpassen - wird beim Import nicht automatisch geprueft."
    )


if __name__ == "__main__":
    main()
