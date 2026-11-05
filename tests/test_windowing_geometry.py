"""Tests fuer die Layout-Geometrie (windowing/geometry.py) - reine Rechnung,
kein echtes Fenstersystem noetig."""
from streamdeck_driver.windowing.geometry import (
    Rect, monitors_from_dicts, rect_to_slot, resolve_monitor, slot_rect,
)

TWO_MONITORS = [
    {"x": 2560, "y": 0, "w": 1920, "h": 1080, "work_x": 2560, "work_y": 0, "work_w": 1920, "work_h": 1032},
    {"x": 0, "y": 0, "w": 2560, "h": 1440, "work_x": 0, "work_y": 0, "work_w": 2560, "work_h": 1368, "primary": True},
]


def test_monitors_are_sorted_left_to_right():
    mons = monitors_from_dicts(TWO_MONITORS)
    assert [m.index for m in mons] == [0, 1]
    assert mons[0].bounds.x == 0 and mons[0].primary
    assert mons[1].bounds.x == 2560


def test_full_slot_is_the_work_area_not_the_monitor():
    mons = monitors_from_dicts(TWO_MONITORS)
    assert slot_rect({"monitor": "left", "x": 0, "y": 0, "w": 1, "h": 1}, mons) == Rect(0, 0, 2560, 1368)


def test_right_half_of_secondary_monitor():
    mons = monitors_from_dicts(TWO_MONITORS)
    assert slot_rect({"monitor": "secondary", "x": 0.5, "y": 0, "w": 0.5, "h": 1}, mons) == Rect(3520, 0, 960, 1032)


def test_adjacent_slots_touch_without_gap_or_overlap():
    mons = monitors_from_dicts([{"x": 0, "y": 0, "w": 1366, "h": 768, "primary": True}])
    a = slot_rect({"x": 0, "y": 0, "w": 1 / 3, "h": 1}, mons)
    b = slot_rect({"x": 1 / 3, "y": 0, "w": 2 / 3, "h": 1}, mons)
    assert a.right == b.x and b.right == 1366


def test_missing_second_monitor_falls_back_to_primary():
    mons = monitors_from_dicts([{"x": 0, "y": 0, "w": 1920, "h": 1080, "primary": True}])
    assert resolve_monitor("secondary", mons) is mons[0]
    assert resolve_monitor("right", mons) is mons[0]
    assert resolve_monitor(5, mons) is mons[0]


def test_numeric_and_named_selectors():
    mons = monitors_from_dicts(TWO_MONITORS)
    assert resolve_monitor(1, mons) is mons[1]
    assert resolve_monitor("1", mons) is mons[1]
    assert resolve_monitor("primary", mons) is mons[0]
    assert resolve_monitor("left", mons) is mons[0]


def test_no_monitors_gives_none():
    assert resolve_monitor("primary", []) is None
    assert slot_rect({"monitor": "primary"}, []) is None


def test_rect_to_slot_roundtrip():
    mons = monitors_from_dicts(TWO_MONITORS)
    original = {"monitor": 1, "x": 0.25, "y": 0.1, "w": 0.5, "h": 0.8}
    rect = slot_rect(original, mons)
    back = rect_to_slot(rect, mons)
    assert back["monitor"] == 1
    assert abs(back["x"] - 0.25) < 0.002 and abs(back["w"] - 0.5) < 0.002
    assert slot_rect(back, mons).close_to(rect, 2)


def test_rect_outside_all_monitors_has_no_slot():
    mons = monitors_from_dicts(TWO_MONITORS)
    assert rect_to_slot(Rect(-5000, -5000, 100, 100), mons) is None
