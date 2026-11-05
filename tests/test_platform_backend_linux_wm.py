"""Tests fuer das reine Parsing in platform_backend/linux_wm.py (Window-Calls-
'List'-Antwort, xrandr-Monitorliste) - ohne echtes GNOME/D-Bus."""
import json

from streamdeck_driver.platform_backend import linux_wm
from streamdeck_driver.platform_backend.linux_wm import parse_window_list, parse_xrandr_monitors

XRANDR = """Monitors: 2
 0: +*DP-1 2560/597x1440/336+0+0  DP-1
 1: +HDMI-1 1920/509x1080/286+2560+0  HDMI-1
"""


def test_xrandr_two_monitors_with_primary_marker():
    mons = parse_xrandr_monitors(XRANDR)
    assert mons == [
        {"x": 0, "y": 0, "w": 2560, "h": 1440, "primary": True},
        {"x": 2560, "y": 0, "w": 1920, "h": 1080, "primary": False},
    ]


def test_xrandr_garbage_gives_empty_list():
    assert parse_xrandr_monitors("nix\nMonitors: 0\n") == []


def test_window_list_parsing_maps_fields_and_lowercases_class():
    raw = json.dumps([
        {"id": 12345, "wm_class": "Firefox", "focus": True, "x": 10, "y": 20, "width": 800, "height": 600},
        {"id": 7, "wm_class": "Code", "focus": False, "x": 0, "y": 0, "width": 100, "height": 50, "title": "T"},
    ])
    wins = parse_window_list(raw)
    assert wins[0] == {
        "id": "12345", "app_id": "firefox", "title": "", "x": 10, "y": 20, "w": 800, "h": 600,
        "minimized": False, "maximized": False, "focused": True, "window_type": 0,
    }
    assert wins[1]["title"] == "T" and wins[1]["focused"] is False


def test_list_windows_reads_geometry_and_state_per_window(monkeypatch):
    """Window Calls 'List' liefert (live geprueft) keine Geometrie: sie kommt per
    GetFrameRect, minimiert/maximiert per Details; Nicht-Fenster (Desktop-Icons,
    window_type != 0) werden ausgefiltert."""
    listing = json.dumps([
        {"id": 1, "wm_class": "Gjs", "title": "Desktop Icons", "window_type": 1, "focus": False},
        {"id": 2, "wm_class": "Firefox", "title": "Seite", "window_type": 0, "focus": True},
    ])

    def fake_call(method, signature="", *args):
        if method == "List":
            return {"data": [listing]}
        if method == "GetFrameRect":
            return {"data": [json.dumps({"x": 5, "y": 6, "width": 700, "height": 400})]}
        if method == "Details":
            return {"data": [json.dumps({"minimized": True, "maximized": 3, "fullscreen": False})]}
        raise AssertionError(method)

    monkeypatch.setattr(linux_wm, "_call", fake_call)
    wins = linux_wm.list_windows()
    assert len(wins) == 1
    w = wins[0]
    assert (w["id"], w["app_id"], w["x"], w["y"], w["w"], w["h"]) == ("2", "firefox", 5, 6, 700, 400)
    assert w["minimized"] is True and w["maximized"] is True and w["focused"] is True
