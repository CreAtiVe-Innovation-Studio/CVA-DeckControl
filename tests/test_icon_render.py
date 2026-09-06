"""Tests fuer die profilspezifischen switch_profile-Icons in icon_render.py -
vorher sahen ALLE switch_profile-Tasten identisch aus (nur der Titeltext
unterschied sich), was auf dem Elgato Mini (reine Moduswahl, oft >10 Profile
ueber mehrere Seiten) die Tasten ununterscheidbar machte."""
import io

from PIL import Image

from streamdeck_driver import icon_render
from streamdeck_driver.icon_render import _resolve_profile_symbol, render_generated_icon, render_key_icon


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


def test_render_key_icon_ignores_static_switch_profile_asset(monkeypatch, tmp_path):
    """Live gefundener Bug: existiert eine generische 'switch_profile.png'
    unter assets/generated-icons/ (z.B. aus einem frueheren Icon-Generierungs-
    Lauf), hat sie IMMER Vorrang vor render_generated_icon() bekommen - damit
    saehen alle switch_profile-Tasten trotz der Keyword-Symbole oben weiterhin
    identisch aus. render_key_icon() muss fuer switch_profile diese Datei
    ignorieren und direkt zum profilspezifischen Symbol gehen."""
    (tmp_path / "switch_profile.png").write_bytes(_tiny_png())
    monkeypatch.setattr(icon_render, "GENERATED_ICON_DIR", tmp_path)

    timer_icon = render_key_icon({"type": "generated"}, (100, 100), "Timer", "switch_profile", "timer")
    radar_icon = render_key_icon({"type": "generated"}, (100, 100), "Radar", "switch_profile", "radar")
    assert timer_icon.tobytes() != radar_icon.tobytes()


def _tiny_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (200, 50, 50)).save(buf, format="PNG")
    return buf.getvalue()
