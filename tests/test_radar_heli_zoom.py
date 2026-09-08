"""Tests fuer den Helikopter-Tiefflug-Zoom in radar.py (Nutzerwunsch
2026-09-08: "bei Tiefueberflug von Helikopter gerne naeher als 5km") - reine
Logik (Distanzrechnung + Listen-Filterung), kein Netzwerk. HOME_LAT/HOME_LON
werden auf einen beliebigen, oeffentlich bekannten Punkt umgebogen (Wien),
damit die Tests nicht von echten persoenlichen Koordinaten abhaengen."""
from streamdeck_driver import radar

WIEN_LAT, WIEN_LON = 48.2082, 16.3738


def _heli_at(dist_km: float, category: str = "A7") -> dict:
    """Ein erfundenes Flugzeug knapp noerdlich von WIEN_LAT/LON, ungefaehr
    dist_km entfernt (1 Breitengrad ~ 111km, reicht fuer Testzwecke)."""
    return {"lat": WIEN_LAT + dist_km / 111.0, "lon": WIEN_LON, "category": category}


def test_find_nearby_heli_ignores_airliners(monkeypatch):
    monkeypatch.setattr(radar, "HOME_LAT", WIEN_LAT)
    monkeypatch.setattr(radar, "HOME_LON", WIEN_LON)
    airliner = _heli_at(1.0, category="A3")
    ac, dist = radar._find_nearby_heli([airliner])
    assert ac is None
    assert dist is None


def test_find_nearby_heli_ignores_far_away_heli(monkeypatch):
    monkeypatch.setattr(radar, "HOME_LAT", WIEN_LAT)
    monkeypatch.setattr(radar, "HOME_LON", WIEN_LON)
    far_heli = _heli_at(radar.HELI_DETECT_RADIUS_KM + 5)
    ac, dist = radar._find_nearby_heli([far_heli])
    assert ac is None


def test_find_nearby_heli_finds_close_heli(monkeypatch):
    monkeypatch.setattr(radar, "HOME_LAT", WIEN_LAT)
    monkeypatch.setattr(radar, "HOME_LON", WIEN_LON)
    close_heli = _heli_at(1.0)
    ac, dist = radar._find_nearby_heli([close_heli])
    assert ac is close_heli
    assert 0.5 < dist < 1.5


def test_find_nearby_heli_picks_the_closest_one(monkeypatch):
    monkeypatch.setattr(radar, "HOME_LAT", WIEN_LAT)
    monkeypatch.setattr(radar, "HOME_LON", WIEN_LON)
    near, far = _heli_at(1.0), _heli_at(4.0)
    ac, dist = radar._find_nearby_heli([far, near])
    assert ac is near


def test_decide_view_zooms_closer_than_approach_minimum_for_a_close_heli(monkeypatch):
    monkeypatch.setattr(radar, "HOME_LAT", WIEN_LAT)
    monkeypatch.setattr(radar, "HOME_LON", WIEN_LON)
    monkeypatch.setattr(radar, "_lightning_km", lambda: None)
    close_heli = _heli_at(0.5)
    lat, lon, radius, warning = radar._decide_view([close_heli])
    assert radius < radar.APPROACH_MIN_RADIUS_KM
    assert radius >= radar.HELI_MIN_RADIUS_KM
    assert "Helikopter" in warning


def test_decide_view_falls_back_to_default_without_a_heli(monkeypatch):
    monkeypatch.setattr(radar, "HOME_LAT", WIEN_LAT)
    monkeypatch.setattr(radar, "HOME_LON", WIEN_LON)
    monkeypatch.setattr(radar, "_lightning_km", lambda: None)
    lat, lon, radius, warning = radar._decide_view([])
    assert radius == radar.DEFAULT_RADIUS_KM
    assert warning is None


def test_zoom_cycle_has_a_tighter_step_than_the_old_five_km_floor():
    numeric_steps = [v for v in radar.ZOOM_CYCLE if isinstance(v, (int, float))]
    assert min(numeric_steps) < 5.0
