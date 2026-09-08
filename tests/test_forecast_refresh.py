"""Tests fuer die Vorhersage-Seite (wetter_vorhersage): automatisches
Weiterschalten durch die Nowcast-Frames beim periodischen Hintergrund-
Refresh ("wie die Wolken ziehen sehen", Nutzerwunsch 2026-09-08) - kein
echtes Netzwerk/Rendering, render_current_page() wird dafuer durch einen
Zaehler ersetzt (analog zu test_long_press.py::test_radar_zoom_key_ignores_release)."""
import time

from streamdeck_driver import deckone_controller, radar
from streamdeck_driver.deckone_controller import DeckOneController


class _FakeDevice:
    connected = True

    class info:
        num_keys = 15
        image_size = (100, 100)

    def set_key_image(self, idx, img):
        return True

    def end_batch(self):
        pass


def test_forecast_radius_is_wider_than_the_resting_radar_view():
    assert radar.FORECAST_RADIUS_KM > radar.DEFAULT_RADIUS_KM


def test_forecast_idx_auto_advances_during_background_refresh(monkeypatch):
    config = {"deckone": {"active_profile": "wetter_vorhersage", "profiles": {
        "wetter_vorhersage": {"pages": [{"name": "Regenvorhersage", "keys": {}}]},
    }}}
    ctrl = DeckOneController(config)
    ctrl.device = _FakeDevice()
    ctrl.active_profile = "wetter_vorhersage"

    render_calls = []
    monkeypatch.setattr(ctrl, "render_current_page", lambda: render_calls.append(ctrl._forecast_idx))
    monkeypatch.setattr(radar, "_rainviewer_nowcast_frames", lambda: [{"time": 0}, {"time": 1}, {"time": 2}])
    monkeypatch.setattr(deckone_controller, "SYSTEM_REFRESH_INTERVAL_S", 0.02)

    ctrl.start_stat_refresh()
    time.sleep(0.13)
    ctrl.stop_stat_refresh()

    assert len(render_calls) >= 3
    # Zyklisch weiterschaltend (jeder Tick +1 mod 3), nicht bei einem festen
    # Frame stehenbleibend - Startpunkt ist absichtlich nicht festgelegt (die
    # erste Erhoehung passiert schon vor dem allerersten Render).
    for a, b in zip(render_calls, render_calls[1:]):
        assert b == (a + 1) % 3


def test_forecast_idx_does_not_advance_without_nowcast_frames(monkeypatch):
    config = {"deckone": {"active_profile": "wetter_vorhersage", "profiles": {
        "wetter_vorhersage": {"pages": [{"name": "Regenvorhersage", "keys": {}}]},
    }}}
    ctrl = DeckOneController(config)
    ctrl.device = _FakeDevice()
    ctrl.active_profile = "wetter_vorhersage"

    render_calls = []
    monkeypatch.setattr(ctrl, "render_current_page", lambda: render_calls.append(ctrl._forecast_idx))
    monkeypatch.setattr(radar, "_rainviewer_nowcast_frames", lambda: [])
    monkeypatch.setattr(deckone_controller, "SYSTEM_REFRESH_INTERVAL_S", 0.02)

    ctrl.start_stat_refresh()
    time.sleep(0.07)
    ctrl.stop_stat_refresh()

    assert render_calls and all(idx == 0 for idx in render_calls)
