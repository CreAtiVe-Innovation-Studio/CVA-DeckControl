"""Tests fuer die reinen Geo-/Web-Mercator-Hilfsfunktionen in radar.py - kein
Netzwerk-/Hardwarezugriff, importierbar auch ohne config/location.yaml
(faellt dann auf Platzhalter-Koordinaten 0,0 zurueck, siehe radar.py::
_load_home_location, betrifft diese Tests aber nicht - sie rechnen mit
eigenen, festen Koordinaten)."""
import math

from streamdeck_driver import radar


def test_haversine_zero_distance_for_identical_points():
    assert radar._haversine_km(50.0, 7.0, 50.0, 7.0) == 0.0


def test_haversine_known_distance_cologne_duesseldorf():
    # Koeln/Bonn <-> Duesseldorf, beide Koordinaten schon im Modul als
    # oeffentliche Flughafenkoordinaten vorhanden (siehe radar.py::CGN/DUS).
    # Erwarteter Bereich ist die tatsaechliche Luftlinie zwischen den beiden
    # Koordinaten (~54km) mit Toleranz - dient als Regressionsschutz gegen
    # eine kaputte Haversine-Formel, nicht als exakte Kilometer-Behauptung.
    km = radar._haversine_km(*radar.CGN, *radar.DUS)
    assert 48 < km < 60


def test_bearing_north_is_zero():
    bearing = radar._bearing_deg(50.0, 7.0, 51.0, 7.0)  # rein noerdlich
    assert bearing == 0 or bearing > 359


def test_bearing_east_is_ninety():
    bearing = radar._bearing_deg(50.0, 7.0, 50.0, 8.0)  # rein oestlich (grob)
    assert 85 < bearing < 95


def test_angle_diff_wraps_around_360():
    assert radar._angle_diff(350, 10) == 20
    assert radar._angle_diff(10, 350) == 20
    assert radar._angle_diff(0, 0) == 0


def test_pixel_coords_and_latlon_from_pixel_are_inverse():
    lat, lon, zoom = 48.2082, 16.3738, 10  # Wien - beliebiger, oeffentlich bekannter Punkt
    x, y = radar._pixel_coords(lat, lon, zoom)
    lat2, lon2 = radar._latlon_from_pixel(x, y, zoom)
    assert math.isclose(lat, lat2, abs_tol=1e-6)
    assert math.isclose(lon, lon2, abs_tol=1e-6)


def test_pixel_coords_doubles_with_each_zoom_level():
    lat, lon = 51.0, 7.0
    x1, y1 = radar._pixel_coords(lat, lon, 5)
    x2, y2 = radar._pixel_coords(lat, lon, 6)
    assert math.isclose(x2, x1 * 2, rel_tol=1e-9)
    assert math.isclose(y2, y1 * 2, rel_tol=1e-9)


def test_choose_zoom_returns_higher_zoom_for_smaller_radius():
    """Kleinerer Sichtradius = staerker reingezoomt (hoehere Zoomstufe) -
    das war mal genau andersrum kaputt (siehe Kommentar in radar.py::
    _choose_zoom, 'KORRIGIERT'), diese Regression darf nicht zurueckkommen."""
    z_close = radar._choose_zoom(radius_km=5.0, lat=51.0)
    z_far = radar._choose_zoom(radius_km=40.0, lat=51.0)
    assert z_close > z_far
