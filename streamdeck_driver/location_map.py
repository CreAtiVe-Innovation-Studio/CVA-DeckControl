"""'Wo ist?' - Standort-Karte fuer getrackte Personen/Geraete, komponiert wie
radar.py (ein grosses Kartenbild, in Kacheln zerschneiden), aber bewusst ein
EIGENES, unabhaengiges Modul - separat vom Radar, nicht gemeinsamer Code,
nur gemeinsames MUSTER (siehe grid.py fuer den tatsaechlich geteilten Teil:
die Grid-Geometrie, damit das hier auch auf anderen Geraete-Rastern als der
DECK-ONE-5x3-Flaeche laeuft).

Datenquelle bewusst NICHT direkt Apple Find My oder WhatsApp: Find My hat nur
eine inoffizielle, jederzeit brechbare API (pyicloud & Forks), WhatsApp
Live-Standort hat ueberhaupt keine API (Ende-zu-Ende-verschluesselt zwischen
den Apps selbst, siehe Projekt-Recherche). Stattdessen ueber Home Assistants
`person`/`device_tracker`-Entities (ha_client.py) - Apple-seitige Bruch-
Anfaelligkeit ist dann Sache der HA-/iCloud3-Community, nicht dieses Codes.
Ohne konfigurierte Tracker-Entities zeigt die Seite einen Platzhalter statt
zu crashen oder leer zu bleiben."""
from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass, field

import requests
from PIL import Image, ImageDraw, ImageOps

from . import ha_client
from .grid import DECKONE_GRID, Grid
from .icon_render import _load_font
from .paths import app_root
from .radar import HOME_LAT, HOME_LON, _bearing_deg, _haversine_km  # geteilte Geo-Basisfunktionen

logger = logging.getLogger("streamdeck_driver.location_map")

TILE_SIZE = 256
_tile_cache: dict[tuple[int, int, int], Image.Image] = {}


# -- Web-Mercator-Hilfsfunktionen (eigene Kopie, siehe Moduldocstring) -------

def _pixel_coords(lat: float, lon: float, zoom: float) -> tuple[float, float]:
    """Nimmt bewusst einen FLIESSKOMMA-Zoom entgegen (nicht nur ganzzahlig) -
    Web-Mercator-Pixelkoordinaten skalieren stufenlos mit 2**zoom, das
    erlaubt einen exakt berechneten (nicht nur zwischen OSM-Ganzzahlstufen
    gesuchten) Ziel-Zoom, siehe _choose_zoom_to_fit()."""
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n * TILE_SIZE
    y = (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n * TILE_SIZE
    return x, y


def _latlon_from_pixel(x: float, y: float, zoom: float) -> tuple[float, float]:
    n = 2.0 ** zoom
    lon = x / (n * TILE_SIZE) * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / (n * TILE_SIZE)))))
    return lat, lon


