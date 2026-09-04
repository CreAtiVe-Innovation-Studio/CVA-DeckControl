"""Fallback fuer eine nicht erkannte Plattform (sys.platform weder linux*,
win32 noch darwin) - alle Aufrufe loggen nur eine Warnung statt den Treiber
mit einem AttributeError abstuerzen zu lassen."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger("streamdeck_driver.platform_backend.unsupported")


def _warn(action: str) -> None:
    logger.warning("'%s' wird auf dieser Plattform (%s) nicht unterstuetzt", action, sys.platform)


def send_hotkey(vkeycode: int, ctrl: bool, shift: bool, alt: bool) -> None:
    _warn("Hotkey")


def open_command(cmd: str) -> None:
    _warn("Programm oeffnen")


def open_url(url: str) -> None:
    _warn("Website oeffnen")


def take_screenshot_interactive() -> None:
    _warn("Screenshot")


def set_app_volume(app_name: str, direction: str, step_percent: int = 5) -> None:
    _warn("App-Lautstaerke")


def play_sound(path: Path) -> None:
    _warn("Ton abspielen")


def show_message_popup(title: str, text: str) -> None:
    _warn("Popup-Anzeige")
