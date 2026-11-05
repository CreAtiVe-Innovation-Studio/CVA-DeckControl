"""Fensterverwaltung fuer Plattformen OHNE Implementierung (macOS, unbekannte
Systeme): liefert leere Listen und loggt einmalig, statt abzustuerzen. Die
Layout-Tasten tun dort einfach nichts."""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger("streamdeck_driver.platform_backend.no_wm")
_warned = False


def _warn() -> None:
    global _warned
    if not _warned:
        logger.warning("Fenster-Layouts werden auf dieser Plattform (%s) nicht unterstuetzt", sys.platform)
        _warned = True


def list_windows() -> list[dict]:
    _warn()
    return []


def list_monitors() -> list[dict]:
    _warn()
    return []


def move_window(window_id, x: int, y: int, w: int, h: int) -> None:
    _warn()


def focus_window(window_id) -> None:
    _warn()


def maximize_window(window_id) -> None:
    _warn()


def restore_window(window_id) -> None:
    _warn()


def minimize_window(window_id) -> None:
    _warn()


def start_minimized(command: str, cwd: str | None = None) -> None:
    _warn()
