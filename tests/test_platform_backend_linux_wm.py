"""Tests fuer das reine Parsing in platform_backend/linux_wm.py (Window-Calls-
'List'-Antwort, xrandr-Monitorliste) - ohne echtes GNOME/D-Bus."""
import json

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
        "minimized": False, "maximized": False, "focused": True,
    }
    assert wins[1]["title"] == "T" and wins[1]["focused"] is False
