"""Windows-Backend - UNGETESTET (dieses Projekt lief bisher ausschliesslich
auf Linux, hier ist keine Windows-Maschine zum Testen vorhanden). Jede
Funktion nutzt eine gut dokumentierte Standard-Windows-API/-Technik statt
etwas Exotisches, aber vor produktivem Einsatz auf echter Hardware
verifizieren - insbesondere send_hotkey() (rohes SendInput per ctypes) und
set_app_volume() (pycaw, muss per 'pip install pycaw comtypes' installiert
werden - kein Teil der Kern-Abhaengigkeiten, da Windows-only)."""
from __future__ import annotations

import ctypes
import logging
import shlex
import subprocess
from pathlib import Path

logger = logging.getLogger("streamdeck_driver.platform_backend.windows")

# -- Hotkey-Injection per SendInput (ctypes) ---------------------------------
# vkeycode ist hier bewusst OHNE Uebersetzungstabelle nutzbar: die Werte in
# profiles.yaml stammen urspruenglich aus dem Windows-Manifest-Import (siehe
# action_translation.py) und sind damit bereits echte Windows-Virtual-Key-
# Codes - anders als beim Linux-Backend, das erst per vkeycode_map.py auf
# Linux-Input-Event-Codes uebersetzen muss.

PUL = ctypes.POINTER(ctypes.c_ulong)
VK_CONTROL, VK_SHIFT, VK_MENU = 0x11, 0x10, 0x12
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1


class _KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL),
    ]


# KORREKTUR 2026-09-03 (echte Windows-Session, per USBPcap-Handoff-Tests
# gefunden): die Union muss ALLE drei INPUT-Varianten (Keyboard/Maus/Hardware)
# enthalten, nicht nur KEYBDINPUT - sonst berechnet ctypes auf 64-bit eine zu
# kleine Struktur (32 statt der echten 40 Byte, weil MOUSEINPUT das groesste
# Unions-Mitglied ist). SendInput() liest cbSize strikt gegen die ECHTE
# Win32-INPUT-Groesse, nicht gegen das, was man ihr uebergibt - eine falsche
# Groesse fuehrt zu sofortigem, LAUTLOSEM Fehlschlag (Rueckgabewert 0,
# GetLastError()==87 ERROR_INVALID_PARAMETER), der bisherige Code hat den
# Rueckgabewert nie geprueft. Damit war send_hotkey() bisher komplett
# wirkungslos, ohne dass ein Fehler sichtbar wurde.
class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long), ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong), ("dwExtraInfo", PUL),
    ]


