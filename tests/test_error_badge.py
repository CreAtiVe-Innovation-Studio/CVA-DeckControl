"""Tests fuer die sichtbare Fehler-Badge auf HA-abhaengigen Kacheln: die
ha_client.is_healthy()-Zustandsverfolgung und deren Verkabelung in
deckone_controller.py (kein echtes HTTP, kein echtes USB)."""
import requests

from streamdeck_driver import ha_client
from streamdeck_driver.deckone_controller import DeckOneController
from streamdeck_driver.icon_render import add_error_badge, blank_icon


class _FakeDevice:
    connected = True

    class info:
        num_keys = 15
        image_size = (100, 100)

    def set_key_image(self, idx, img):
        return True

    def end_batch(self):
        pass


def _make_ctrl(key):
    config = {
        "deckone": {
            "active_profile": "test",
            "profiles": {"test": {"pages": [{"name": "Test", "keys": {0: key}}]}},
        },
    }
    c = DeckOneController(config)
    c.device = _FakeDevice()
    return c


def test_add_error_badge_keeps_size_and_mode():
    img = blank_icon((100, 100))
    badged = add_error_badge(img)
    assert badged.size == (100, 100)
    assert badged.mode == "RGB"


def test_add_error_badge_changes_top_right_corner():
    img = blank_icon((100, 100))
    before = img.getpixel((90, 10))
    after = add_error_badge(img).getpixel((90, 10))
    assert before != after


def test_is_healthy_true_by_default(monkeypatch):
    monkeypatch.setattr(ha_client, "_healthy", True)
    assert ha_client.is_healthy() is True


def test_refresh_cache_failure_marks_unhealthy(monkeypatch):
    monkeypatch.setattr(ha_client, "_secrets", {"url": "http://ha.invalid", "token": "x"})
    monkeypatch.setattr(ha_client, "_cache", {})
    monkeypatch.setattr(ha_client, "_cache_time", 0.0)

    def _raise(*a, **kw):
        raise requests.RequestException("nicht erreichbar")

    monkeypatch.setattr(requests, "get", _raise)
    ha_client.get_state("sensor.does_not_matter")
    assert ha_client.is_healthy() is False


def test_call_service_success_marks_healthy(monkeypatch):
    monkeypatch.setattr(ha_client, "_secrets", {"url": "http://ha.invalid", "token": "x"})
    monkeypatch.setattr(ha_client, "_healthy", False)

    class _Resp:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(requests, "post", lambda *a, **kw: _Resp())
    assert ha_client.call_service("light", "turn_on", "light.test") is True
    assert ha_client.is_healthy() is True


def test_render_ha_key_shows_badge_when_unhealthy(monkeypatch):
    ctrl = _make_ctrl({
        "name": "Temp", "title": "Temp",
        "action": {"type": "ha_sensor", "entity_id": "sensor.temp"},
    })
    monkeypatch.setattr(ha_client, "get_state", lambda entity_id: None)
    monkeypatch.setattr(ha_client, "is_healthy", lambda: False)
    healthy_card = ctrl._render_ha_key(ctrl._current_page_keys()[0], (100, 100))

    monkeypatch.setattr(ha_client, "is_healthy", lambda: True)
    plain_card = ctrl._render_ha_key(ctrl._current_page_keys()[0], (100, 100))

    assert healthy_card.getpixel((90, 10)) != plain_card.getpixel((90, 10))


def test_render_weather_forecast_key_shows_badge_when_unhealthy(monkeypatch):
    ctrl = _make_ctrl({
        "name": "Vorhersage", "title": "Morgen",
        "action": {"type": "weather_forecast", "entity_id": "weather.home", "offset": 1},
    })
    monkeypatch.setattr(ha_client, "get_forecast", lambda entity_id, forecast_type: None)
    monkeypatch.setattr(ha_client, "is_healthy", lambda: False)
    badged = ctrl._render_weather_forecast_key(ctrl._current_page_keys()[0], (100, 100))

    monkeypatch.setattr(ha_client, "is_healthy", lambda: True)
    plain = ctrl._render_weather_forecast_key(ctrl._current_page_keys()[0], (100, 100))

    assert badged.getpixel((90, 10)) != plain.getpixel((90, 10))
