"""Gemeinsame Aktions-Ausfuehrung fuer beide Geraete (Hotkey/Programm/Website).
Ausgelagert aus dem urspruenglich Elgato-only daemon.py, damit DECK ONE dieselbe
Logik nutzen kann statt sie zu duplizieren. Die eigentlichen System-Aufrufe
(OS-spezifisch) stecken in platform_backend/ - hier steht nur noch, WELCHE
Aktion zu welchem Backend-Aufruf wird."""
from __future__ import annotations

import logging
import socket
import sys
import threading
import time

from gui import server as gui_server

from . import ha_client, platform_backend, windowing

logger = logging.getLogger("streamdeck_driver.actions")

_IS_WINDOWS = sys.platform == "win32"


def _resolve_open_cmd(step: dict) -> str | None:
    """Waehlt den Befehl fuer eine Open-Aktion/einen Sequenz-Schritt. Beim
    Windows-Import aus dem urspruenglichen Deck-Manifest wurde 'original_path'
    (der echte Windows-Programmpfad) mitgefuehrt, bevor er fuer den Linux-
    Betrieb durch 'linux_command' ersetzt wurde (siehe manifest_parser.py) -
    unter Windows ist original_path daher fast immer die bessere Wahl, wo
    vorhanden. Ausnahme bewusst NICHT gesondert behandelt: einzelne Eintraege,
    bei denen linux_command absichtlich vom Original abweicht (z.B. Teams-Web
    statt nativer App), werden dadurch auf ihr urspruengliches Verhalten
    zurueckgesetzt - das ist fuer den Windows-Fall i.d.R. sogar erwuenscht,
    da die native Windows-App zur Verfuegung steht."""
    original = step.get("original_path")
    if _IS_WINDOWS and original:
        return original
    return step.get("linux_command")


def run_hotkey(action: dict) -> None:
    platform_backend.send_hotkey(
        action.get("vkeycode"), action.get("ctrl", False), action.get("shift", False), action.get("alt", False)
    )


def run_open(action: dict) -> None:
    cmd = _resolve_open_cmd(action)
    if not cmd:
        logger.warning(
            "Open-Aktion ohne bekannten Befehl (original_path=%s, note=%s) - ignoriert",
            action.get("original_path"), action.get("note"),
        )
        return
    platform_backend.open_command(cmd)


def run_open_sequence(action: dict) -> None:
    for step in action.get("steps", []):
        cmd = _resolve_open_cmd(step)
        if cmd:
            platform_backend.open_command(cmd)


def run_app_volume(app_name: str, direction: str, step_percent: int = 5) -> None:
    platform_backend.set_app_volume(app_name, direction, step_percent)


def run_website(action: dict) -> None:
    platform_backend.open_url(action.get("url"), new_window=bool(action.get("new_window")))


def run_ha_toggle(action: dict) -> None:
    entity_id = action.get("entity_id")
    if not entity_id:
        logger.warning("ha_toggle-Aktion ohne entity_id - ignoriert")
        return
    ha_client.toggle(entity_id)


def run_ha_cover(action: dict) -> None:
    entity_id = action.get("entity_id")
    direction = action.get("direction")
    if not entity_id or direction not in ("up", "down"):
        logger.warning("ha_cover-Aktion ohne entity_id/direction - ignoriert")
        return
    ha_client.cover_move(entity_id, direction)


def run_open_gui(action: dict) -> None:
    """Startet die Settings-GUI eingebettet im eigenen Daemon-Prozess (falls
    nicht schon eine eigene oder separat gestartete Instanz laeuft, siehe
    gui/server.py::start_in_thread()) und oeffnet sie im Browser - macht sie
    von einer physischen Taste aus erreichbar, ohne Terminal/Verknuepfung.
    Bewusst kein Subprocess-Start mehr (frueherer Ansatz): in der per
    PyInstaller gebauten .exe gibt es keinen separat aufrufbaren
    'python'-Interpreter fuer ein externes Skript mehr."""
    port = int(action.get("port", 8420))
    gui_server.start_in_thread(port)
    open_when_ready(port)


def open_when_ready(port: int, timeout_s: float = 8.0) -> None:
    """Oeffnet http://127.0.0.1:<port>/ erst, wenn der Server wirklich
    Verbindungen annimmt - sonst landet der Browser auf 'Verbindung
    abgelehnt', weil der Server direkt nach dem Start noch hochfaehrt."""
    def _wait_and_open() -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        platform_backend.open_url(f"http://127.0.0.1:{port}/")

    threading.Thread(target=_wait_and_open, daemon=True).start()


def dispatch(action: dict, key_label: str) -> None:
    """Fuehrt alle Aktionstypen aus, die NICHT geraetespezifisch sind
    (Seiten-/Profilwechsel bleiben Sache des Aufrufers, da die jeweilige
    Seiten-/Profilverwaltung pro Geraet unterschiedlich ist)."""
    action_type = action.get("type")
    if action_type == "hotkey" and "screenshot" in key_label.strip().lower():
        platform_backend.take_screenshot_interactive()
    elif action_type == "hotkey":
        run_hotkey(action)
    elif action_type == "open":
        run_open(action)
    elif action_type == "open_sequence":
        run_open_sequence(action)
    elif action_type == "website":
        run_website(action)
    elif action_type == "app_volume":
        run_app_volume(action.get("app_name", ""), action.get("direction", "up"))
    elif action_type == "ha_toggle":
        run_ha_toggle(action)
    elif action_type == "ha_cover":
        run_ha_cover(action)
    elif action_type == "open_gui":
        run_open_gui(action)
    elif action_type in windowing.ACTION_TYPES:
        windowing.run_action(action)
    elif action_type == "unmapped":
        logger.warning("Unmapped-Aktion (%s): %s - ignoriert", key_label, action.get("note"))
    else:
        logger.warning("Unbekannter/geraetespezifischer Aktionstyp '%s' bei dispatch() - ignoriert", action_type)
