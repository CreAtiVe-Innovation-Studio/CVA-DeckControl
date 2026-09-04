"""Uebersetzungstabelle Windows-Pfade/vbs-Skripte -> Linux-Kommandos.

Diese Tabelle ist zwangslaeufig unvollstaendig, weil manche der urspruenglichen
Windows-Programme (Pepakura5, ...) keine 1:1-Entsprechung unter Linux haben.
Eintraege mit verified=False sind Bestapproximationen - siehe SETUP.md
"Bekannte Grenzen". Stand 2026-08-21: alle Eintraege wurden gegen die
tatsaechlich installierte Software auf dieser Maschine gegengeprueft (welche
Binaries/Flatpaks/.desktop-Dateien wirklich existieren), nicht nur geraten.

Format: basename (Windows-Pfad oder vbs-Dateiname, GROSS/klein wie im Original)
        -> (linux_command_or_None, verified: bool, note: str)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Translation:
    linux_command: Optional[str]
    verified: bool
    note: str


KNOWN_TRANSLATIONS: dict[str, Translation] = {
    "firefox.exe": Translation("firefox", True, ""),
    "WINWORD.EXE": Translation("libreoffice --writer", True, ""),
    "POWERPNT.EXE": Translation("libreoffice --impress", True, ""),
    "ms-teams.exe": Translation(
        "teams-for-linux", True,
        "verifiziert 2026-08-21: /snap/bin/teams-for-linux existiert real auf dieser Maschine",
    ),
    "blender-launcher.exe": Translation(
        None, False,
        "verifiziert 2026-08-21: Blender ist NICHT installiert (weder Binary noch "
        "Flatpak gefunden) - muesste erst nachinstalliert werden (z.B. "
        "'flatpak install flathub org.blender.Blender'), bevor diese Aktion "
        "funktioniert",
    ),
    "anki.exe": Translation(
        None, False,
        "verifiziert 2026-08-21: Anki ist NICHT installiert (weder Binary noch "
        "Flatpak gefunden) - muesste erst nachinstalliert werden",
    ),
    "FusionLauncher.exe": Translation(
        None, False,
        "Autodesk Fusion hat keinen nativen Linux-Client - kein direkter Ersatz "
        "moeglich. Alternative (nicht automatisiert): Autodesk bietet eine "
        "Web-Version unter fusion.autodesk.com an, die im Browser laeuft.",
    ),
    "pepakura5.exe": Translation(
        None, False, "Pepakura Designer ist Windows-only - kein Linux-Ersatz bekannt"
    ),
    "open-geogebra.vbs": Translation(
        "flatpak run org.geogebra.GeoGebra", True,
        "verifiziert 2026-08-21: Flatpak org.geogebra.GeoGebra (GeoGebra Classic 6) "
        "ist real installiert, startet die volle App",
    ),
    "open-cas-rechner.vbs": Translation(
        "flatpak run org.geogebra.GeoGebra", True,
        "verifiziert 2026-08-21: GeoGebras eigene --help-Ausgabe zeigt KEINE "
        "Modus-Flags (kein --cas/--graphing/--geometry) - die urspruengliche "
        "Vermutung war falsch. Startet die volle Classic-6-App, CAS-Ansicht "
        "muss manuell wie unter Windows ueber das App-Menue gewaehlt werden.",
    ),
    "open-geometrie.vbs": Translation(
        "flatpak run org.geogebra.GeoGebra", True,
        "siehe open-cas-rechner.vbs - keine Modus-Flags verfuegbar, volle App startet",
    ),
    "open-grafikrechner.vbs": Translation(
        "flatpak run org.geogebra.GeoGebra", True,
        "siehe open-cas-rechner.vbs - keine Modus-Flags verfuegbar, volle App startet",
    ),
    "open-mathe-aufgaben.vbs": Translation(
        None, False,
        "oeffnete unter Windows den Ordner 'Desktop/Mathe Aufgaben' per explorer.exe. "
        "Bester Kandidat auf dieser Maschine (verifiziert 2026-08-21, aber NICHT "
        "automatisch uebernommen, da der Name abweicht und eine Fehlzuordnung "
        "beim Oeffnen fremder Ordner riskant waere): "
        "'/media/alien/DATA/1_vv/Privat/Lustige Mathe Aufgaben' - bei Bedarf manuell "
        "als linux_command='xdg-open \"/media/alien/DATA/1_vv/Privat/Lustige Mathe "
        "Aufgaben\"' eintragen, wenn das wirklich der richtige Ordner ist.",
    ),
    "open-whiteboard.vbs": Translation(
        "/snap/bin/chromium --profile-directory=Default "
        "--app-id=dnfpoenibinnbbckgbhendmlljoobcfg",
        True,
        "verifiziert 2026-08-21: echte installierte Excalidraw-PWA gefunden "
        "(~/.local/share/applications/chrome-dnfpoenibinnbbckgbhendmlljoobcfg-Default.desktop), "
        "startet als eigenes App-Fenster statt nur eines Browser-Tabs",
    ),
    "open-calc-suite.vbs": Translation(
        None, False,
        "oeffnete eine Desktop-Verknuepfung 'Calculator Suite.lnk' - Zielprogramm "
        "unbekannt, kein Linux-Ersatz ermittelbar",
    ),
    "open-claude-app.vbs": Translation(
        "claude-desktop", True,
        "verifiziert 2026-08-21: /usr/bin/claude-desktop existiert real auf dieser "
        "Maschine (eigene Desktop-App, nicht nur die Claude-Code-CLI)",
    ),
}

# Best-recherchierte, aber bewusst NICHT automatisch eingetragene Kandidaten fuer
# die Z:-Netzlaufwerk-Pfade (Z: existiert unter Linux nicht) - siehe manifest_parser.py
# _translate_open_action() fuer die Pfade "Z:/Nachhilfe/..." und "Z:/Studium IU".
# Ordner-Namen laufen unter dem gemeinsam genutzten Laufwerk unter anderen Namen und
# es gibt mehrere Kandidaten (z.B. zwei verschiedene "Studium"-Ordner von
# unterschiedlichen Personen) - eine automatische Zuordnung waere zu riskant
# (koennte den falschen/fremden Ordner oeffnen). Manuell pruefen:
#   Z:/Nachhilfe/... -> /media/alien/Gaming/KI/Projekte/Nachhilfe (existiert, aber
#     ohne die urspruengliche "Themen/Mathematik"-Unterordnerstruktur)
#   Z:/Studium IU    -> zwei Kandidaten gefunden: /media/alien/DATA/1_vv/Studium
#     (vermutlich der Nutzer selbst) vs. ein Ordner einer anderen Person auf
#     demselben Laufwerk - NICHT automatisch raten.

# vol-*.vbs (App-spezifische Lautstaerkeregelung ueber app-volume.ps1) - kein
# einfacher 1:1-Linux-Ersatz ohne PipeWire/PulseAudio-Sink-Input-Scripting
# (out of scope fuer dieses Projekt, siehe SETUP.md).
VOLUME_SCRIPT_NOTE = (
    "app-spezifische Lautstaerkeregelung (app-volume.ps1) hat keinen implementierten "
    "Linux-Ersatz - wuerde PipeWire/pactl-Sink-Input-Scripting pro Anwendung "
    "brauchen, aus Zeitgruenden nicht umgesetzt"
)
