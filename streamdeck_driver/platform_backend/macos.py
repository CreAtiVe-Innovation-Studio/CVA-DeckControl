"""EXPERIMENTELL - macOS-Backend, UNGETESTET (dieses Projekt lief bisher nur
auf Linux + einmal live auf Windows, es gibt keine Mac-Maschine zum Testen).
Nutzt ueberall Standard-macOS-Bordmittel (osascript/AppleScript, 'open',
'screencapture', 'afplay') statt Zusatz-Abhaengigkeiten, um das Risiko so
klein wie moeglich zu halten - aber ungetesteter Code ist ungetesteter Code.
Bei Fehlern bitte ein Issue im Repo aufmachen (mit macOS-Version + Logausgabe)
statt still zu verzweifeln - das ist der einzige Weg, wie das hier je
verifiziert werden kann.

EIN ECHTER OFFENER PUNKT statt eines UNGETESTET-Vorbehalts: send_hotkey()
kann die vkeycode-Werte NICHT automatisch uebersetzen. Sie stammen aus dem
urspruenglichen Windows-Manifest-Import (siehe action_translation.py) und
sind Windows-Virtual-Key-Codes - macOS' 'key code'-Nummerierung (AppleScript/
System Events) ist eine voellig andere, nicht ableitbare Zuordnung (z.B. ist
Mac-Keycode 0 die Taste 'A', Windows-VK 0x41 ist ebenfalls 'A', aber die
beiden Systeme laufen ab da komplett auseinander). Eine geratene Tabelle
wuerde im schlimmsten Fall lautlos die FALSCHE Taste ausloesen - deshalb
bewusst NICHT implementiert, bis jemand mit einem echten Mac eine Windows-
VK-zu-Mac-Keycode-Tabelle durch Testen aufbaut."""
from __future__ import annotations

import logging
import shlex
import subprocess
import time
from pathlib import Path

logger = logging.getLogger("streamdeck_driver.platform_backend.macos")

_MOD_NAMES = {"ctrl": "control down", "shift": "shift down", "alt": "option down"}


def send_hotkey(vkeycode: int, ctrl: bool, shift: bool, alt: bool) -> None:
    logger.error(
        "Hotkey (vkeycode=%s) auf macOS nicht ausgefuehrt: es gibt keine verlaessliche "
        "Windows-VK-Code -> macOS-Keycode-Zuordnung (siehe Docstring von platform_backend/macos.py) - "
        "muesste durch echtes Testen auf einem Mac aufgebaut werden, um nicht versehentlich "
        "die falsche Taste zu senden.",
        vkeycode,
    )


def open_command(cmd: str) -> None:
    if not cmd:
        return
    try:
        subprocess.Popen(shlex.split(cmd))
        logger.info("Programm gestartet: %s", cmd)
    except OSError as exc:
        logger.error("Programm konnte nicht gestartet werden (%s): %s", cmd, exc)


def open_url(url: str) -> None:
    if not url:
        return
    try:
        subprocess.Popen(["open", url])
        logger.info("Website geoeffnet: %s", url)
    except OSError as exc:
        logger.error("Website konnte nicht geoeffnet werden (%s): %s", url, exc)


def take_screenshot_interactive() -> None:  # UNGETESTET
    """'screencapture -i -c': interaktive Bereichsauswahl UND Kopie ins
    Clipboard in einem Aufruf - macOS-Bordmittel, kommt der Linux-
    gnome-screenshot+wl-copy-Kombination sehr nahe."""
    try:
        subprocess.Popen(["screencapture", "-i", "-c"])
        logger.info("Screenshot-Bereichsauswahl gestartet (screencapture -i -c)")
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.error("Screenshot fehlgeschlagen: %s", exc)


def set_app_volume(app_name: str, direction: str, step_percent: int = 5) -> None:  # UNGETESTET
    """macOS bietet ueber oeffentliche/stabile APIs KEINE echte pro-App-
    Lautstaerkeregelung (anders als PipeWire/Windows) - Rueckfall auf die
    SYSTEM-Lautstaerke ueber AppleScript. app_name wird dabei nur geloggt,
    nicht wirklich zur Filterung genutzt - bekannte Plattform-Einschraenkung,
    kein Implementierungsfehler."""
    sign = 1 if direction == "up" else -1
    delta = sign * step_percent
    try:
        get_vol = subprocess.run(
            ["osascript", "-e", "output volume of (get volume settings)"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        current = int(get_vol.stdout.strip())
        new_vol = max(0, min(100, current + delta))
        subprocess.run(["osascript", "-e", f"set volume output volume {new_vol}"], check=True, timeout=5)
        logger.info(
            "App-Lautstaerke: '%s' angefordert, aber macOS hat keine oeffentliche pro-App-API - "
            "System-Lautstaerke stattdessen auf %s%% gesetzt", app_name, new_vol,
        )
    except (subprocess.SubprocessError, FileNotFoundError, ValueError) as exc:
        logger.error("System-Lautstaerke konnte nicht gesetzt werden: %s", exc)


def play_sound(path: Path) -> None:
    try:
        subprocess.Popen(["afplay", str(path)])
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.warning("Ton konnte nicht abgespielt werden: %s", exc)


def _applescript_string(s: str) -> str:
    """AppleScript-String-Literal: nur \\ und " escapen, ECHTE Zeilenumbrueche
    unveraendert lassen (AppleScript kennt kein \\n-Escape - ein Python
    repr() wuerde mehrzeiligen Text wie die Top-Prozesse-Liste als
    sichtbares '\\n' statt als Zeilenumbruch anzeigen)."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def show_message_popup(title: str, text: str) -> None:
    script = (
        f"display dialog {_applescript_string(text)} with title {_applescript_string(title)} "
        'buttons {"OK"} default button "OK"'
    )
    try:
        subprocess.Popen(["osascript", "-e", script])
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.error("Popup-Anzeige fehlgeschlagen: %s", exc)


def get_active_app_id() -> str | None:  # UNGETESTET
    """Liefert den Namen der vordergruendigen App (kleingeschrieben), z.B.
    'firefox' oder 'code' - fuer automatischen Profilwechsel je nach aktiver
    App (window_watch.py). 'System Events'/frontmost ist die uebliche,
    stabile AppleScript-Standardtechnik dafuer - kein zusaetzliches pyobjc
    noetig (das ist keine Kern-Abhaengigkeit dieses Projekts)."""
    script = 'tell application "System Events" to get name of first application process whose frontmost is true'
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3, check=True)
        return result.stdout.strip().lower() or None
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.warning("Aktive App nicht ermittelbar: %s", exc)
        return None
