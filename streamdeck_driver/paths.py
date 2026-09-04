"""Zentrale Basis-Pfade fuer Nutzer-Dateien (Config/Assets/Sounds).

Ueberall sonst im Projekt wurden diese Pfade bisher direkt ueber
`Path(__file__).resolve().parent...` berechnet - das bricht in einer per
PyInstaller gebauten .exe: dort zeigt `__file__` eines gebuendelten Moduls auf
einen temporaeren Extraktionsordner, nicht auf den echten Installationsort.
config/profiles.yaml & assets/ muessen aber am echten, dauerhaften Ort neben
der .exe gefunden werden (der Nutzer editiert die dort). Deshalb hier die
einzige Stelle mit der sys.frozen-Unterscheidung, alle anderen Module rufen
nur noch app_root()/project_root() auf.
"""
from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Projekt-Wurzel (.../linux-driver/, enthaelt config/ + streamdeck_driver/)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def project_root() -> Path:
    """Ein Verzeichnis ueber app_root() - dort liegt 'assets/' als
    Geschwister-Ordner von linux-driver (siehe README Setup-Abschnitt)."""
    return app_root().parent