def _dark_mode(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(img)
    inverted = ImageOps.invert(gray)
    darker = inverted.point(lambda p: int((p / 255) ** 1.3 * 255))
    return darker.convert("RGB")


def _fetch_tile(z: int, x: int, y: int) -> Image.Image:
    key = (z, x, y)
    cached = _tile_cache.get(key)
    if cached is not None:
        return cached
    url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    headers = {"User-Agent": "streamdeck-driver-location-map/1.0 (privater Eigenbedarf)"}
    resp = requests.get(url, headers=headers, timeout=6)
    resp.raise_for_status()
    img = _dark_mode(Image.open(io.BytesIO(resp.content)).convert("RGB"))
    if len(_tile_cache) > 300:
        _tile_cache.clear()
    _tile_cache[key] = img
    return img


def _choose_zoom_to_fit(points: list[tuple[float, float]], width_px: int, height_px: int,
                         margin_px: int = 28, min_zoom: float = 2.0, max_zoom: float = 17.0) -> float:
    """Stufenloser (gebrochener) Zoom, bei dem alle Punkte (inkl. Rand) GENAU
    ins Bild passen - analytisch berechnet statt (wie eine fruehere Version)
    nur zwischen ganzzahligen OSM-Zoomstufen zu waehlen (Nutzerfeedback
    2026-09-06: "zoomt stufenlos, bis es super passt" - radar.py::_fetch_map
    macht mit fractional zoom + Resize genau das schon fuers Radar).
    Web-Mercator-Pixelabstaende verdoppeln sich pro Zoomstufe exakt, der
    noetige Zoom ergibt sich also direkt aus log2(verfuegbarer Platz /
    tatsaechlicher Punkte-Abstand) bei einem beliebigen Referenz-Zoom, ohne
    raten/suchen zu muessen."""
    if len(points) < 2:
        return max_zoom - 3
    ref_zoom = 10.0
    xs, ys = zip(*(_pixel_coords(lat, lon, ref_zoom) for lat, lon in points))
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    avail_x, avail_y = width_px - 2 * margin_px, height_px - 2 * margin_px
    candidates = [max_zoom]
    if span_x > 0:
        candidates.append(ref_zoom + math.log2(avail_x / span_x))
    if span_y > 0:
        candidates.append(ref_zoom + math.log2(avail_y / span_y))
    return max(min_zoom, min(candidates))


def _best_axis_shift(coords: list[float], pitch: int, visible: int, slack: float) -> float:
    """Sucht den Verschiebungsbetrag (innerhalb des verfuegbaren `slack`, also
    ohne dass irgendein Punkt aus dem sichtbaren Bild faellt), bei dem alle
    Punkte auf dieser Achse moeglichst NAH AN DER MITTE ihrer jeweils
    zugewiesenen Kachel landen. Bewusst KEIN Snap auf die Kachel-Mitte
    (waere geografisch falsch, Nutzerfeedback 2026-09-06) - stattdessen wird
    Zoom/Zentrum so gewaehlt, dass die echte Position von selbst zentral
    liegt. X- und Y-Achse sind unabhaengig (Spalten/Zeilen-Raster), deshalb
    getrennte 1D-Suchen statt einer teuren 2D-Suche."""
    if slack <= 0:
        return 0.0
    best_shift, best_score = 0.0, float("inf")
    step = max(1.0, slack / 40)
    shift = -slack / 2
    while shift <= slack / 2:
        worst = 0.0
        for c in coords:
            offset = (c + shift) % pitch
            if offset >= visible:
                worst = float("inf")  # faellt in die Luecke zwischen Kacheln - ungueltig
                break
            worst = max(worst, abs(offset - visible / 2))
        if worst < best_score:
            best_score, best_shift = worst, shift
        shift += step
    return best_shift


def _fetch_map(center_lat: float, center_lon: float, zoom: float, width_px: int, height_px: int) -> Image.Image:
    """Generische Version von radar.py::_fetch_map - Groesse per Parameter
    statt fest auf EFFECTIVE_W/H verdrahtet, damit das auf jedem Grid laeuft.
    Wie dort: OSM liefert nur GANZZAHLIGE Zoomstufen, bei gebrochenem `zoom`
    wird bei der naechsten Ganzzahl geholt und die Differenz per Resize
    ausgeglichen, damit trotzdem der exakte (gebrochene) Ziel-Zoom
    herauskommt - siehe _choose_zoom_to_fit() fuer wie der berechnet wird."""
    zoom_int = round(zoom)
    scale = 2 ** (zoom - zoom_int)  # >1 = staerker rein als zoom_int, <1 = weiter raus
    fetch_w = max(1, round(width_px / scale))
    fetch_h = max(1, round(height_px / scale))

    cx, cy = _pixel_coords(center_lat, center_lon, zoom_int)
    left, top = cx - fetch_w / 2, cy - fetch_h / 2
    tile_x0, tile_y0 = int(left // TILE_SIZE), int(top // TILE_SIZE)
    tile_x1, tile_y1 = int((left + fetch_w) // TILE_SIZE), int((top + fetch_h) // TILE_SIZE)
    n = 2 ** zoom_int

    canvas = Image.new("RGB", ((tile_x1 - tile_x0 + 1) * TILE_SIZE, (tile_y1 - tile_y0 + 1) * TILE_SIZE), (25, 25, 30))
    for tx in range(tile_x0, tile_x1 + 1):
        for ty in range(tile_y0, tile_y1 + 1):
            if ty < 0 or ty >= n:
                continue
            try:
                tile_img = _fetch_tile(zoom_int, tx % n, ty)
            except Exception as exc:
                logger.warning("Kartenkachel %s/%s/%s fehlgeschlagen: %s", zoom_int, tx % n, ty, exc)
                continue
            canvas.paste(tile_img, ((tx - tile_x0) * TILE_SIZE, (ty - tile_y0) * TILE_SIZE))

    crop_left, crop_top = int(left - tile_x0 * TILE_SIZE), int(top - tile_y0 * TILE_SIZE)
    cropped = canvas.crop((crop_left, crop_top, crop_left + fetch_w, crop_top + fetch_h))
    if (fetch_w, fetch_h) != (width_px, height_px):
        cropped = cropped.resize((width_px, height_px), Image.LANCZOS)
    return cropped


def _project(lat: float, lon: float, zoom: float, center_px: tuple[float, float],
             width_px: int, height_px: int) -> tuple[float, float]:
    x, y = _pixel_coords(lat, lon, zoom)
    cx, cy = center_px
    return width_px / 2 + (x - cx), height_px / 2 + (y - cy)


# -- Getrackte Punkte (Home Assistant) ---------------------------------------

@dataclass
class TrackedPoint:
    name: str
    lat: float
    lon: float
    entity_id: str


def _fake_tracked_points() -> list[TrackedPoint]:
    """NUR ZUM TESTEN (siehe CVA_FAKE_TRACKERS unten) - synthetische Punkte in
    unterschiedlicher Entfernung/Richtung von zuhause, um den vollen Render-
    Pfad (Zoom-Fit ueber mehrere Punkte, Pin-Platzierung, Info-Karte) auf
    echter Hardware zu pruefen, ohne dass schon eine echte HA-Tracker-
    Integration (z.B. iCloud3) eingerichtet ist. VOR dem Release/Commit
    wieder entfernen."""
    # Bewusst deutlich voneinander UND von zuhause getrennt (~8-15km
    # zueinander) - ein Testpunkt direkt neben zuhause wuerde bei jedem
    # sinnvollen Zoom zwangslaeufig dieselbe Kachel treffen (reine Geometrie,
    # kein Bug) und damit keine faire Pruefung der Kachel-Verteilung sein.
    return [
        TrackedPoint("Norden", HOME_LAT + 0.09, HOME_LON + 0.01, "fake.north"),
        TrackedPoint("Osten", HOME_LAT - 0.02, HOME_LON + 0.14, "fake.east"),
        TrackedPoint("Sueden", HOME_LAT - 0.11, HOME_LON - 0.06, "fake.south"),
    ]


def _fetch_tracked_points() -> list[TrackedPoint]:
    """Bevorzugt 'person'-Entities (haben einen sprechenden Namen ueber
    friendly_name) - faellt auf 'device_tracker' zurueck, falls keine
    person-Entity mit Koordinaten existiert (z.B. bei einem HA-Setup ohne
    eingerichtete Personen, nur rohe Geraete-Tracker)."""
    import os
    if os.environ.get("CVA_FAKE_TRACKERS") == "1":
        return _fake_tracked_points()
    points = []
    for entity in ha_client.list_domain("person"):
        attrs = entity.get("attributes", {})
        lat, lon = attrs.get("latitude"), attrs.get("longitude")
        if lat is not None and lon is not None:
            name = attrs.get("friendly_name") or entity["entity_id"].split(".", 1)[-1]
            points.append(TrackedPoint(name, float(lat), float(lon), entity["entity_id"]))
    if points:
        return points
    for entity in ha_client.list_domain("device_tracker"):
        attrs = entity.get("attributes", {})
        lat, lon = attrs.get("latitude"), attrs.get("longitude")
        if lat is not None and lon is not None:
            name = attrs.get("friendly_name") or entity["entity_id"].split(".", 1)[-1]
            points.append(TrackedPoint(name, float(lat), float(lon), entity["entity_id"]))
    return points


# -- Frame-Aufbau -------------------------------------------------------------

@dataclass
class LocationFrame:
    image: Image.Image
    grid: Grid
    points: dict[tuple[int, int], TrackedPoint] = field(default_factory=dict)  # (col,row) -> Punkt
    zoom: float = 0.0
    center: tuple[float, float] = (0.0, 0.0)  # Pixelkoordinaten bei `zoom`


_PIN_COLOR = (56, 189, 248)
_HOME_COLOR = (167, 139, 250)


def _draw_pin(draw: ImageDraw.ImageDraw, px: float, py: float, color: tuple) -> None:
    """Nur ein grosser, kontrastreicher Punkt - bewusst OHNE Namens-Label auf
    der Karte selbst: eine Kachel ist nur 100x100px und wird an einer
    beliebigen Stelle relativ zum Punkt hart abgeschnitten, ein Textlabel
    daneben/darunter landet dadurch abhaengig von der Position haeufig
    abgeschnitten am Kachelrand (live gemeldet: "nicht gut zu sehen",
    Label nur noch als 1-2 Pixelzeilen sichtbar). Name/Distanz/Richtung gibt
    es stattdessen ueber die Info-Karte bei Tastendruck (siehe
    render_info_card), die den vollen Kachel-Platz dafuer hat."""
    r = 13
    draw.ellipse((px - r - 2, py - r - 2, px + r + 2, py + r + 2), fill=(10, 10, 14))
    draw.ellipse((px - r, py - r, px + r, py + r), fill=color, outline=(255, 255, 255), width=3)


def build_frame(grid: Grid = DECKONE_GRID) -> LocationFrame:
    points = _fetch_tracked_points()
    all_latlon = [(HOME_LAT, HOME_LON)] + [(p.lat, p.lon) for p in points]
    margin_px = 28

    # "Zuhause" zaehlt mit rein, WELCHER Zoom noetig ist (damit es im Bild
    # bleibt), bestimmt aber NICHT die Bildmitte - der Fokus soll auf den
    # getrackten Personen liegen, nicht zwingend auf zuhause zentriert sein
    # (Nutzerfeedback 2026-09-06).
    zoom = _choose_zoom_to_fit(all_latlon, grid.effective_w, grid.effective_h)
    if not points:
        center_lat, center_lon = HOME_LAT, HOME_LON
    else:
        people_px = [_pixel_coords(lat, lon, zoom) for lat, lon in ((p.lat, p.lon) for p in points)]
        base_cx = sum(x for x, _ in people_px) / len(people_px)
        base_cy = sum(y for _, y in people_px) / len(people_px)

        # Zusaetzlich (auf beiden Achsen unabhaengig) den Versatz suchen, der
        # ALLE Punkte (inkl. zuhause) moeglichst nah an die Mitte ihrer
        # jeweiligen Kachel rueckt, OHNE die echte geografische Position zu
        # veraendern (kein Snap - Nutzerfeedback: "muss geografisch korrekt
        # bleiben") - stattdessen wird innerhalb des nach dem Zoom-Fit noch
        # uebrigen Spielraums ("slack") am Zentrum gefeilt.
        all_px = [_pixel_coords(lat, lon, zoom) for lat, lon in all_latlon]
        frame_xs = [x - base_cx + grid.effective_w / 2 for x, _ in all_px]
        frame_ys = [y - base_cy + grid.effective_h / 2 for _, y in all_px]
        slack_x = max(0.0, (grid.effective_w - 2 * margin_px) - (max(frame_xs) - min(frame_xs)))
        slack_y = max(0.0, (grid.effective_h - 2 * margin_px) - (max(frame_ys) - min(frame_ys)))
        pitch = grid.tile_px + grid.gap_px
        shift_x = _best_axis_shift(frame_xs, pitch, grid.tile_px, slack_x)
        shift_y = _best_axis_shift(frame_ys, pitch, grid.tile_px, slack_y)

        center_lat, center_lon = _latlon_from_pixel(base_cx - shift_x, base_cy - shift_y, zoom)

    try:
        canvas = _fetch_map(center_lat, center_lon, zoom, grid.effective_w, grid.effective_h)
    except Exception as exc:
        logger.warning("Standort-Karte konnte nicht geladen werden: %s", exc)
        canvas = Image.new("RGB", (grid.effective_w, grid.effective_h), (25, 25, 30))

    canvas = canvas.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    center_px = _pixel_coords(center_lat, center_lon, zoom)

    def _pixel_to_cell(px: float, py: float) -> tuple[int, int]:
        col = min(grid.cols - 1, max(0, int(px // (grid.tile_px + grid.gap_px))))
        row = min(grid.rows - 1, max(0, int(py // (grid.tile_px + grid.gap_px))))
        return col, row

    # Pin wird an der ECHTEN geografischen Position gezeichnet (kein Snap auf
    # die Kachel-Mitte - waere geografisch falsch, Nutzerfeedback 2026-09-06).
    # Dass sie trotzdem nahe der Kachel-Mitte landet, ist Aufgabe der
    # Zoom/Zentrum-Wahl oben (_best_axis_shift), nicht dieser Zeichenfunktion.
    hx, hy = _project(HOME_LAT, HOME_LON, zoom, center_px, grid.effective_w, grid.effective_h)
    _draw_pin(draw, hx, hy, _HOME_COLOR)

    cell_points: dict[tuple[int, int], TrackedPoint] = {}
    for p in points:
        px, py = _project(p.lat, p.lon, zoom, center_px, grid.effective_w, grid.effective_h)
        _draw_pin(draw, px, py, _PIN_COLOR)
        cell_points[_pixel_to_cell(px, py)] = p

    return LocationFrame(image=canvas, grid=grid, points=cell_points, zoom=zoom, center=center_px)


def slice_tiles(frame: LocationFrame) -> dict[int, Image.Image]:
    return frame.grid.slice_tiles(frame.image)


def tracked_point_at(frame: LocationFrame, key_index: int) -> TrackedPoint | None:
    col, row = frame.grid.key_index_to_cell(key_index)
    return frame.points.get((col, row))


def tile_image(frame: LocationFrame, key_index: int) -> Image.Image:
    return slice_tiles(frame)[key_index]


def render_placeholder(grid: Grid = DECKONE_GRID) -> dict[int, Image.Image]:
    """Kein Tracker gefunden (kein `person`/`device_tracker` mit Koordinaten
    in Home Assistant, oder HA gar nicht konfiguriert) - eigene, klar
    beschriftete Karte statt einer leeren/kaputten Kartenansicht."""
    canvas = Image.new("RGB", (grid.effective_w, grid.effective_h), (20, 20, 26))
    draw = ImageDraw.Draw(canvas)
    font = _load_font(15)
    text = "Keine Tracker\ngefunden"
    draw.multiline_text((grid.effective_w / 2, grid.effective_h / 2), text, fill=(140, 140, 150),
                         font=font, anchor="mm", align="center", spacing=6)
    return grid.slice_tiles(canvas)


def render_info_card(point: TrackedPoint, base_tile: Image.Image) -> Image.Image:
    """Kleine Info-Karte bei Tastendruck auf eine Pin-Kachel - Name +
    Entfernung/Richtung von Zuhause, analog zu radar.py::render_info_card."""
    size = base_tile.size
    img = base_tile.copy().convert("RGB")
    overlay = Image.new("RGBA", size, (0, 0, 0, 150))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_font(13)
    dist_km = _haversine_km(HOME_LAT, HOME_LON, point.lat, point.lon)
    bearing = _bearing_deg(HOME_LAT, HOME_LON, point.lat, point.lon)
    lines = [point.name, f"{dist_km:.1f} km von zuhause", f"Richtung {bearing:.0f}°"]
    y = size[1] / 2 - (len(lines) * 14) / 2
    for line in lines:
        draw.text((size[0] / 2, y), line, fill=(235, 235, 240), font=font, anchor="ma")
        y += 16
    return img
