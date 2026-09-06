"""Tests fuer die reinen Geometrie-/Zoom-Berechnungen in location_map.py -
keine Home-Assistant-/Netzwerkzugriffe (die passieren nur in
_fetch_tracked_points()/_fetch_map(), hier nicht getestet)."""
import math

from streamdeck_driver import location_map


def test_pixel_coords_and_latlon_from_pixel_are_inverse():
    lat, lon, zoom = 51.2, 7.3, 11.5  # gebrochener Zoom muss auch funktionieren
    x, y = location_map._pixel_coords(lat, lon, zoom)
    lat2, lon2 = location_map._latlon_from_pixel(x, y, zoom)
    assert math.isclose(lat, lat2, abs_tol=1e-6)
    assert math.isclose(lon, lon2, abs_tol=1e-6)


def test_choose_zoom_to_fit_single_point_uses_default():
    zoom = location_map._choose_zoom_to_fit([(51.0, 7.0)], width_px=776, height_px=438)
    assert zoom == 17.0 - 3


def test_choose_zoom_to_fit_is_continuous_not_integer():
    """Kernanforderung aus dem Nutzer-Feedback ('zoomt stufenlos') - das
    Ergebnis darf keine Ganzzahl sein, sonst waere es wieder die alte,
    grobe Zoomstufen-Suche."""
    points = [(51.0, 7.0), (51.05, 7.05)]
    zoom = location_map._choose_zoom_to_fit(points, width_px=776, height_px=438)
    assert zoom != int(zoom)


def test_choose_zoom_to_fit_tighter_for_closer_points():
    close_points = [(51.0, 7.0), (51.01, 7.01)]
    far_points = [(51.0, 7.0), (51.5, 7.5)]
    zoom_close = location_map._choose_zoom_to_fit(close_points, width_px=776, height_px=438)
    zoom_far = location_map._choose_zoom_to_fit(far_points, width_px=776, height_px=438)
    assert zoom_close > zoom_far


def test_choose_zoom_to_fit_result_actually_fits_the_points():
    """End-to-end-Pruefung des eigentlichen Zwecks: bei dem berechneten Zoom
    muessen alle Punkte tatsaechlich innerhalb der Bildflaeche (abzueglich
    Rand) liegen."""
    points = [(51.0, 7.0), (51.2, 7.3), (50.9, 6.8)]
    width, height, margin = 776, 438, 28
    zoom = location_map._choose_zoom_to_fit(points, width, height, margin_px=margin)
    xs, ys = zip(*(location_map._pixel_coords(lat, lon, zoom) for lat, lon in points))
    assert max(xs) - min(xs) <= width - 2 * margin + 1e-6
    assert max(ys) - min(ys) <= height - 2 * margin + 1e-6


def test_best_axis_shift_returns_zero_when_no_slack():
    assert location_map._best_axis_shift([10.0, 50.0], pitch=169, visible=100, slack=0) == 0.0


def test_best_axis_shift_improves_centering_within_slack():
    """Ein Punkt sitzt bewusst nah am Rand seiner Kachel (Modulo pitch nahe
    0) - mit genug Spielraum sollte die Suche einen Versatz finden, der ihn
    naeher an die Mitte (visible/2) rueckt."""
    pitch, visible = 169, 100
    coord = 5.0  # nahe am linken Rand der ersten Kachel
    baseline_offset = abs((coord % pitch) - visible / 2)
    shift = location_map._best_axis_shift([coord], pitch, visible, slack=80)
    improved_offset = abs(((coord + shift) % pitch) - visible / 2)
    assert improved_offset <= baseline_offset
