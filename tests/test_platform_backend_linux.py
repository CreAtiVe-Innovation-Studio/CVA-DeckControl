"""Test fuer die Wayland/X11-Session-Erkennung in platform_backend/linux.py -
live gefundener Bug: das Screenshot-Clipboard-Werkzeug war fest auf
'wl-copy' verdrahtet, das unter einer X11-Session lautlos fehlschlaegt
(reproduziert nach einem Wechsel von Wayland zu X11). Reine Logik, kein
echtes Display/System noetig - siehe tests/README.md fuer die Abgrenzung."""
from streamdeck_driver.platform_backend.linux import _is_wayland_session


def test_wayland_display_env_var_means_wayland(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    assert _is_wayland_session() is True


def test_xdg_session_type_wayland_means_wayland(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert _is_wayland_session() is True


def test_xdg_session_type_x11_means_not_wayland(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert _is_wayland_session() is False


def test_no_env_vars_defaults_to_not_wayland(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    assert _is_wayland_session() is False
