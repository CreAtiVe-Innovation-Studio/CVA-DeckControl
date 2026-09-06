"""Duenner Client fuer die Home-Assistant-REST-API. Zugangsdaten liegen in
config/ha_secrets.yaml (chmod 600, bewusst getrennt von profiles.yaml - siehe
ha_secrets.example.yaml fuer eine Vorlage). Kein HA-SDK noetig - die
REST-API reicht fuer Zustand lesen + generisches toggle."""
from __future__ import annotations

import logging
import time

import requests
import yaml

from .paths import app_root

logger = logging.getLogger("streamdeck_driver.ha_client")

SECRETS_PATH = app_root() / "config" / "ha_secrets.yaml"
CACHE_TTL_S = 2.0
FORECAST_CACHE_TTL_S = 900.0  # 15min - Vorhersagen aendern sich nicht sekuendlich

_secrets: dict | None = None
_cache: dict[str, dict] = {}
_cache_time = 0.0
_forecast_cache: dict[tuple[str, str], dict] = {}


def _load_secrets() -> dict:
    global _secrets
    if _secrets is None:
        with open(SECRETS_PATH, encoding="utf-8") as f:
            _secrets = yaml.safe_load(f)
    return _secrets


def _headers() -> dict:
    return {"Authorization": f"Bearer {_load_secrets()['token']}", "Content-Type": "application/json"}


def _refresh_cache() -> None:
    global _cache, _cache_time
    now = time.monotonic()
    if _cache and now - _cache_time < CACHE_TTL_S:
        return
    url = f"{_load_secrets()['url']}/api/states"
    try:
        resp = requests.get(url, headers=_headers(), timeout=5)
        resp.raise_for_status()
        _cache = {e["entity_id"]: e for e in resp.json()}
        _cache_time = now
    except requests.RequestException as exc:
        logger.warning("HA: Zustaende konnten nicht geladen werden: %s", exc)


def get_state(entity_id: str) -> dict | None:
    """Liefert das rohe HA-State-Objekt (state, attributes, ...) fuer eine
    Entity, aus einem kurzlebigen Cache (2s) damit eine ganze Seite mit
    mehreren HA-Kacheln nicht pro Taste einen eigenen API-Call macht."""
    _refresh_cache()
    return _cache.get(entity_id)


def list_domain(domain: str) -> list[dict]:
    """Alle States einer Domain (z.B. 'geo_location' fuer Blitzortung-
    Einzelblitze) aus demselben kurzlebigen Cache."""
    _refresh_cache()
    prefix = f"{domain}."
    return [e for eid, e in _cache.items() if eid.startswith(prefix)]


def call_service(domain: str, service: str, entity_id: str) -> bool:
    """Ruft einen beliebigen HA-Service auf (z.B. cover.open_cover)."""
    url = f"{_load_secrets()['url']}/api/services/{domain}/{service}"
    try:
        resp = requests.post(url, headers=_headers(), json={"entity_id": entity_id}, timeout=5)
        resp.raise_for_status()
        logger.info("HA: %s.%s auf %s aufgerufen", domain, service, entity_id)
        global _cache_time
        _cache_time = 0.0  # naechster Read soll frischen Zustand holen
        return True
    except requests.RequestException as exc:
        logger.error("HA: %s.%s fuer %s fehlgeschlagen: %s", domain, service, entity_id, exc)
        return False


def get_forecast(entity_id: str, forecast_type: str = "daily") -> list[dict] | None:
    """Wettervorhersage ueber den weather.get_forecasts-Service (seit HA
    2023.9 der Weg dafuer - das alte 'forecast'-Attribut direkt auf der
    Entity ist deprecated/mittlerweile entfernt, taucht also NICHT in
    get_state()/list_domain() auf). forecast_type: 'daily', 'hourly' oder
    'twice_daily' - welche davon unterstuetzt werden, haengt von der
    jeweiligen Wetter-Integration ab, nicht jede bietet alle drei.
    15min gecacht (viel laenger als der normale State-Cache, Vorhersagen
    aendern sich nicht sekuendlich)."""
    cache_key = (entity_id, forecast_type)
    now = time.monotonic()
    cached = _forecast_cache.get(cache_key)
    if cached and now - cached["fetched_at"] < FORECAST_CACHE_TTL_S:
        return cached["data"]
    url = f"{_load_secrets()['url']}/api/services/weather/get_forecasts?return_response"
    try:
        resp = requests.post(
            url, headers=_headers(), json={"entity_id": entity_id, "type": forecast_type}, timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        forecast = data.get("service_response", {}).get(entity_id, {}).get("forecast")
        _forecast_cache[cache_key] = {"data": forecast, "fetched_at": now}
        return forecast
    except requests.RequestException as exc:
        logger.warning("HA: Wettervorhersage fuer %s (%s) fehlgeschlagen: %s", entity_id, forecast_type, exc)
        return None


def toggle(entity_id: str) -> bool:
    """Ruft den generischen homeassistant.toggle-Service auf - funktioniert
    domain-uebergreifend fuer light/switch/etc., ohne dass man pro Domain
    den richtigen Service-Namen kennen muss."""
    return call_service("homeassistant", "toggle", entity_id)


def cover_move(entity_id: str, direction: str) -> bool:
    """Hoch/Runter-Taste mit 'Gegenrichtung stoppt'-Verhalten: wenn der
    Rolladen gerade in die JEWEILS ANDERE Richtung faehrt, stoppt ein
    Druck auf diese Taste ihn nur, statt sofort umzukehren - direction
    ist 'up' oder 'down'."""
    state_obj = get_state(entity_id)
    current = state_obj.get("state") if state_obj else None
    opposite_moving = "closing" if direction == "up" else "opening"
    if current == opposite_moving:
        return call_service("cover", "stop_cover", entity_id)
    service = "open_cover" if direction == "up" else "close_cover"
    return call_service("cover", service, entity_id)
