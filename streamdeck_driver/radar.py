"""Radar-Seite: rendert EIN grosses Kartenbild (500x300px, passend zum 5x3-
Tastenraster der DECK ONE) statt wie sonst jede Taste unabhaengig, und
zerschneidet es in 15 Kacheln. Drei Datenquellen:
  - Flugzeuge: adsb.lol (kostenlos, kein Key)
  - Karte: OpenStreetMap-Kacheln (kostenlos, kein Key)
  - Gewitter: Blitzortung ueber Home Assistant (ha_client)

Zoom-Logik:
  - Default: 40km-Uebersicht um zuhause (HOME_LAT/HOME_LON, siehe
    _load_home_location() - kommt aus config/location.yaml, nicht hier im Code)
  - Naehert sich ein Gewitter (sensor.home_lightning_distance): zoomt in
    Stufen 30/20/10/5km rein, ab 5km "MASSIVE WARNUNG"-roter Overlay
  - Flugzeug im Landeanflug auf Koeln/Bonn oder Duesseldorf (tief + sinkend +
    Kurs Richtung Flughafen): zoomt eng auf das Flugzeug (8km), zeigt die
    Landung
"""
from __future__ import annotations

import io
import logging
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests
import yaml
from PIL import Image, ImageDraw, ImageOps

from . import ha_client
from .grid import DECKONE_GRID
from .icon_render import _load_font
from .paths import app_root, project_root

logger = logging.getLogger("streamdeck_driver.radar")


def _load_home_location() -> tuple[float, float, str]:
    """Lokaler Standort (+ die Wetter-Entity fuer Wind/Klarer-Himmel-Check,
    siehe _wind_info()/_weather_condition()) kommt aus config/location.yaml
    (siehe location.example.yaml als Vorlage) statt hart im Code zu stehen -
    sonst wuerde die echte Adresse (bzw. der eigene HA-Entity-Name) in einem
    oeffentlichen Repo landen. weather_entity_id faellt auf den generischen
    HA-Standardnamen 'weather.home' zurueck, falls nicht gesetzt. Faellt bei
    fehlender Datei auf 0,0 zurueck (nur eine Warnung, kein Absturz), damit
    der Rest des Treibers (Hotkeys etc.) auch ohne Radar-Setup startet."""
    path = app_root() / "config" / "location.yaml"
    if not path.exists():
        logger.warning(
            "%s fehlt - Radar-Seite nutzt Platzhalter-Koordinaten (0,0). Vorlage kopieren: "
            "cp config/location.example.yaml config/location.yaml", path,
        )
        return 0.0, 0.0, "weather.home"
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return (
        float(data.get("home_lat", 0.0)),
        float(data.get("home_lon", 0.0)),
        data.get("weather_entity_id", "weather.home"),
    )


HOME_LAT, HOME_LON, WEATHER_ENTITY_ID = _load_home_location()
CGN = (50.8659, 7.1427)  # Koeln/Bonn - oeffentliche Flughafenkoordinate, keine private Adresse
DUS = (51.2895, 6.7668)  # Duesseldorf

# Grid-Geometrie jetzt aus dem geteilten grid.py-Modul bezogen (siehe dort) -
# gleiche Zahlen wie vorher, nur nicht mehr lose Modul-Konstanten, damit
# andere Features (z.B. eine Standort-Karte) dieselbe Logik fuer andere
# Geraete-Grids wiederverwenden koennen. GAP_PX-Herleitung (nachgemessen:
# Taste 1,3cm, Luecke 0,9cm) steckt jetzt in Grid.__post_init__.
GRID = DECKONE_GRID
GRID_COLS, GRID_ROWS = GRID.cols, GRID.rows
TILE_PX = GRID.tile_px
GAP_PX = GRID.gap_px
CANVAS_W, CANVAS_H = GRID.canvas_w, GRID.canvas_h  # 500x300 - SICHTBARE Flaeche
EFFECTIVE_W, EFFECTIVE_H = GRID.effective_w, GRID.effective_h  # inkl. der "verdeckten" Luecken-Pixel
TILE_SIZE = 256  # OSM-Kachelgroesse

DEFAULT_RADIUS_KM = 5.0  # Ausgangssicht/Ruhezustand
FORECAST_RADIUS_KM = 20.0  # Nutzerwunsch 2026-09-08: weiter rausgezoomt als
# der 5km-Radar-Ruhezustand, damit man auf der Vorhersage-Seite sieht, aus
# welcher Richtung Regen zieht - nicht nur ob es direkt zuhause regnet.
APPROACH_MIN_RADIUS_KM = 5.0
APPROACH_MAX_RADIUS_KM = 40.0
STORM_BANDS_KM = [(5, 5), (10, 10), (20, 20), (30, 30)]  # (Schwelle, Ziel-Radius)

_tile_cache: dict[tuple[int, int, int], Image.Image] = {}


# -- Geo-Hilfsfunktionen -----------------------------------------------------

def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bearing_deg(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlambda)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _angle_diff(a, b) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


# -- OSM-Kartenkacheln --------------------------------------------------------

