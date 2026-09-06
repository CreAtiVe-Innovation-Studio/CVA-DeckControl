"""Tests fuer die kurz/lang-Druck-Unterscheidung in deckone_controller.py -
gegen ein Fake-Geraet (kein echtes USB), mit echtem time.sleep() fuer die
Haltedauer (kurz genug um Tests nicht spuerbar zu verlangsamen)."""
import time

import pytest

from streamdeck_driver import actions
from streamdeck_driver.deckone_controller import DeckOneController, LONG_PRESS_THRESHOLD_S


class _FakeDevice:
    connected = True

    class info:
        num_keys = 15
        image_size = (100, 100)

    def set_key_image(self, idx, img):
        return True

    def end_batch(self):
        pass


@pytest.fixture
def ctrl():
    config = {
        "deckone": {
            "active_profile": "test",
            "profiles": {
                "test": {
                    "pages": [{
                        "name": "Test",
                        "keys": {
                            0: {
                                "name": "k0", "title": "K0",
                                "action": {"type": "open", "linux_command": "short"},
                                "action_long": {"type": "open", "linux_command": "long"},
                            },
                            1: {
                                "name": "k1", "title": "K1",
                                "action": {"type": "open", "linux_command": "only-short"},
                            },
                        },
                    }],
                },
            },
        },
    }
    c = DeckOneController(config)
    c.device = _FakeDevice()
    return c


@pytest.fixture
def dispatched(monkeypatch):
    calls = []
    monkeypatch.setattr(actions, "dispatch", lambda action, label: calls.append(action.get("linux_command")))
    return calls


def test_short_press_fires_normal_action(ctrl, dispatched):
    ctrl.handle_key(0, True)
    ctrl.handle_key(0, False)
    assert dispatched == ["short"]


def test_long_press_fires_action_long(ctrl, dispatched):
    ctrl.handle_key(0, True)
    time.sleep(LONG_PRESS_THRESHOLD_S + 0.05)
    ctrl.handle_key(0, False)
    assert dispatched == ["long"]


def test_long_press_without_action_long_falls_back_to_normal_action(ctrl, dispatched):
    ctrl.handle_key(1, True)
    time.sleep(LONG_PRESS_THRESHOLD_S + 0.05)
    ctrl.handle_key(1, False)
    assert dispatched == ["only-short"]


def test_release_without_matching_press_does_not_crash(ctrl, dispatched):
    """Kann in der Praxis vorkommen (z.B. Daemon-Neustart mitten im
    gehaltenen Druck) - darf nicht crashen, soll die normale (kurze)
    Aktion ausloesen (Haltedauer dann 0)."""
    ctrl.handle_key(0, False)
    assert dispatched == ["short"]


def test_radar_zoom_key_ignores_release(monkeypatch):
    config = {"deckone": {"active_profile": "radar", "profiles": {"radar": {"pages": [{"name": "Radar", "keys": {}}]}}}}
    ctrl = DeckOneController(config)
    ctrl.device = _FakeDevice()
    ctrl.active_profile = "radar"
    monkeypatch.setattr(ctrl, "render_current_page", lambda: None)

    zoom_key = 14  # unten rechts, siehe radar.GRID_COLS * radar.GRID_ROWS - 1
    ctrl.handle_key(zoom_key, True)
    assert ctrl._radar_zoom_idx == 1
    ctrl.handle_key(zoom_key, False)  # darf NICHTS mehr aendern
    assert ctrl._radar_zoom_idx == 1