class _HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_short), ("wParamH", ctypes.c_ushort),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KeyBdInput), ("mi", _MouseInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", _InputUnion)]


def _send_vk(vk: int, key_up: bool) -> None:
    extra = ctypes.c_ulong(0)
    ii = _InputUnion()
    ii.ki = _KeyBdInput(vk, 0, KEYEVENTF_KEYUP if key_up else 0, 0, ctypes.pointer(extra))
    packet = _Input(INPUT_KEYBOARD, ii)
    ctypes.windll.kernel32.SetLastError(0)
    sent = ctypes.windll.user32.SendInput(1, ctypes.pointer(packet), ctypes.sizeof(packet))
    if sent != 1:
        raise OSError(f"SendInput fehlgeschlagen (vk={vk}), GetLastError()={ctypes.GetLastError()}")


def send_hotkey(vkeycode: int, ctrl: bool, shift: bool, alt: bool) -> None:  # UNGETESTET
    if not vkeycode:
        logger.warning("Hotkey ohne vkeycode - ignoriert")
        return
    mods = [vk for vk, held in ((VK_CONTROL, ctrl), (VK_SHIFT, shift), (VK_MENU, alt)) if held]
    try:
        for vk in mods:
            _send_vk(vk, key_up=False)
        _send_vk(vkeycode, key_up=False)
        _send_vk(vkeycode, key_up=True)
        for vk in reversed(mods):
            _send_vk(vk, key_up=True)
        logger.info("Hotkey ausgefuehrt: vkeycode=%s (mods=%s)", vkeycode, mods)
    except OSError as exc:
        logger.error("Hotkey fehlgeschlagen (vkeycode=%s): %s", vkeycode, exc)


def open_command(cmd: str) -> None:
    if not cmd:
        return
    try:
        # creationflags=CREATE_NO_WINDOW: verhindert ein aufblitzendes leeres
        # Konsolenfenster, falls cmd auf ein Konsolen-Programm (.bat/.exe ohne
        # eigenes GUI) zeigt und der Daemon selbst keine Konsole hat
        # (console=False in der gebauten .exe) - siehe hw_monitor.py fuer den
        # Bug, der das live gezeigt hat. Betrifft KEINE GUI-Programme (Spiele,
        # Browser etc.) - die bekommen so oder so nie ein Konsolenfenster.
        subprocess.Popen(shlex.split(cmd, posix=False), creationflags=subprocess.CREATE_NO_WINDOW)
        logger.info("Programm gestartet: %s", cmd)
    except OSError as exc:
        logger.error("Programm konnte nicht gestartet werden (%s): %s", cmd, exc)


def open_url(url: str) -> None:
    if not url:
        return
    try:
        import os
        os.startfile(url)  # stdlib, exaktes Windows-Gegenstueck zu xdg-open
        logger.info("Website geoeffnet: %s", url)
    except OSError as exc:
        logger.error("Website konnte nicht geoeffnet werden (%s): %s", url, exc)


def take_screenshot_interactive() -> None:  # UNGETESTET
    """Kein direktes Windows-Gegenstueck zur interaktiven Bereichsauswahl
    ohne Zusatz-Abhaengigkeit - nimmt stattdessen den GANZEN Bildschirm auf
    und speichert ihn (kein Clipboard-Kopieren, um keinen ungetesteten
    GDI-Clipboard-Code zu riskieren). Bekannte Abweichung vom Linux-
    Verhalten, keine offene TODO-Vereinfachung."""
    try:
        from PIL import ImageGrab
        import time
        img = ImageGrab.grab()
        out_dir = Path.home() / "Pictures" / "StreamDeckScreenshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"screenshot_{int(time.time())}.png"
        img.save(out_path)
        logger.info("Screenshot gespeichert: %s (kein Bereichs-Ausschnitt, kein Clipboard - siehe Docstring)", out_path)
    except Exception as exc:
        logger.error("Screenshot fehlgeschlagen: %s", exc)


def set_app_volume(app_name: str, direction: str, step_percent: int = 5) -> None:  # UNGETESTET
    """Braucht 'pycaw' + 'comtypes' (pip install pycaw comtypes) - bewusst
    NICHT Teil der Kern-Requirements, da reine Windows-Abhaengigkeit."""
    try:
        from pycaw.pycaw import AudioUtilities
    except ImportError:
        logger.error("App-Lautstaerke: 'pycaw' nicht installiert (pip install pycaw comtypes)")
        return
    try:
        sessions = AudioUtilities.GetAllSessions()
    except OSError as exc:
        logger.error("App-Lautstaerke: pycaw-Sitzungen konnten nicht gelesen werden: %s", exc)
        return

    sign = 1 if direction == "up" else -1
    delta = sign * step_percent / 100.0
    matched = False
    for session in sessions:
        proc = session.Process
        if not proc or app_name.lower() not in proc.name().lower():
            continue
        matched = True
        iface = session.SimpleAudioVolume
        new_vol = max(0.0, min(1.0, iface.GetMasterVolume() + delta))
        iface.SetMasterVolume(new_vol, None)
        logger.info("App-Lautstaerke: '%s' -> %.0f%%", app_name, new_vol * 100)
    if not matched:
        logger.info("App-Lautstaerke: kein aktiver Audio-Stream fuer '%s' gefunden - keine Aktion", app_name)


def play_sound(path: Path) -> None:
    try:
        import winsound
        if path.suffix.lower() != ".wav":
            logger.warning("Timer-Sound '%s' ist kein .wav - winsound (stdlib) spielt nur WAV ab", path)
            return
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception as exc:
        logger.warning("Ton konnte nicht abgespielt werden: %s", exc)


def show_message_popup(title: str, text: str) -> None:
    # Blockierend (modal) - aber process_monitor.py ruft das bereits aus
    # einem eigenen Hintergrund-Thread auf, blockiert also nicht den
    # DECK-ONE-Tastendruck-Loop.
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, 0)
    except OSError as exc:
        logger.error("Popup-Anzeige fehlgeschlagen: %s", exc)
