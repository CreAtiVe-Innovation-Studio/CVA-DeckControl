"""Tests fuer die profilspezifischen switch_profile-Icons in icon_render.py -
vorher sahen ALLE switch_profile-Tasten identisch aus (nur der Titeltext
unterschied sich), was auf dem Elgato Mini (reine Moduswahl, oft >10 Profile
ueber mehrere Seiten) die Tasten ununterscheidbar machte."""
from streamdeck_driver.icon_render import _resolve_profile_symbol, render_generated_icon


def test_resolve_profile_symbol_matches_known_keywords():
    assert _resolve_profile_symbol("timer") == "clock"
    assert _resolve_profile_symbol("wo_ist") == "pin"
    assert _resolve_profile_symbol("wetter_vorhersage") == "cloud"
    assert _resolve_profile_symbol("nachhilfe") == "book"


def test_resolve_profile_symbol_is_case_insensitive():
    assert _resolve_profile_symbol("RADAR") == "radar"


def test_resolve_profile_symbol_returns_none_for_unknown_profile():
    assert _resolve_profile_symbol("buero") is None


def test_switch_profile_icon_differs_by_profile():
    timer_icon = render_generated_icon((100, 100), "Timer", "switch_profile", "timer")
    radar_icon = render_generated_icon((100, 100), "Radar", "switch_profile", "radar")
    assert timer_icon.tobytes() != radar_icon.tobytes()


def test_switch_profile_icon_falls_back_without_keyword_match():
    fallback_a = render_generated_icon((100, 100), "Buero", "switch_profile", "buero")
    fallback_b = render_generated_icon((100, 100), "Anders", "switch_profile", "anders")
    # Beide ohne Keyword-Treffer - muessen dasselbe generische Pfeil-Symbol
    # bekommen (Titeltext unterscheidet sich, das Symbol selbst nicht).
    assert _resolve_profile_symbol("buero") is None
    assert _resolve_profile_symbol("anders") is None
