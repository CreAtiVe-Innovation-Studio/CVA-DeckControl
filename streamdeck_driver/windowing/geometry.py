"""Reine Geometrie fuer das Fenster-Layout-Feature: Rechtecke, Monitore und
die Umrechnung eines relativen 'Slots' (Anteile 0..1 der Monitor-Arbeitsflaeche)
in echte Pixel. Bewusst ohne jeden OS-Aufruf, damit alles hier ohne echte
Fenster testbar ist (siehe tests/test_windowing_geometry.py).

Warum RELATIVE Slots statt fester Pixel: dasselbe Layout soll auf Rechnern mit
anderer Aufloesung/Skalierung funktionieren (Entwickler = Linux, Tester =
Windows, beide mit je zwei Monitoren, aber nicht identischen). Die Arbeitsflaeche
(= Monitor ohne Taskleiste/Panel) ist die Bezugsgroesse, daher ueberdeckt ein
'volle Hoehe'-Slot nie die Taskleiste."""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("streamdeck_driver.windowing.geometry")


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def contains_point(self, px: int, py: int) -> bool:
        return self.x <= px < self.right and self.y <= py < self.bottom

    def close_to(self, other: "Rect", tolerance: int = 3) -> bool:
        return (
            abs(self.x - other.x) <= tolerance and abs(self.y - other.y) <= tolerance
            and abs(self.w - other.w) <= tolerance and abs(self.h - other.h) <= tolerance
        )


@dataclass(frozen=True)
class Monitor:
    index: int  # Position von links nach rechts (bei gleichem x von oben nach unten)
    bounds: Rect
    work: Rect  # Arbeitsflaeche ohne Taskleiste/Panel
    primary: bool = False


@dataclass(frozen=True)
class WindowInfo:
    id: str
    app_id: str  # Prozessname ohne '.exe' (Windows) bzw. wm_class (Linux), klein
    title: str
    rect: Rect  # sichtbarer Rahmen, ohne unsichtbaren Fenster-Schatten
    minimized: bool = False
    maximized: bool = False
    focused: bool = False


def monitors_from_dicts(raw: list[dict]) -> list[Monitor]:
    """Backend-Rohdaten -> Monitor-Liste, links nach rechts sortiert. Erwartet
    pro Eintrag x/y/w/h (Gesamtflaeche) und optional work_x/work_y/work_w/
    work_h (Arbeitsflaeche, sonst = Gesamtflaeche) sowie primary."""
    ordered = sorted(raw, key=lambda m: (m["x"], m["y"]))
    result = []
    for idx, m in enumerate(ordered):
        bounds = Rect(m["x"], m["y"], m["w"], m["h"])
        work = Rect(
            m.get("work_x", m["x"]), m.get("work_y", m["y"]),
            m.get("work_w", m["w"]), m.get("work_h", m["h"]),
        )
        result.append(Monitor(idx, bounds, work, bool(m.get("primary", False))))
    return result


def windows_from_dicts(raw: list[dict]) -> list[WindowInfo]:
    return [
        WindowInfo(
            id=str(w["id"]), app_id=str(w.get("app_id", "")).lower(), title=str(w.get("title", "")),
            rect=Rect(w["x"], w["y"], w["w"], w["h"]),
            minimized=bool(w.get("minimized", False)), maximized=bool(w.get("maximized", False)),
            focused=bool(w.get("focused", False)),
        )
        for w in raw
    ]


def resolve_monitor(selector, monitors: list[Monitor]) -> Monitor | None:
    """selector: 'primary' | 'secondary' | 'left' | 'right' | Zahl (Index von
    links nach rechts). 'secondary' ist der erste NICHT-primaere Monitor.

    Fehlt der gewuenschte Monitor (z.B. nur ein Bildschirm angeschlossen),
    faellt die Aufloesung auf den primaeren Monitor zurueck statt zu scheitern -
    das Layout ist dann eben gestapelt, aber nichts landet ausserhalb des
    sichtbaren Bereichs."""
    if not monitors:
        return None
    primary = next((m for m in monitors if m.primary), monitors[0])
    sel = str(selector).strip().lower()
    if sel == "primary":
        return primary
    if sel == "secondary":
        others = [m for m in monitors if m is not primary]
        return others[0] if others else primary
    if sel == "left":
        return monitors[0]
    if sel == "right":
        return monitors[-1]
    if sel.isdigit() and int(sel) < len(monitors):
        return monitors[int(sel)]
    logger.warning("Monitor-Angabe '%s' nicht aufloesbar - nehme den primaeren Monitor", selector)
    return primary


def slot_rect(slot: dict, monitors: list[Monitor]) -> Rect | None:
    """Slot {monitor, x, y, w, h} (Anteile 0..1 der Arbeitsflaeche) -> Pixel.
    Linke/rechte Kante werden getrennt gerundet, damit zwei nebeneinander
    liegende Slots ohne 1-px-Luecke/Ueberlappung aneinanderstossen."""
    mon = resolve_monitor(slot.get("monitor", "primary"), monitors)
    if mon is None:
        return None
    wa = mon.work
    fx, fy = float(slot.get("x", 0.0)), float(slot.get("y", 0.0))
    fw, fh = float(slot.get("w", 1.0)), float(slot.get("h", 1.0))
    left, top = round(wa.x + fx * wa.w), round(wa.y + fy * wa.h)
    right, bottom = round(wa.x + (fx + fw) * wa.w), round(wa.y + (fy + fh) * wa.h)
    return Rect(left, top, right - left, bottom - top)


def monitor_at(point: tuple[int, int], monitors: list[Monitor]) -> Monitor | None:
    for m in monitors:
        if m.bounds.contains_point(*point):
            return m
    return None


def rect_to_slot(rect: Rect, monitors: list[Monitor]) -> dict | None:
    """Gegenstueck zu slot_rect() fuer das Aufnahme-Werkzeug: ein echtes
    Fensterrechteck -> relativer Slot (auf 3 Nachkommastellen gerundet)."""
    mon = monitor_at(rect.center, monitors)
    if mon is None:
        return None
    wa = mon.work
    return {
        "monitor": mon.index,
        "x": round((rect.x - wa.x) / wa.w, 3), "y": round((rect.y - wa.y) / wa.h, 3),
        "w": round(rect.w / wa.w, 3), "h": round(rect.h / wa.h, 3),
    }