def _pixel_coords(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Globale Pixelkoordinaten (Web-Mercator) bei gegebenem Zoom."""
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n * TILE_SIZE
    y = (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n * TILE_SIZE
    return x, y


def _choose_zoom(radius_km: float, lat: float) -> int:
    """Hoechster Zoom (am staerksten reingezoomt), bei dem der gewuenschte
    Durchmesser (2*radius_km) noch komplett in die sichtbare Breite passt.
    KORRIGIERT: der Vergleich war invertiert und lieferte praktisch immer
    den maximalen Zoom (16) zurueck, egal welcher Radius verlangt war -
    dadurch waren z.B. 30km entfernte Flugzeuge nie im sichtbaren Bereich."""
    target_span_m = 2 * radius_km * 1000
    for z in range(16, 4, -1):
        meters_per_px = 156543.03392 * math.cos(math.radians(lat)) / (2 ** z)
        if meters_per_px * CANVAS_W >= target_span_m:
            return z
    return 5


def _dark_mode(img: Image.Image) -> Image.Image:
    """Schwarz-mit-grauen-Akzenten-Look aus einer normalen (hellen) OSM-
    Kachel: Graustufen + Invertierung (heller Hintergrund -> satt schwarz,
    dunkle Linien/Beschriftung -> hellgrau), keine Farbe. Statt eines
    dritten Kachel-Dienstes (CARTO zeigt ab einer gewissen Anfragemenge ein
    'API KEY REQUIRED'-Wasserzeichen statt der Kachel), damit die Karte nie
    von einem fremden Kontingent abhaengt."""
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
    headers = {"User-Agent": "streamdeck-driver-radar/1.0 (privater Eigenbedarf)"}
    resp = requests.get(url, headers=headers, timeout=6)
    resp.raise_for_status()
    img = _dark_mode(Image.open(io.BytesIO(resp.content)).convert("RGB"))
    if len(_tile_cache) > 300:
        _tile_cache.clear()  # simpler Schutz gegen unbegrenztes Wachstum
    _tile_cache[key] = img
    return img


_rainviewer_cache: dict = {"data": None, "fetched_at": 0.0}
RAINVIEWER_TTL_S = 300.0  # neue Radar-Frames alle ~10min, 5min Cache reicht
MAX_PRECIP_ZOOM = 7  # jenseits davon (live geprueft) nur "Zoom Level Not Supported"-Kacheln
PRECIP_OPACITY = 0.5  # RainViewer-Kacheln sind bei starkem Regen fast deckend


def _rainviewer_data() -> dict | None:
    """Rohe weather-maps.json-Antwort, 5min gecacht - enthaelt sowohl die
    'past'-Frames (fuer den JETZT-Zustand, siehe _rainviewer_frame_path) als
    auch 'nowcast' (Vorhersage, siehe _rainviewer_nowcast_frames), beide aus
    demselben API-Aufruf statt zwei separaten."""
    now = time.monotonic()
    if _rainviewer_cache["data"] and now - _rainviewer_cache["fetched_at"] < RAINVIEWER_TTL_S:
        return _rainviewer_cache["data"]
    try:
        resp = requests.get("https://api.rainviewer.com/public/weather-maps.json", timeout=6)
        resp.raise_for_status()
        data = resp.json()
        _rainviewer_cache["data"] = data
        _rainviewer_cache["fetched_at"] = now
        return data
    except Exception as exc:
        logger.warning("RainViewer Frame-Info fehlgeschlagen: %s", exc)
        return None


def _rainviewer_frame_path() -> str | None:
    """Wolken/Niederschlag ueber RainViewer (kostenlos, kein Key) - liefert
    den Pfad zum aktuellsten (JETZT-)Radar-Frame."""
    data = _rainviewer_data()
    if not data:
        return None
    frames = data.get("radar", {}).get("past", [])
    if not frames:
        return None
    return data["host"] + frames[-1]["path"]


def _rainviewer_nowcast_frames() -> list[dict]:
    """Liste der RainViewer-VORHERSAGE-Frames (naechste ~30-60min, alle
    10min), aeltester zuerst - fuer die reine Vorhersage-Kartenseite (siehe
    build_forecast_frame()). Kann leer sein, RainViewer garantiert Nowcast
    nicht immer/ueberall - Aufrufer muss das vertragen (siehe dortiger
    Platzhalter-Text)."""
    data = _rainviewer_data()
    if not data:
        return []
    host = data.get("host", "")
    return [{"time": f["time"], "path": host + f["path"]} for f in data.get("radar", {}).get("nowcast", [])]


# BUG GEFUNDEN 2026-09-06 (live gemeldet: Avatar zeigte "Regen" ohne
# sichtbare Regenwolke): 30 war zu niedrig - die RainViewer-Kachel wird mit
# Glaettung geholt (siehe _fetch_precip_tile, ".../2/1_1.png" - das "1_1"
# aktiviert einen weichen Alpha-Verlauf/Blur um echte Niederschlagsflaechen
# herum). Bei Zuhause direkt gemessen waehrend es NICHT geregnet hat: Alpha
# 41-62 in einer 11x11-Pixel-Umgebung, konsistent (kein Einzelpixel-Rauschen,
# sondern genau dieser Weichzeichner-Schleier). Echter, sichtbarer Regen
# rendert in diesem Farbschema deutlich kraeftiger. Schwelle entsprechend
# angehoben, um den Schleier auszuschliessen, ohne echten Regen zu verpassen.
RAIN_AVATAR_ZOOM = 7  # = MAX_PRECIP_ZOOM, gleiche Aufloesung wie die Kartenebene
RAIN_AVATAR_ALPHA_THRESHOLD = 110  # von 255


def _is_raining_at_home() -> bool:
    """Prueft ECHTE Niederschlags-Pixel bei HOME_LAT/HOME_LON aus derselben
    RainViewer-Kachel, die auch auf der Karte gezeichnet wird - bewusst NICHT
    ueber _weather_condition() (Home-Assistant-FORECAST-Entity): die kann
    z.B. fuer die restliche Vorhersage-Stunde bei 'rainy' haengen bleiben,
    obwohl der tatsaechliche Regen laengst weitergezogen ist (User-Report
    2026-09-03: Avatar zeigte 'Regen' obwohl auf der Karte keine Wolke mehr
    zu sehen war - zwei verschiedene, nicht synchronisierte Datenquellen).
    Diese Funktion fragt stattdessen exakt das ab, was auch sichtbar
    gezeichnet wird, damit Charakter und Karte nie auseinanderlaufen."""
    frame_path = _rainviewer_frame_path()
    if not frame_path:
        return False
    px, py = _pixel_coords(HOME_LAT, HOME_LON, RAIN_AVATAR_ZOOM)
    tile_x, tile_y = int(px // TILE_SIZE), int(py // TILE_SIZE)
    try:
        tile = _fetch_precip_tile(frame_path, RAIN_AVATAR_ZOOM, tile_x, tile_y)
    except Exception as exc:
        logger.debug("Regen-Check bei Zuhause fehlgeschlagen: %s", exc)
        return False
    local_x, local_y = int(px % TILE_SIZE), int(py % TILE_SIZE)
    alpha = tile.getpixel((local_x, local_y))[3]
    return alpha >= RAIN_AVATAR_ALPHA_THRESHOLD


def _fetch_precip_tile(frame_path: str, z: int, x: int, y: int) -> Image.Image:
    # Farbschema 2 = "Universal Blue", 1_1 = leichte Glaettung + Schnee an
    url = f"{frame_path}/256/{z}/{x}/{y}/2/1_1.png"
    resp = requests.get(url, timeout=6)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content)).convert("RGBA")


def _fetch_precip_overlay(center_lat: float, center_lon: float, zoom: int, frame_path: str | None = None) -> Image.Image | None:
    """Regen/Wolken-Ebene auf EFFECTIVE_W x EFFECTIVE_H. RainViewer hat keine
    echten Kacheln jenseits von MAX_PRECIP_ZOOM (zeigt sonst nur ein 'Zoom
    Level Not Supported'-Schild) - bei staerkerem Reinzoomen wird die Ebene
    stattdessen beim naechst-groeberen unterstuetzten Zoom geholt und
    hochskaliert (dann halt etwas unscharf, aber sichtbar statt komplett
    zu fehlen oder das Wasserzeichen zu zeigen).
    frame_path: expliziter RainViewer-Frame statt dem aktuellsten (JETZT-)
    Frame - fuer die Vorhersage-Kartenseite (siehe build_forecast_frame()),
    die einen 'nowcast'-Frame statt 'past' nutzen will."""
    precip_path = frame_path if frame_path is not None else _rainviewer_frame_path()
    if not precip_path:
        return None
    p_zoom = min(round(zoom), MAX_PRECIP_ZOOM)  # RainViewer-Kacheln sind nur ganzzahlig zoombar
    scale = 2 ** (p_zoom - zoom)  # <=1 wenn staerker reingezoomt als unterstuetzt
    pw, ph = max(1, round(EFFECTIVE_W * scale)), max(1, round(EFFECTIVE_H * scale))
    cx, cy = _pixel_coords(center_lat, center_lon, p_zoom)
    left, top = cx - pw / 2, cy - ph / 2

    tile_x0, tile_y0 = int(left // TILE_SIZE), int(top // TILE_SIZE)
    tile_x1, tile_y1 = int((left + pw) // TILE_SIZE), int((top + ph) // TILE_SIZE)
    n = 2 ** p_zoom

    canvas = Image.new("RGBA", ((tile_x1 - tile_x0 + 1) * TILE_SIZE, (tile_y1 - tile_y0 + 1) * TILE_SIZE), (0, 0, 0, 0))
    got_any = False
    for tx in range(tile_x0, tile_x1 + 1):
        for ty in range(tile_y0, tile_y1 + 1):
            if ty < 0 or ty >= n:
                continue
            try:
                tile_img = _fetch_precip_tile(precip_path, p_zoom, tx % n, ty)
                got_any = True
            except Exception as exc:
                logger.debug("Niederschlags-Kachel %s/%s/%s fehlgeschlagen: %s", p_zoom, tx % n, ty, exc)
                continue
            canvas.paste(tile_img, ((tx - tile_x0) * TILE_SIZE, (ty - tile_y0) * TILE_SIZE), tile_img)

    if not got_any:
        return None
    crop_left, crop_top = int(left - tile_x0 * TILE_SIZE), int(top - tile_y0 * TILE_SIZE)
    cropped = canvas.crop((crop_left, crop_top, crop_left + pw, crop_top + ph))
    if scale < 1:
        cropped = cropped.resize((EFFECTIVE_W, EFFECTIVE_H), Image.BILINEAR)
    # RainViewer-Kacheln kommen bei starkem Niederschlag fast deckend - die
    # Karte darunter (Strassen/Ortsnamen) sonst kaum noch zu erkennen. Alpha
    # global auf die Haelfte skalieren, statt die Original-Deckkraft zu uebernehmen.
    r, g, b, a = cropped.split()
    a = a.point(lambda v: v * PRECIP_OPACITY)
    cropped = Image.merge("RGBA", (r, g, b, a))
    return cropped


def _fetch_map_for_radius(center_lat: float, center_lon: float, radius_km: float):
    """Normalfall: Zoom wird aus dem gewuenschten Sichtradius abgeleitet."""
    zoom = _choose_zoom(radius_km, center_lat)
    return _fetch_map(center_lat, center_lon, zoom)


def _fetch_map(center_lat: float, center_lon: float, zoom: float):
    """Holt/rendert die Karte auf EFFECTIVE_W x EFFECTIVE_H (sichtbare
    500x300 PLUS die dazwischenliegenden, spaeter beim Zerschneiden
    uebersprungenen Luecken-Pixel) bei einem bereits feststehenden Zoom-Level
    (siehe _fetch_map_for_radius fuer den ueblichen Radius->Zoom-Weg, bzw.
    _overview_view fuer den Fall, dass ein EXAKTER - oft gebrochener - Zoom
    gebraucht wird, damit zwei Punkte pixelgenau auf Kachelmitten landen).
    OSM liefert nur ganzzahlige Zoomstufen: bei gebrochenem `zoom` wird bei
    der naechsten Ganzzahl geholt und die Differenz per Resize ausgeglichen,
    damit die zurueckgegebenen Pixelkoordinaten trotzdem exakt zum
    gewuenschten (gebrochenen) Zoom passen."""
    zoom_int = round(zoom)
    scale = 2 ** (zoom - zoom_int)  # >1 = staerker rein als zoom_int, <1 = weiter raus
    fetch_w = max(1, round(EFFECTIVE_W / scale))
    fetch_h = max(1, round(EFFECTIVE_H / scale))

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
    if (fetch_w, fetch_h) != (EFFECTIVE_W, EFFECTIVE_H):
        cropped = cropped.resize((EFFECTIVE_W, EFFECTIVE_H), Image.LANCZOS)

    precip = _fetch_precip_overlay(center_lat, center_lon, zoom)
    if precip is not None:
        cropped = cropped.convert("RGBA")
        cropped.alpha_composite(precip)
        cropped = cropped.convert("RGB")
    # (cx, cy) wurde bei zoom_int bestimmt (fuer die Kachel-Auswahl) - nach
    # aussen muss der Mittelpunkt bei der GEBROCHENEN Zoomstufe zurueck, da
    # _project() spaeter mit genau diesem `zoom` rechnet.
    return cropped, zoom, _pixel_coords(center_lat, center_lon, zoom)


def _project(lat: float, lon: float, zoom: int, center_px: tuple[float, float]) -> tuple[float, float]:
    """Pixelposition im EFFECTIVE_W x EFFECTIVE_H-Bild (inkl. Luecken-Raum)."""
    x, y = _pixel_coords(lat, lon, zoom)
    cx, cy = center_px
    return EFFECTIVE_W / 2 + (x - cx), EFFECTIVE_H / 2 + (y - cy)


def _cell_origin(col: int, row: int) -> tuple[int, int]:
    """Obere linke Ecke der sichtbaren TILE_PXxTILE_PX-Flaeche fuer (col,row)
    im EFFECTIVE-Bild - jede Zelle wird durch GAP_PX vom Nachbarn getrennt.
    Duenner Wrapper um Grid.cell_origin() (siehe grid.py)."""
    return GRID.cell_origin(col, row)


# -- Flugzeuge (adsb.lol) -----------------------------------------------------

_last_aircraft: list[dict] = []


def _fetch_aircraft(radius_km: float) -> list[dict]:
    """Bei einem fehlgeschlagenen/gedrosselten Request (adsb.lol limitiert
    bei zu haeufigen Anfragen mit 429) wird die letzte bekannte Liste
    zurueckgegeben statt einer leeren - sonst 'verschwinden' kurz alle
    Flugzeuge bei jedem Ausfall, statt einfach kurz stehenzubleiben."""
    global _last_aircraft
    radius_nm = radius_km / 1.852
    url = f"https://api.adsb.lol/v2/point/{HOME_LAT}/{HOME_LON}/{int(radius_nm) + 5}"
    try:
        resp = requests.get(url, timeout=6)
        resp.raise_for_status()
        _last_aircraft = resp.json().get("ac", [])
    except requests.RequestException as exc:
        logger.warning("adsb.lol Abfrage fehlgeschlagen, zeige letzten bekannten Stand: %s", exc)
    return _last_aircraft


OVERHEAD_RADIUS_KM = 18.0  # nur Anfluege werten, die tatsaechlich nahe zuhause vorbeikommen
APPROACH_MAX_ALT_FT = 16500  # ~5km, beobachteter Wert fuer Anflugverkehr ueber dem Haus


def _find_approach(aircraft: list[dict]):
    """Sucht ein Flugzeug im Landeanflug auf CGN/DUS, das dabei ueber/nahe
    zuhause vorbeikommt: tief, im Sinkflug, Kurs zeigt aufs Flughafengelaende
    UND die aktuelle Position liegt nahe an Zuhause (sonst wuerde JEDER
    Anflug irgendwo im 60km-Suchradius die Zoom-Ansicht auf Koeln/Duesseldorf
    umschalten, auch wenn er bei uns gar nicht sichtbar/relevant ist)."""
    for ac in aircraft:
        lat, lon, track = ac.get("lat"), ac.get("lon"), ac.get("track")
        alt, vs = ac.get("alt_baro"), ac.get("baro_rate")
        if None in (lat, lon, track) or not isinstance(alt, (int, float)):
            continue
        if _aircraft_shape(ac.get("category")) != "airliner":
            continue  # Kleinflugzeuge/Helis zaehlen nicht als Anflugverkehr
        # Erfahrungswert: Anflugverkehr auf CGN/DUS ueberquert das Haus unter
        # ca. 5km (~16400ft) Hoehe - urspruenglich 4000ft war deutlich zu
        # niedrig angesetzt und hat den eigentlichen Anflugverkehr verpasst.
        if alt > APPROACH_MAX_ALT_FT or (vs is not None and vs > -100):
            continue
        if _haversine_km(lat, lon, HOME_LAT, HOME_LON) > OVERHEAD_RADIUS_KM:
            continue
        for name, (alat, alon) in (("CGN", CGN), ("DUS", DUS)):
            if _haversine_km(lat, lon, alat, alon) > 25:
                continue
            if _angle_diff(track, _bearing_deg(lat, lon, alat, alon)) < 35:
                return ac, name
    return None, None


def _altitude_color(alt) -> tuple[int, int, int]:
    if not isinstance(alt, (int, float)):
        return (170, 170, 170)
    if alt < 3000:
        return (255, 60, 60)
    if alt < 10000:
        return (255, 150, 40)
    if alt < 25000:
        return (255, 230, 60)
    return (80, 180, 255)


# ADS-B-Emitter-Kategorie (Feld "category"), siehe DO-260B Tabelle 2-16:
# A1/A2 = leicht/klein (Kleinflugzeug), A3-A5 = gross/schwer (Passagier-/
# Frachtmaschine), A7 = Rotorcraft (Hubschrauber).
def _aircraft_shape(category: str | None) -> str:
    if not category:
        return "small"
    if category.startswith("A7"):
        return "heli"
    if category in ("A3", "A4", "A5"):
        return "airliner"
    return "small"


def _rotate_pt(pt: tuple[float, float], angle_rad: float) -> tuple[float, float]:
    x, y = pt
    return (
        x * math.cos(angle_rad) - y * math.sin(angle_rad),
        x * math.sin(angle_rad) + y * math.cos(angle_rad),
    )


# Gefuellte Flugzeug-Silhouette (wie bei ADS-B Exchange/Flightradar24-artigen
# Trackern) im lokalen Koordinatensystem (Nase = -y, "geradeaus" =
# Flugrichtung 0deg), wird in _draw_aircraft um den Kurs gedreht+skaliert.
_JET_POLY = [
    (0, -20), (1.5, -13), (2.2, -7), (15, 3), (15, 6), (2.8, 2.5), (2.8, 9),
    (10, 15.5), (10, 17.5), (1.3, 13.5), (1.3, 19), (0, 20.5), (-1.3, 19),
    (-1.3, 13.5), (-10, 17.5), (-10, 15.5), (-2.8, 9), (-2.8, 2.5),
    (-15, 6), (-15, 3), (-2.2, -7), (-1.5, -13),
]
# Kleinflugzeug: GERADE (nicht gepfeilte) Tragflaechen - realistisch fuer
# General-Aviation-Maschinen, ein gepfeilter Fluegel wie beim Jet ist dort
# extrem unwahrscheinlich.
_PROP_POLY = [
    (0, -16), (1.2, -10), (1.6, -2), (14, -2), (14, 0.5), (2, 1), (2, 8),
    (7, 13), (0.8, 11), (0.8, 16), (0, 17), (-0.8, 16), (-0.8, 11),
    (-7, 13), (-2, 8), (-2, 1), (-14, 0.5), (-14, -2), (-1.6, -2), (-1.2, -10),
]
_SHAPE_POLY = {"airliner": _JET_POLY, "small": _PROP_POLY}
_SHAPE_SCALE = {"airliner": 1.15, "small": 0.9}


def _draw_aircraft(draw: ImageDraw.ImageDraw, px: float, py: float, track, color, shape: str) -> None:
    """Gefuellte Flugzeug-Silhouette (Passagier-/Frachtmaschine groesser,
    Kleinflugzeug kleiner) bzw. Rotorscheibe fuer Hubschrauber, gedreht in
    die aktuelle Flugrichtung."""
    if shape == "heli":
        # Rumpf + Rotorscheibe von oben - bewusst NICHT nach Kurs gedreht
        # (Helis schweben/drehen viel, ein gedrehter Rotorstrich waere hier
        # nicht erkennbarer als ein fester).
        r = 5
        draw.ellipse([px - r, py - r, px + r, py + r], fill=color, outline=(0, 0, 0))
        draw.line([px - 15, py, px + 15, py], fill=color, width=2)
        draw.line([px, py + r, px, py + 11], fill=color, width=2)
        return
    heading = math.radians(track) if isinstance(track, (int, float)) else 0.0
    scale = _SHAPE_SCALE.get(shape, 0.9)
    poly = _SHAPE_POLY.get(shape, _PROP_POLY)
    pts = [(px + dx, py + dy) for dx, dy in (_rotate_pt((x * scale, y * scale), heading) for x, y in poly)]
    draw.polygon(pts, fill=color, outline=(0, 0, 0))


# -- Gewitter (Blitzortung via Home Assistant) --------------------------------

def _lightning_km() -> float | None:
    state = ha_client.get_state("sensor.home_lightning_distance")
    if state is None:
        return None
    raw = state.get("state")
    if raw in (None, "unknown", "unavailable"):
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    if state.get("attributes", {}).get("unit_of_measurement") == "mi":
        val *= 1.60934
    return val


LIGHTNING_MAX_AGE_MIN = 20.0  # aeltere Blitze werden nicht mehr angezeigt


def _lightning_strikes() -> list[dict]:
    """Einzelblitze (geo_location-Entities des Blitzortung-Integrations) mit
    lat/lon + Alter in Minuten - fuer die farbige Darstellung (gelb=frisch,
    rot=aelter, siehe _strike_color)."""
    strikes = []
    now = time.time()
    for e in ha_client.list_domain("geo_location"):
        attrs = e.get("attributes", {})
        if attrs.get("source") != "blitzortung" and "lightning" not in e.get("entity_id", ""):
            continue
        lat, lon = attrs.get("latitude"), attrs.get("longitude")
        pub_date = attrs.get("publication_date")
        if lat is None or lon is None:
            continue
        age_min = None
        if pub_date:
            try:
                import datetime
                ts = datetime.datetime.fromisoformat(pub_date.replace("Z", "+00:00")).timestamp()
                age_min = (now - ts) / 60.0
            except (ValueError, TypeError):
                age_min = None
        if age_min is not None and age_min > LIGHTNING_MAX_AGE_MIN:
            continue
        strikes.append({"lat": lat, "lon": lon, "age_min": age_min or 0.0})
    return strikes


def _strike_color(age_min: float) -> tuple[int, int, int]:
    """Gelb (frisch) verblasst Richtung Rot (bis LIGHTNING_MAX_AGE_MIN alt)."""
    t = max(0.0, min(1.0, age_min / LIGHTNING_MAX_AGE_MIN))
    return (255, int(230 * (1 - t)), 0)


# -- Zusammenfuehrung ----------------------------------------------------------

@dataclass
class RadarFrame:
    image: Image.Image
    hits: dict[tuple[int, int], dict] = field(default_factory=dict)
    warning: str | None = None


def _decide_view(aircraft: list[dict]):
    """Zentrum ist IMMER zuhause (Am Ueling) - die Karte darf nie wegwandern,
    nur der Radius (Zoom) passt sich an, damit es sich nicht wie ein
    staendiges Verschieben anfuehlt, sondern wie ein ruhiges Rein-/Rauszoomen."""
    approach_ac, airport = _find_approach(aircraft)
    if approach_ac is not None:
        dist_home = _haversine_km(HOME_LAT, HOME_LON, approach_ac["lat"], approach_ac["lon"])
        radius = min(APPROACH_MAX_RADIUS_KM, max(APPROACH_MIN_RADIUS_KM, dist_home * 1.2))
        return HOME_LAT, HOME_LON, radius, f"Landeanflug {airport}"
    dist = _lightning_km()
    if dist is not None:
        for threshold, radius in STORM_BANDS_KM:
            if dist <= threshold:
                warn = "GEWITTER SEHR NAH - MASSIVE WARNUNG" if threshold <= 5 else f"Gewitter naehert sich ({threshold}km)"
                return HOME_LAT, HOME_LON, radius, warn
    return HOME_LAT, HOME_LON, DEFAULT_RADIUS_KM, None


# Manueller Zoom-Override ueber die Taste unten rechts (siehe
# deckone_controller.py) - "auto" gibt die normale _decide_view-Logik frei,
# ein Zahlenwert erzwingt einen festen Radius (immer noch zentriert auf
# Zuhause) bis wieder auf "auto" weitergeschaltet wird.
ZOOM_CYCLE: list[str | float] = ["auto", 5.0, 10.0, 20.0, 40.0]


def _latlon_from_pixel(x: float, y: float, zoom: int) -> tuple[float, float]:
    """Umkehrung von _pixel_coords."""
    n = 2.0 ** zoom
    lon = x / (n * TILE_SIZE) * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / (n * TILE_SIZE)))))
    return lat, lon


def _cell_center_px(col: int, row: int) -> tuple[float, float]:
    x0, y0 = _cell_origin(col, row)
    return x0 + TILE_PX / 2, y0 + TILE_PX / 2


def _overview_view() -> tuple[float, float, float]:
    """Zentrum+Zoom fuer die groesste Uebersichts-Stufe: statt stur auf
    Zuhause zu zentrieren (faellt bei grossem Radius wegen des 5:3-Formats
    hinten runter), wird explizit ein Zoom+Zentrum gesucht, bei dem CGN UND
    DUS jeweils moeglichst genau auf einer Kachel-MITTE landen - sonst
    sitzen sie mal am Kachelrand, mal genau in der (nicht dargestellten)
    Luecke zwischen zwei Tasten. Zuhause darf dafuer vom exakten Bild-
    zentrum abweichen.

    Vorgehen: der Pixel-Vektor CGN->DUS skaliert bei Web-Mercator gleich-
    foermig mit 2**zoom (in x UND y gleichzeitig) - seine RICHTUNG ist also
    fest, nur seine LAENGE laesst sich per Zoom stauchen/strecken. Fuer
    jede moegliche Zielzelle (dcol,drow) im 5x3-Raster wird per kleinsten
    Quadraten der Skalar gesucht, der den echten Vektor moeglichst nah an
    (dcol,drow)*pitch heranskaliert; daraus ergibt sich ein (meist
    gebrochener) Ziel-Zoom. Die Zellen-Kombination mit dem kleinsten Rest-
    Fehler (dem Anteil, der sich NICHT wegskalieren laesst, weil die
    Richtung nicht exakt zur Zelle passt) gewinnt. Der gebrochene Zoom wird
    beim Kachel-Holen auf die naechste Ganzzahl gerundet, die Differenz
    gleicht _fetch_map() per Bild-Resize aus - so landen beide Flughaefen
    trotz der festen Tile-Zoomstufen sehr nah an der jeweiligen Kachelmitte."""
    pitch = TILE_PX + GAP_PX
    ref_zoom = 10
    cgn_ref = _pixel_coords(*CGN, ref_zoom)
    dus_ref = _pixel_coords(*DUS, ref_zoom)
    dx0, dy0 = dus_ref[0] - cgn_ref[0], dus_ref[1] - cgn_ref[1]
    denom = dx0 * dx0 + dy0 * dy0

    best = None  # (fehler, zoom, dcol, drow)
    for dcol in range(-(GRID_COLS - 1), GRID_COLS):
        for drow in range(-(GRID_ROWS - 1), GRID_ROWS):
            if dcol == 0 and drow == 0:
                continue
            tx, ty = dcol * pitch, drow * pitch
            s = (dx0 * tx + dy0 * ty) / denom  # kleinste-Quadrate-Skalar
            if s <= 0:
                continue  # falsche Richtung - wuerde CGN/DUS vertauschen
            zoom = ref_zoom + math.log2(s)
            if not (6.0 <= zoom <= 12.0):
                continue
            err = math.hypot(dx0 * s - tx, dy0 * s - ty)
            if best is None or err < best[0]:
                best = (err, zoom, dcol, drow)

    if best is None:
        # Fallback, falls aus irgendeinem Grund keine Zelle passt (sollte bei
        # der bekannten CGN/DUS-Distanz nicht vorkommen): grobe Mittellage.
        lat = (HOME_LAT + CGN[0] + DUS[0]) / 3
        lon = (HOME_LON + CGN[1] + DUS[1]) / 3
        return lat, lon, 8.0

    _, zoom, dcol, drow = best
    # CGN so plazieren, dass sowohl CGN- als auch DUS-Zielkachel (col+dcol,
    # row+drow) innerhalb des 5x3-Rasters bleiben - aus dem gueltigen
    # Bereich wird die Mitte gewaehlt, damit beide moeglichst zentral sitzen.
    col_lo, col_hi = max(0, -dcol), min(GRID_COLS - 1, GRID_COLS - 1 - dcol)
    row_lo, row_hi = max(0, -drow), min(GRID_ROWS - 1, GRID_ROWS - 1 - drow)
    cgn_col = (col_lo + col_hi) // 2
    cgn_row = (row_lo + row_hi) // 2

    cell_cx, cell_cy = _cell_center_px(cgn_col, cgn_row)
    cgn_px = _pixel_coords(*CGN, zoom)
    # EFFECTIVE_W/2 + (cgn_px.x - center_px.x) == cell_cx  =>  center_px.x = ...
    center_px_x = cgn_px[0] - (cell_cx - EFFECTIVE_W / 2)
    center_px_y = cgn_px[1] - (cell_cy - EFFECTIVE_H / 2)
    center_lat, center_lon = _latlon_from_pixel(center_px_x, center_px_y, zoom)
    return center_lat, center_lon, zoom


def build_frame(manual_zoom: str | float = "auto") -> RadarFrame:
    aircraft = _fetch_aircraft(60)
    max_manual_zoom = max(v for v in ZOOM_CYCLE if isinstance(v, (int, float)))
    is_overview = manual_zoom == max_manual_zoom
    radius_km: float | None
    if manual_zoom == "auto":
        center_lat, center_lon, radius_km, warning = _decide_view(aircraft)
        base, zoom, center_px = _fetch_map_for_radius(center_lat, center_lon, radius_km)
    elif is_overview:
        center_lat, center_lon, zoom = _overview_view()
        warning = None
        radius_km = None
        base, zoom, center_px = _fetch_map(center_lat, center_lon, zoom)
    else:
        center_lat, center_lon, radius_km, warning = HOME_LAT, HOME_LON, float(manual_zoom), None
        base, zoom, center_px = _fetch_map_for_radius(center_lat, center_lon, radius_km)
    img = base.convert("RGB")
    draw = ImageDraw.Draw(img)

    hits: dict[tuple[int, int], dict] = {}
    for ac in aircraft:
        lat, lon = ac.get("lat"), ac.get("lon")
        if lat is None or lon is None:
            continue
        px, py = _project(lat, lon, zoom, center_px)
        if not (-10 <= px <= EFFECTIVE_W + 10 and -10 <= py <= EFFECTIVE_H + 10):
            continue
        color = _altitude_color(ac.get("alt_baro"))
        shape = _aircraft_shape(ac.get("category"))
        _draw_aircraft(draw, px, py, ac.get("track"), color, shape)
        col = min(GRID_COLS - 1, max(0, int(px // (TILE_PX + GAP_PX))))
        row = min(GRID_ROWS - 1, max(0, int(py // (TILE_PX + GAP_PX))))
        hits[(col, row)] = ac

    for strike in _lightning_strikes():
        sx, sy = _project(strike["lat"], strike["lon"], zoom, center_px)
        if not (-10 <= sx <= EFFECTIVE_W + 10 and -10 <= sy <= EFFECTIVE_H + 10):
            continue
        color = _strike_color(strike["age_min"])
        r = 3.5
        draw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=color, outline=(0, 0, 0))

    hx, hy = _project(HOME_LAT, HOME_LON, zoom, center_px)
    draw.ellipse([hx - 4, hy - 4, hx + 4, hy + 4], outline=(0, 255, 120), width=2)

    # Farbiger Warn-Tint nur bei echter Gewittergefahr - ein Landeanflug ist
    # kein Alarm und soll die Karte nicht komplett einfaerben.
    if warning and "Gewitter" in warning or (warning and "MASSIVE" in warning):
        overlay_rgba = (255, 0, 0, 110) if "MASSIVE" in warning else (255, 140, 0, 70)
        overlay = Image.new("RGBA", img.size, overlay_rgba)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    badge_radius_km = radius_km if radius_km is not None else max_manual_zoom
    img = _draw_zoom_badge(img, badge_radius_km, manual_zoom != "auto")
    img = _draw_wind_badge(img)
    img = _draw_avatar(img, _pick_avatar_event(aircraft, warning))

    return RadarFrame(image=img, hits=hits, warning=warning)


# -- Reine Niederschlags-VORHERSAGE (separat vom Live-Radar oben) -----------

def _draw_forecast_badge(img: Image.Image, text: str) -> Image.Image:
    """Gleiche Optik/Position wie _draw_zoom_badge (unten rechts), aber fuer
    den Vorhersage-Zeitversatz ('+10 min' usw.) statt den Sichtradius -
    dieselbe Kachel ist hier auch die manuelle 'naechster Vorhersage-Frame'-
    Taste, siehe deckone_controller.py."""
    x0, y0 = _cell_origin(GRID_COLS - 1, GRID_ROWS - 1)
    rgba = img.convert("RGBA")
    draw = ImageDraw.Draw(rgba)
    font = _load_font(16)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = 4
    box = [x0 + TILE_PX - tw - 2 * pad, y0 + TILE_PX - th - 2 * pad, x0 + TILE_PX, y0 + TILE_PX]
    draw.rectangle(box, fill=(0, 0, 0, 70))
    _draw_outlined_text(draw, (box[0] + pad, box[1] + pad - bbox[1]), text, font)
    return rgba.convert("RGB")


def build_forecast_frame(nowcast_index: int = 0) -> RadarFrame:
    """Reine Niederschlags-VORHERSAGE (RainViewer-Nowcast) um zuhause, OHNE
    Flugzeuge/Blitze/Avatar - bewusst reduziert auf die eine Frage 'wohin
    zieht der Regen als naechstes' (Nutzerwunsch: 'Kartenversion die NUR
    Vorhersage macht', 2026-09-06). Eigene, schlanke Funktion statt build_
    frame() mit Flags zu ueberladen - die beiden haben inhaltlich wenig
    gemeinsam ausser derselben Karten-/Kachel-Infrastruktur.
    nowcast_index waehlt den Frame aus _rainviewer_nowcast_frames() (0 = der
    naechste, hoeher = weiter in der Zukunft) - kann leer sein, RainViewer
    garantiert Nowcast-Daten nicht immer/ueberall, dann bleibt es bei der
    Basiskarte + einem 'keine Vorhersage'-Hinweis statt zu crashen."""
    frames = _rainviewer_nowcast_frames()
    base, zoom, center_px = _fetch_map_for_radius(HOME_LAT, HOME_LON, FORECAST_RADIUS_KM)
    img = base.convert("RGB")

    if frames:
        idx = min(nowcast_index, len(frames) - 1)
        frame = frames[idx]
        try:
            precip = _fetch_precip_overlay(HOME_LAT, HOME_LON, zoom, frame_path=frame["path"])
        except Exception:
            logger.exception("Vorhersage-Niederschlag konnte nicht geladen werden")
            precip = None
        if precip is not None:
            img = img.convert("RGBA")
            img.alpha_composite(precip)
            img = img.convert("RGB")
        minutes_ahead = max(0, round((frame["time"] - time.time()) / 60))
        badge_text = f"+{minutes_ahead}min"
    else:
        badge_text = "keine Daten"

    draw = ImageDraw.Draw(img)
    hx, hy = _project(HOME_LAT, HOME_LON, zoom, center_px)
    draw.ellipse([hx - 4, hy - 4, hx + 4, hy + 4], outline=(0, 255, 120), width=2)
    img = _draw_forecast_badge(img, badge_text)

    return RadarFrame(image=img, hits={}, warning=None)


def _wind_info() -> tuple[float, float] | None:
    """(Richtung woher der Wind kommt in Grad, Geschwindigkeit in km/h) aus
    der Wetter-Entity - None falls (noch) nicht verfuegbar."""
    state = ha_client.get_state(WEATHER_ENTITY_ID)
    if state is None:
        return None
    attrs = state.get("attributes", {})
    bearing, speed = attrs.get("wind_bearing"), attrs.get("wind_speed")
    if not isinstance(bearing, (int, float)) or not isinstance(speed, (int, float)):
        return None
    return bearing, speed


def _draw_wind_badge(img: Image.Image) -> Image.Image:
    """Windrichtung/-geschwindigkeit oben in der mittleren Kachel - Pfeil
    zeigt in die Richtung, in die der Wind weht (wind_bearing ist meteoro-
    logisch die Richtung, AUS der er kommt, deshalb +180deg gedreht)."""
    info = _wind_info()
    if info is None:
        return img
    bearing, speed = info
    x0, y0 = _cell_origin(2, 0)  # obere mittlere Kachel (Spalte 2, Reihe 0)
    cx, cy = x0 + TILE_PX / 2, y0 + TILE_PX / 2 - 4

    rgba = img.convert("RGBA")
    draw = ImageDraw.Draw(rgba)

    heading = math.radians(bearing + 180)
    length = 16
    tip = (cx + length * math.sin(heading), cy - length * math.cos(heading))
    tail = (cx - length * 0.6 * math.sin(heading), cy + length * 0.6 * math.cos(heading))
    draw.line([tail, tip], fill=(120, 200, 255, 255), width=3)
    back1 = _rotate_pt((0, -6), heading + 2.5)
    back2 = _rotate_pt((0, -6), heading - 2.5)
    draw.polygon(
        [tip, (tip[0] + back1[0], tip[1] + back1[1]), (tip[0] + back2[0], tip[1] + back2[1])],
        fill=(120, 200, 255, 255),
    )

    text = f"{speed:.0f}km/h"
    font = _load_font(12)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    _draw_outlined_text(draw, (cx - tw / 2 - bbox[0], y0 + TILE_PX - 16), text, font)

    return rgba.convert("RGB")


def _draw_zoom_badge(img: Image.Image, radius_km: float, manual: bool) -> Image.Image:
    """Kleines Overlay unten rechts (die manuelle Zoom-Taste) mit der
    aktuellen Sichtweite - 'M' Praefix wenn manuell uebersteuert, sonst
    zeigt es einfach den aktuell aktiven (automatischen) Radius."""
    x0, y0 = _cell_origin(GRID_COLS - 1, GRID_ROWS - 1)
    text = f"{'M ' if manual else ''}{radius_km:.0f}km"
    rgba = img.convert("RGBA")
    draw = ImageDraw.Draw(rgba)
    font = _load_font(16)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = 4
    box = [x0 + TILE_PX - tw - 2 * pad, y0 + TILE_PX - th - 2 * pad, x0 + TILE_PX, y0 + TILE_PX]
    draw.rectangle(box, fill=(0, 0, 0, 70))
    _draw_outlined_text(draw, (box[0] + pad, box[1] + pad - bbox[1]), text, font)
    return rgba.convert("RGB")


# -- Reaktiver Mii/VTuber-Charakter (siehe tools/generate_avatar_poses.py) ---
# Die Posen liegen fertig freigestellt (RGBA, transparenter Hintergrund) unter
# assets/generated-avatars/<kategorie>/*.png - eine Ebene ueber linux-driver/,
# wie bei generate_avatar_poses.py::OUT_DIR.
AVATAR_DIR = project_root() / "assets" / "generated-avatars"
AVATAR_CELL = (0, GRID_ROWS - 1)  # untere linke Kachel - bislang ohne eigenes Overlay
AVATAR_WIND_THRESHOLD_KMH = 25.0
AVATAR_TRAFFIC_COUNT = 6  # ab so vielen Flugzeugen im Nahbereich gilt es als "viel Verkehr"
GOV_CALLSIGN_PREFIXES = ("GAF",)  # Luftwaffe/Flugbereitschaft des Bundes


def _weather_condition() -> str | None:
    state = ha_client.get_state(WEATHER_ENTITY_ID)
    return state.get("state") if state else None


AVATAR_LOCAL_RADIUS_KM = 8.0  # fuer heli_tief/viel_verkehr - "tatsaechlich in Kartennaehe
# sichtbar", bewusst enger als OVERHEAD_RADIUS_KM (18km, fuer die CGN/DUS-Anflug-
# erkennung gedacht) - sonst reagiert der Charakter auf einen Heli, der bei der
# Standard-5km-Ausgangssicht laengst ausserhalb des sichtbaren Kartenausschnitts liegt.


def _pick_avatar_event(aircraft: list[dict], warning: str | None) -> str:
    """Bestimmt, welche Charakter-Pose-Kategorie gerade passt (Kategorien
    siehe tools/generate_avatar_poses.py::POSES) - Prioritaet: je
    dramatischer/spezifischer das Ereignis, desto weiter oben in der
    Funktion, damit sich z.B. ein nahes Gewitter immer gegen "viel Verkehr"
    durchsetzt. Allgemeiner Regen (ohne Blitz-Risiko) rangiert bewusst UEBER
    heli_tief/viel_verkehr - ein andauernder Wetterzustand ist relevanter als
    ein einzelnes, ggf. laengst wieder verschwundenes Flugzeug."""
    if warning and "MASSIVE" in warning:
        return "gewitter_massive"
    if warning and "Gewitter" in warning:
        return "gewitter"

    nearby_wide = [
        ac for ac in aircraft
        if ac.get("lat") is not None and ac.get("lon") is not None
        and _haversine_km(ac["lat"], ac["lon"], HOME_LAT, HOME_LON) <= OVERHEAD_RADIUS_KM
    ]
    if any((ac.get("flight") or "").strip().startswith(GOV_CALLSIGN_PREFIXES) for ac in nearby_wide):
        return "regierungsflugzeug"
    if warning and warning.startswith("Landeanflug"):
        return "camera_lowfly"

    if _is_raining_at_home():
        return "regen"

    nearby_local = [
        ac for ac in nearby_wide
        if _haversine_km(ac["lat"], ac["lon"], HOME_LAT, HOME_LON) <= AVATAR_LOCAL_RADIUS_KM
    ]
    if any(_aircraft_shape(ac.get("category")) == "heli" for ac in nearby_local):
        return "heli_tief"
    if len(nearby_local) >= AVATAR_TRAFFIC_COUNT:
        return "viel_verkehr"

    if _weather_condition() in ("sunny", "clear-night"):
        return "klarer_himmel"
    wind = _wind_info()
    if wind is not None and wind[1] >= AVATAR_WIND_THRESHOLD_KMH:
        return "wind"
    return "idle"


_avatar_pose_cache: dict[str, list[Path]] = {}
_avatar_state: dict[str, str | Path | None] = {"category": None, "path": None}


_AVATAR_CATEGORY_ALIASES = {
    # "regen" (allgemeiner Regen ohne Blitz-Risiko) hat noch keine eigenen
    # generierten Posen - nutzt bis dahin dieselben Regenschirm-Bilder wie
    # "gewitter" (siehe _AVATAR_EVENT_LABELS fuer das unterschiedliche Label).
    "regen": "gewitter",
}


def _avatar_poses(category: str) -> list[Path]:
    folder_category = _AVATAR_CATEGORY_ALIASES.get(category, category)
    if folder_category not in _avatar_pose_cache:
        folder = AVATAR_DIR / folder_category
        _avatar_pose_cache[folder_category] = sorted(folder.glob("*.png")) if folder.is_dir() else []
    return _avatar_pose_cache[folder_category]


def _load_avatar_pose(category: str) -> Image.Image | None:
    """Wuerfelt bei JEDEM Refresh neu innerhalb der aktuellen Kategorie (ob
    "idle" oder ein aktives Ereignis wie "gewitter") - nie zweimal direkt
    hintereinander dieselbe Pose, damit der Charakter wie eine lebendige
    Kamera wirkt statt wie ein Standbild, auch waehrend ein Ereignis
    anhaelt."""
    poses = _avatar_poses(category)
    if not poses:
        _avatar_state["category"] = category
        _avatar_state["path"] = None
    else:
        prev = _avatar_state["path"] if _avatar_state["category"] == category else None
        choices = [p for p in poses if p != prev] or poses
        _avatar_state["category"] = category
        _avatar_state["path"] = random.choice(choices)
    path = _avatar_state["path"]
    if path is None:
        return None
    try:
        return Image.open(path).convert("RGBA")
    except OSError as exc:
        logger.warning("Avatar-Pose konnte nicht geladen werden: %s (%s)", path, exc)
        return None


# Kurzes, lesbares Label pro Kategorie - sonst ist auf der 100x100px-Kachel
# nicht erkennbar, WORAUF der Charakter gerade reagiert (eine Pose allein,
# z.B. "haelt Regenschirm", ist ohne Kontext mehrdeutig).
_AVATAR_EVENT_LABELS = {
    "idle": "Ruhig",
    "camera_lowfly": "Tiefflug!",
    "regen": "Regen",
    "gewitter": "Gewitter naht",
    "gewitter_massive": "Gewitter nah!",
    "regierungsflugzeug": "Regierungsjet",
    "wind": "Starker Wind",
    "heli_tief": "Heli tief",
    "klarer_himmel": "Klarer Himmel",
    "viel_verkehr": "Viel Verkehr",
}


def _draw_avatar(img: Image.Image, category: str) -> Image.Image:
    pose = _load_avatar_pose(category)
    if pose is None:
        return img
    x0, y0 = _cell_origin(*AVATAR_CELL)
    pose = pose.resize((TILE_PX, TILE_PX), Image.LANCZOS)
    rgba = img.convert("RGBA")
    rgba.alpha_composite(pose, (x0, y0))

    label = _AVATAR_EVENT_LABELS.get(category)
    if label:
        draw = ImageDraw.Draw(rgba)
        font = _load_font(11)
        bbox = draw.textbbox((0, 0), label, font=font)
        while bbox[2] - bbox[0] > TILE_PX - 8 and font.size > 7:
            font = _load_font(font.size - 1)
            bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = x0 + (TILE_PX - tw) // 2 - bbox[0]
        ty = y0 + TILE_PX - th - 6 - bbox[1]
        _draw_outlined_text(draw, (tx, ty), label, font)

    return rgba.convert("RGB")


def _draw_outlined_text(draw: ImageDraw.ImageDraw, pos: tuple[float, float], text: str, font) -> None:
    """Text mit duennem schwarzem Rand statt solidem Hintergrundkasten -
    bleibt auf der Karte lesbar, ohne die Kachel darunter zu verdecken."""
    x, y = pos
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 255))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))


def slice_tiles(frame: RadarFrame) -> dict[int, Image.Image]:
    """Zerschneidet in DECK-ONE-Reihenfolge (row-major, Index 0-14) - ueber-
    springt dabei die GAP_PX-Luecken zwischen den Zellen (siehe _cell_origin),
    damit Inhalte ueber die physischen Tastenraender hinweg weiterlaufen.
    Duenner Wrapper um Grid.slice_tiles() (siehe grid.py)."""
    return GRID.slice_tiles(frame.image)


def aircraft_at(frame: RadarFrame, key_index: int) -> dict | None:
    row, col = divmod(key_index, GRID_COLS)
    return frame.hits.get((col, row))


def tile_image(frame: RadarFrame, key_index: int) -> Image.Image:
    """Schneidet die aktuelle Kartenkachel an dieser Tastenposition aus dem
    Gesamtbild aus - Basis fuer ein transparentes Info-Overlay (siehe
    render_info_card), das die Karte darunter sichtbar laesst."""
    row, col = divmod(key_index, GRID_COLS)
    x0, y0 = _cell_origin(col, row)
    return frame.image.crop((x0, y0, x0 + TILE_PX, y0 + TILE_PX))


# Kleine Auswahl gaengiger ICAO-Typcodes -> Klartext (kein Anspruch auf
# Vollstaendigkeit, deckt aber den ueblichen Verkehr über uns ab). Unbekannte
# Codes werden einfach roh angezeigt (z.B. "A333"), auch das ist informativ.
_TYPE_NAMES = {
    "A319": "A319", "A320": "A320", "A321": "A321", "A20N": "A320neo", "A21N": "A321neo",
    "A332": "A330-200", "A333": "A330-300", "A338": "A330-800", "A339": "A330-900",
    "A342": "A340-200", "A343": "A340-300", "A345": "A340-500", "A346": "A340-600",
    "A359": "A350-900", "A35K": "A350-1000", "A388": "A380",
    "B738": "737-800", "B737": "737-700", "B739": "737-900", "B38M": "737 MAX 8", "B39M": "737 MAX 9",
    "B752": "757-200", "B763": "767-300", "B772": "777-200", "B77W": "777-300ER",
    "B788": "787-8", "B789": "787-9", "B78X": "787-10", "B744": "747-400",
    "E170": "E170", "E190": "E190", "E195": "E195", "E75L": "E175",
    "CRJ2": "CRJ200", "CRJ9": "CRJ900", "DH8D": "Dash 8 Q400",
    "C25M": "Citation CJ4", "C56X": "Citation Excel", "C68A": "Citation Latitude",
    "PC12": "Pilatus PC-12", "SR22": "Cirrus SR22",
}


def aircraft_type_name(ac: dict) -> str:
    code = (ac.get("t") or "").strip()
    return _TYPE_NAMES.get(code, code or "unbekannt")


_route_cache: dict[str, dict | None] = {}


def _lookup_route(callsign: str) -> dict | None:
    """Herkunft/Ziel + Airline ueber adsbdb.com (kostenlos, kein Key) -
    pro Callsign fuer die Laufzeit gecacht, da sich die Route eines Flugs
    nicht mehr aendert."""
    if callsign in _route_cache:
        return _route_cache[callsign]
    result = None
    try:
        resp = requests.get(f"https://api.adsbdb.com/v0/callsign/{callsign}", timeout=5)
        if resp.status_code == 200:
            route = resp.json().get("response", {}).get("flightroute")
            if route:
                result = route
    except requests.RequestException as exc:
        logger.debug("adsbdb-Abfrage fuer %s fehlgeschlagen: %s", callsign, exc)
    _route_cache[callsign] = result
    return result


def render_info_card(ac: dict, base_tile: Image.Image) -> Image.Image:
    """Detail-Text fuer eine angetippte Flugzeug-Kachel als TRANSPARENTES
    Overlay ueber der bestehenden Kartenkachel (nicht ersetzend): Typ, Flug,
    Route (falls ermittelbar), Hoehe (ft+km) und Geschwindigkeit (km/h)."""
    w, h = base_tile.size
    rgba = base_tile.convert("RGBA")
    draw = ImageDraw.Draw(rgba)
    # dezent abgedunkelt, damit weisser Text auf hellen Kartenstellen auch
    # lesbar bleibt, aber die Kachel darunter weiterhin erkennbar ist
    dim = Image.new("RGBA", (w, h), (0, 0, 0, 90))
    rgba.alpha_composite(dim)
    draw = ImageDraw.Draw(rgba)

    callsign = (ac.get("flight") or ac.get("hex") or "?").strip()
    alt = ac.get("alt_baro")
    gs = ac.get("gs")
    route = _lookup_route(callsign)

    lines = [aircraft_type_name(ac), callsign]
    if route:
        origin = route.get("origin", {}).get("iata_code") or route.get("origin", {}).get("icao_code") or "?"
        dest = route.get("destination", {}).get("iata_code") or route.get("destination", {}).get("icao_code") or "?"
        lines.append(f"{origin}→{dest}")
    if isinstance(alt, (int, float)):
        lines.append(f"{alt:.0f}ft/{alt * 0.0003048:.1f}km")
    if isinstance(gs, (int, float)):
        lines.append(f"{gs * 1.852:.0f}km/h")

    font = _load_font(11)
    y = 6
    for line in lines[:6]:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        _draw_outlined_text(draw, (max(2, (w - tw) / 2), y - bbox[1]), line, font)
        y += 15
    return rgba.convert("RGB")


def show_aircraft_info(ac: dict) -> None:
    """Zeigt Flugzeug-Details per zenity-Popup an (analog process_monitor.py)."""
    import subprocess

    flight = (ac.get("flight") or ac.get("hex") or "?").strip()
    alt = ac.get("alt_baro")
    gs = ac.get("gs")
    track = ac.get("track")
    vs = ac.get("baro_rate")
    lines = [
        f"Flug: {flight}",
        f"Höhe: {alt} ft" if alt is not None else "Höhe: unbekannt",
        f"Geschwindigkeit: {gs:.0f} kt" if isinstance(gs, (int, float)) else "Geschwindigkeit: unbekannt",
        f"Kurs: {track:.0f}°" if isinstance(track, (int, float)) else "Kurs: unbekannt",
        f"Steig-/Sinkrate: {vs} ft/min" if vs is not None else "",
    ]
    text = "\n".join(line for line in lines if line)
    try:
        subprocess.Popen(["zenity", "--info", "--title=Flugzeug", f"--text={text}", "--width=280"])
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.error("zenity-Anzeige (Flugzeug) fehlgeschlagen: %s", exc)
