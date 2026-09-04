#!/usr/bin/env python3
"""Zeigt, welches Elgato-Stream-Deck-Modell gerade angeschlossen ist (per
VID:PID-Abgleich gegen devices/elgato_generic.py::MODEL_TABLE, plus die
bereits fest eingebaute Mini) - und ob dieses Modell schon gegen echte
Hardware verifiziert ist oder nicht.

Ausfuehren: python3 tools/detect_elgato_device.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hid  # noqa: E402

from streamdeck_driver.devices.elgato_generic import MODEL_TABLE, VENDOR_ID_ELGATO  # noqa: E402
from streamdeck_driver.devices.elgato_mini import PRODUCT_ID as MINI_PID  # noqa: E402


def main() -> None:
    found_any = False
    for dev in hid.enumerate(VENDOR_ID_ELGATO, 0):
        pid = dev.get("product_id")
        found_any = True
        if pid == MINI_PID:
            print(f"Gefunden: Elgato Stream Deck Mini (PID 0x{pid:04X}) - VERIFIZIERT, eigener Treiber (elgato_mini.py)")
            continue
        model = MODEL_TABLE.get(pid)
        if model is None:
            print(f"Gefunden: unbekanntes Elgato-Geraet, PID 0x{pid:04X} - kein Eintrag in MODEL_TABLE, noch nicht unterstuetzt")
            continue
        status = "VERIFIZIERT" if model.verified else "UNGETESTET - vor Nutzung mit Testbild pruefen (siehe elgato_generic.py-Docstring)"
        print(f"Gefunden: {model.name} (PID 0x{pid:04X}, {model.num_keys} Tasten, {model.grid_cols}x{model.grid_rows}) - {status}")

    if not found_any:
        print("Kein Elgato-Geraet (VID 0x0FD9) gefunden.")
        print("Bekannte Modelle in diesem Projekt:")
        print(f"  - Elgato Stream Deck Mini (PID 0x{MINI_PID:04X}) - verifiziert")
        for pid, model in MODEL_TABLE.items():
            print(f"  - {model.name} (PID 0x{pid:04X}) - {'verifiziert' if model.verified else 'ungetestet'}")


if __name__ == "__main__":
    main()
