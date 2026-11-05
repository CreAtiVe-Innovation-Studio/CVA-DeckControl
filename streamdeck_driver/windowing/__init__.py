"""Fenster-Layouts ('Unterricht'-Modus): Apps oeffnen, positionieren, per Taste
in den Vordergrund holen. Siehe SEITEN-LOGIK.md Abschnitt 4.14."""
from __future__ import annotations

import logging

from . import engine

logger = logging.getLogger("streamdeck_driver.windowing")

ACTION_TYPES = (
    "layout_start", "layout_arrange", "layout_focus", "layout_page", "layout_maximize", "layout_stop",
    "layout_hotkey",
)


def configure(config: dict):
    return engine.configure(config)


def run_action(action: dict) -> None:
    eng = engine.get_engine()
    if eng is None:
        logger.warning("Layout-Aktion '%s', aber kein 'window_layouts'-Block in der Config - ignoriert", action.get("type"))
        return
    layout = action.get("layout")
    kind = action.get("type")
    if kind == "layout_start":
        eng.start(layout)
    elif kind == "layout_arrange":
        eng.arrange(layout)
    elif kind == "layout_focus":
        eng.focus_app(action.get("app", ""), layout)
    elif kind == "layout_page":
        eng.page(action.get("direction", "next"), layout)
    elif kind == "layout_hotkey":
        eng.focus_then_hotkey(
            action.get("app", ""), layout, action.get("vkeycode"),
            action.get("ctrl", False), action.get("shift", False), action.get("alt", False),
        )
    elif kind == "layout_maximize":
        eng.toggle_maximize(layout)
    elif kind == "layout_stop":
        eng.stop_auto_placer()
