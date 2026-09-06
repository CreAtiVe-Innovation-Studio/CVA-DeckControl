"""DECK-ONE-Controller: verwaltet die 5 Profile (streaming/nachhilfe/studium/
kreativ/audio) mit ihren jeweiligen Seiten, rendert die aktuelle Seite,
verarbeitet Tastendruecke. Profilwechsel wird von aussen (typischerweise vom
ElgatoController, siehe unified_daemon.py) ausgeloest - DECK ONE selbst hat
in unserer Config keine eigenen switch_profile-Tasten."""
from __future__ import annotations

import logging
import threading
import time

from . import actions, ha_client, hw_monitor, live_view, location_map, process_monitor, radar, timer_engine
from .devices.deckone import DeckOne
from .icon_render import (
    blank_icon, render_key_icon, render_stat_card, render_timer_card,
    render_toggle_card, render_weather_forecast_card, zoom_icon,
)

FLASH_DURATION_S = 0.13
# Ab dieser Haltedauer (Sekunden zwischen Druecken und Loslassen) gilt ein
# Tastendruck als "lang" - loest dann `action_long` statt `action` aus, falls
# die Taste ein action_long definiert hat (siehe handle_key()). 0.6s ist ein
# ueblicher Standardwert fuer lang/kurz-Unterscheidung bei Tasten/Touch.
LONG_PRESS_THRESHOLD_S = 0.6

logger = logging.getLogger("streamdeck_driver.deckone_controller")

# Metrik -> (Einheit, Formatierung) fuer render_stat_card(). "ram_gb" ist ein
# Sonderfall (zwei Zahlen "genutzt/gesamt" statt einer Prozentzahl).
STAT_UNITS = {
    "cpu": "%", "cpu_temp": "°C", "ram": "%", "gpu_load": "%",
    "gpu_vram": "%", "gpu_temp": "°C", "disk": "%",
}

SYSTEM_REFRESH_INTERVAL_S = 3.0


class DeckOneController:
    def __init__(self, config: dict):
        self.config = config.get("deckone", {})
        self.device = DeckOne()
        self.active_profile = self.config.get("active_profile", "nachhilfe")
        self.current_page_index = 0
        self._refresh_stop = threading.Event()
        self._refresh_thread: threading.Thread | None = None
        self._radar_frame: radar.RadarFrame | None = None
        self._radar_zoom_idx = 0
        self._radar_info: tuple[int, dict, float] | None = None  # (key_index, aircraft, expires_at)
        self._forecast_frame: radar.RadarFrame | None = None
        self._forecast_idx = 0
        self._location_frame: location_map.LocationFrame | None = None
        self._location_info: tuple[int, location_map.TrackedPoint, float] | None = None
        self._press_started: dict[int, float] = {}  # key_index -> time.monotonic() bei Tastendruck
        # Schuetzt jede Sequenz aus set_key_image()-Aufrufen + end_batch() als
        # EINE atomare Einheit - ohne das koennen der 3s-Hintergrund-Refresh
        # (start_stat_refresh) und ein zeitgleicher Tastendruck/Profilwechsel
        # (vom Elgato-Mini-Event-Thread) ihre Bild-Uploads auf demselben
        # USB-Geraet verschachteln, was zu sichtbar korrupten/gemischten
        # Kacheln fuehrt (live gemeldet: "halb grau halb Bild", alte Kachel
        # bleibt nach Profilwechsel stehen). RLock, da verschachtelte Aufrufe
        # im selben Thread vorkommen (z.B. render_current_page -> _render_
        # radar_page -> _apply_radar_info_overlay).
        self._render_lock = threading.RLock()

    @property
    def connected(self) -> bool:
        return self.device.connected

    def connect(self) -> bool:
        return self.device.connect()

    def disconnect(self) -> None:
        self.device.disconnect()

    def _set_key_image(self, key_index: int, img):
        """Wie device.set_key_image(), haelt aber zusaetzlich einen Schnapp-
        schuss fuer die Live-Ansicht im Browser (live_view.py) aktuell -
        billig (nur PNG-Encode + Dict-Update), egal ob die Live-Ansicht
        gerade an oder aus ist."""
        live_view.deckone_snapshot.update(key_index, img)
        return self.device.set_key_image(key_index, img)

    def start_event_loop(self) -> None:
        self.device.start_event_loop(self.handle_key)

    # -- Seiten/Profile -----------------------------------------------------

    def _profile_pages(self, profile_name: str) -> list[dict]:
        return self.config.get("profiles", {}).get(profile_name, {}).get("pages", [])

    def _current_page_keys(self) -> dict:
        pages = self._profile_pages(self.active_profile)
        if not pages or not (0 <= self.current_page_index < len(pages)):
            return {}
        return pages[self.current_page_index].get("keys", {})

    def render_current_page(self) -> None:
        with self._render_lock:
            if self.active_profile == "radar":
                self._render_radar_page()
                return
            if self.active_profile == "wo_ist":
                self._render_location_page()
                return
            if self.active_profile == "wetter_vorhersage":
                self._render_forecast_page()
                return
            keys = self._current_page_keys()
            size = self.device.info.image_size
            stats = hw_monitor.snapshot() if self.active_profile in ("system", "ki") else None
            for idx in range(self.device.info.num_keys):
                key = keys.get(idx)
                img = blank_icon(size) if key is None else self._render_key_icon_for(key, stats, size, idx)
                ok = self._set_key_image(idx, img)
                if not ok:
                    logger.warning("DECK ONE Taste %s: Bild setzen fehlgeschlagen", idx)
            self.device.end_batch()
            logger.info("DECK ONE: Profil '%s' Seite %s gerendert", self.active_profile, self.current_page_index)

    def _render_radar_page(self) -> None:
        """Sonderfall: die Radar-Seite wird NICHT Taste-fuer-Taste aus der
        YAML gerendert, sondern als EIN grosses Kartenbild (siehe radar.py),
        das in 15 Kacheln zerschnitten wird."""
        try:
            frame = radar.build_frame(radar.ZOOM_CYCLE[self._radar_zoom_idx])
        except Exception:
            logger.exception("Radar-Rendering fehlgeschlagen")
            return
        self._radar_frame = frame
        for idx, tile in radar.slice_tiles(frame).items():
            ok = self._set_key_image(idx, tile)
            if not ok:
                logger.warning("DECK ONE Taste %s (Radar): Bild setzen fehlgeschlagen", idx)
        self._apply_radar_info_overlay()
        self.device.end_batch()
        logger.info("DECK ONE: Radar-Seite gerendert (warning=%s)", frame.warning)

    def _render_forecast_page(self) -> None:
        """Sonderfall wie _render_radar_page(): reine Niederschlags-
        VORHERSAGE (siehe radar.py::build_forecast_frame), separat von der
        Live-Radar-Seite - kein Flugzeug/Blitz/Avatar-Schnickschnack, nur
        die eine Frage 'wohin zieht der Regen'."""
        try:
            frame = radar.build_forecast_frame(self._forecast_idx)
        except Exception:
            logger.exception("Vorhersage-Rendering fehlgeschlagen")
            return
        self._forecast_frame = frame
        for idx, tile in radar.slice_tiles(frame).items():
            ok = self._set_key_image(idx, tile)
            if not ok:
                logger.warning("DECK ONE Taste %s (Vorhersage): Bild setzen fehlgeschlagen", idx)
        self.device.end_batch()
        logger.info("DECK ONE: Vorhersage-Seite gerendert (Index %s)", self._forecast_idx)

    def _render_location_page(self) -> None:
        """Sonderfall wie _render_radar_page(): 'Wo ist?'-Seite wird als EIN
        grosses Kartenbild komponiert (siehe location_map.py), nicht aus der
        YAML gerendert. Ohne konfigurierte HA-Tracker-Entities zeigt sie
        einen Platzhalter statt leer/kaputt zu bleiben."""
        try:
            points = location_map._fetch_tracked_points()
            if not points:
                self._location_frame = None
                tiles = location_map.render_placeholder()
            else:
                frame = location_map.build_frame()
                self._location_frame = frame
                tiles = location_map.slice_tiles(frame)
        except Exception:
            logger.exception("Standort-Karte-Rendering fehlgeschlagen")
            return
        for idx, tile in tiles.items():
            ok = self._set_key_image(idx, tile)
            if not ok:
                logger.warning("DECK ONE Taste %s (Wo-ist): Bild setzen fehlgeschlagen", idx)
        self._apply_location_info_overlay()
        self.device.end_batch()
        logger.info("DECK ONE: Wo-ist-Seite gerendert (%s Tracker)", len(points))

    def _apply_location_info_overlay(self) -> None:
        if self._location_info is None:
            return
        key_index, point, expires_at = self._location_info
        if time.monotonic() >= expires_at:
            self._location_info = None
            return
        base_tile = location_map.tile_image(self._location_frame, key_index) if self._location_frame else blank_icon(self.device.info.image_size)
        card = location_map.render_info_card(point, base_tile)
        self._set_key_image(key_index, card)

    def _apply_radar_info_overlay(self) -> None:
        """Zeigt bei angetippter Flugzeug-Kachel deren Detail-Karte an,
        solange sie noch nicht abgelaufen ist (siehe handle_key) - ersetzt
        NUR diese eine Kachel, der Rest der Radar-Seite bleibt normal."""
        if self._radar_info is None:
            return
        key_index, ac, expires_at = self._radar_info
        if time.monotonic() >= expires_at:
            self._radar_info = None
            return
        base_tile = radar.tile_image(self._radar_frame, key_index) if self._radar_frame else blank_icon(self.device.info.image_size)
        card = radar.render_info_card(ac, base_tile)
        self._set_key_image(key_index, card)

    def _render_key_icon_for(self, key: dict, stats: dict | None, size: tuple[int, int], key_index: int = -1):
        action_type = key.get("action", {}).get("type")
        if action_type == "live_stat":
            return self._render_stat_key(key, stats, size)
        if action_type == "ha_sensor":
            return self._render_ha_key(key, size)
        if action_type == "weather_forecast":
            return self._render_weather_forecast_key(key, size)
        if action_type == "timer":
            return self._render_timer_key(key, size, key_index)
        if action_type == "live_view_toggle":
            label = key.get("title") or key.get("name", "")
            # Datei-Existenz statt live_view.is_enabled(): die Datei kippt
            # synchron beim Tastendruck, is_enabled() erst wenn die Haupt-
            # Loop (daemon.py, alle 0.5s) den Server tatsaechlich (ge)startet
            # hat - sonst zeigt die Taste kurz noch den alten Zustand.
            return render_toggle_card(size, label, live_view.ENABLED_FLAG_PATH.exists())
        return render_key_icon(
            key.get("icon", {}),
            size,
            title=key.get("title") or key.get("name", ""),
            action_type=action_type or "",
        )

    def _timer_key_id(self, key_index: int) -> str:
        return f"{self.active_profile}:{self.current_page_index}:{key_index}"

    def _render_timer_key(self, key: dict, size: tuple[int, int], key_index: int):
        action = key.get("action", {})
        duration_min = float(action.get("duration_min", 25))
        sound_path = action.get("sound")
        style = action.get("style", "digital")
        label = key.get("title") or key.get("name", "")
        state = timer_engine.get_state(self._timer_key_id(key_index), duration_min, sound_path)
        phase, display_seconds, sublabel = timer_engine.describe(state)
        return render_timer_card(size, label, phase, display_seconds, sublabel, style, state.target_s)

    def _render_ha_key(self, key: dict, size: tuple[int, int]):
        """Live-Kachel fuer eine Home-Assistant-Entity (Sensor oder Wetter),
        analog zu _render_stat_key aber ueber ha_client statt hw_monitor.
        color_percent fest auf 30 (ruhiges Gruen) - die Ampel-Logik ist fuer
        Auslastungs-Prozente gedacht, nicht fuer Temperatur/Wetterwerte."""
        entity_id = key["action"].get("entity_id", "")
        label = key.get("title") or key.get("name", "")
        state_obj = ha_client.get_state(entity_id)
        if state_obj is None:
            return render_stat_card(size, label, value=None, unit="", value_text="--", color_percent=30)
        attrs = state_obj.get("attributes", {})
        if entity_id.startswith("weather."):
            temp = attrs.get("temperature")
            unit = attrs.get("temperature_unit", "°C")
            value_text = f"{temp:.0f}{unit}" if temp is not None else state_obj.get("state", "--")
        else:
            raw = state_obj.get("state", "--")
            unit = attrs.get("unit_of_measurement", "")
            try:
                value_text = f"{float(raw):.1f}{unit}"
            except (TypeError, ValueError):
                value_text = str(raw)
        return render_stat_card(size, label, value=None, unit="", value_text=value_text, color_percent=30)

    def _render_weather_forecast_key(self, key: dict, size: tuple[int, int]):
        """Vorhersage-Kachel (nicht der aktuelle Zustand wie _render_ha_key,
        sondern ein Tag/Stunde in der Zukunft) - ueber ha_client.get_forecast()
        (weather.get_forecasts-Service, siehe dort). offset=0 ist der naechste
        Eintrag der jeweiligen Granularitaet, NICHT zwingend 'heute' (bei
        forecast_type='daily' ist offset=0 je nach Integration manchmal schon
        der Rest des heutigen Tages, manchmal schon morgen - kommt auf die
        Wetter-Integration an)."""
        action = key.get("action", {})
        entity_id = action.get("entity_id", "")
        forecast_type = action.get("forecast_type", "daily")
        offset = int(action.get("offset", 0))
        label = key.get("title") or key.get("name", "")
        forecast = ha_client.get_forecast(entity_id, forecast_type)
        if not forecast or offset >= len(forecast):
            return render_weather_forecast_card(size, label, None, None, None)
        entry = forecast[offset]
        return render_weather_forecast_card(
            size, label, entry.get("condition"),
            entry.get("temperature"), entry.get("templow"),
        )

    def _flash_key_press(self, key_index: int, key: dict, action_type: str) -> None:
        """Kurzer Zoom-Puls auf der gedrueckten Taste als visuelles Feedback -
        bei Seiten-/Profilwechsel ausgelassen, da sich der Bildschirm dabei
        ohnehin sofort komplett neu aufbaut."""
        if action_type in ("page_next", "page_previous", "switch_profile", "live_stat", "timer", "live_view_toggle"):
            return  # live_stat/timer/live_view_toggle rendern sich beim Druck ohnehin sofort neu (Sofort-Refresh)
        size = self.device.info.image_size
        stats = hw_monitor.snapshot() if self.active_profile == "system" else None
        normal_img = self._render_key_icon_for(key, stats, size, key_index)
        self._set_key_image(key_index, zoom_icon(normal_img))
        self.device.end_batch()

        def _restore():
            time.sleep(FLASH_DURATION_S)
            # Laeuft in einem eigenen Thread, lange NACH dem urspruenglichen
            # handle_key()-Aufruf zurueckgekehrt ist - braucht deshalb sein
            # eigenes Lock statt sich auf den (laengst wieder freigegebenen)
            # Lock von handle_key() zu verlassen.
            with self._render_lock:
                self._set_key_image(key_index, normal_img)
                self.device.end_batch()

        threading.Thread(target=_restore, daemon=True).start()

    def _render_stat_key(self, key: dict, stats: dict | None, size: tuple[int, int]):
        metric = key["action"].get("metric", "")
        label = key.get("title") or key.get("name", "")
        if stats is None:
            stats = hw_monitor.snapshot()
        if metric == "ram_gb":
            used, total = stats.get("ram_used_gb"), stats.get("ram_total_gb")
            value_text = f"{used:.0f}/{total:.0f}GB" if used is not None and total is not None else None
            # Farbe UND Verlaufsgraph kommen von der RAM-Prozentzahl
            # (geglaettet/historisiert), nicht von den Absolutwerten in GB.
            color = hw_monitor.rolling_average("ram", stats.get("ram"))
            history = hw_monitor.get_recent_values("ram")
            return render_stat_card(
                size, label, value=None, unit="", value_text=value_text,
                color_percent=color, history=history,
            )
        value = stats.get(metric)
        unit = STAT_UNITS.get(metric, "")
        # KORRIGIERT 2026-08-21: Ampel-Farbe nutzt jetzt den gleitenden
        # 2-Minuten-Durchschnitt statt des Momentanwerts, damit sie nicht bei
        # jedem 3s-Refresh hin- und herspringt, wenn ein Wert knapp um eine
        # Schwelle schwankt. Die angezeigte ZAHL bleibt der aktuelle Wert.
        # Zusaetzlich: Verlaufsgraph der letzten 2 Minuten im Kartenhintergrund.
        color = hw_monitor.rolling_average(metric, value)
        history = hw_monitor.get_recent_values(metric)
        return render_stat_card(size, label, value, unit, color_percent=color, history=history)

    # -- Live-Refresh, solange das System-Profil aktiv ist ------------------

    def start_stat_refresh(self) -> None:
        if self._refresh_thread is not None:
            return
        self._refresh_stop.clear()

        def _run():
            while not self._refresh_stop.wait(SYSTEM_REFRESH_INTERVAL_S):
                if self.active_profile in ("system", "ki", "home", "radar", "timer", "wo_ist", "wetter_vorhersage") and self.device.connected:
                    try:
                        self.render_current_page()
                    except Exception:
                        logger.exception("Fehler beim Auffrischen der Live-Stats")

        self._refresh_thread = threading.Thread(target=_run, name="deckone-system-refresh", daemon=True)
        self._refresh_thread.start()

    def stop_stat_refresh(self) -> None:
        self._refresh_stop.set()
        if self._refresh_thread is not None:
            self._refresh_thread.join(timeout=2)
            self._refresh_thread = None

    def switch_profile(self, profile_name: str) -> None:
        if profile_name not in self.config.get("profiles", {}):
            logger.warning("DECK ONE: unbekanntes Profil '%s' - ignoriert", profile_name)
            return
        self.active_profile = profile_name
        self.current_page_index = 0
        logger.info("DECK ONE: Profil gewechselt zu '%s'", profile_name)
        self.render_current_page()

    def _switch_page(self, direction: int) -> None:
        pages = self._profile_pages(self.active_profile)
        if not pages:
            return
        self.current_page_index = (self.current_page_index + direction) % len(pages)
        self.render_current_page()

    # -- Tastendruck ----------------------------------------------------------

    def handle_key(self, key_index: int, pressed: bool) -> None:
        with self._render_lock:
            if self.active_profile in ("radar", "wetter_vorhersage", "wo_ist") and not pressed:
                return
            if self.active_profile == "radar":
                if key_index == radar.GRID_COLS * radar.GRID_ROWS - 1:  # unten rechts = manueller Zoom
                    self._radar_zoom_idx = (self._radar_zoom_idx + 1) % len(radar.ZOOM_CYCLE)
                    self.render_current_page()
                    return
                if self._radar_info is not None and self._radar_info[0] == key_index:
                    # Erneuter Druck auf dieselbe Kachel: Info wieder ausblenden.
                    self._radar_info = None
                    self.render_current_page()
                    return
                if self._radar_frame is not None:
                    ac = radar.aircraft_at(self._radar_frame, key_index)
                    if ac is not None:
                        self._radar_info = (key_index, ac, time.monotonic() + 20.0)
                        card = radar.render_info_card(ac, radar.tile_image(self._radar_frame, key_index))
                        self._set_key_image(key_index, card)
                        self.device.end_batch()
                return
            if self.active_profile == "wetter_vorhersage":
                if key_index == radar.GRID_COLS * radar.GRID_ROWS - 1:  # unten rechts = naechster Vorhersage-Frame
                    frames = radar._rainviewer_nowcast_frames()
                    if frames:
                        self._forecast_idx = (self._forecast_idx + 1) % len(frames)
                    self.render_current_page()
                return
            if self.active_profile == "wo_ist":
                if self._location_info is not None and self._location_info[0] == key_index:
                    self._location_info = None
                    self.render_current_page()
                    return
                if self._location_frame is not None:
                    point = location_map.tracked_point_at(self._location_frame, key_index)
                    if point is not None:
                        self._location_info = (key_index, point, time.monotonic() + 20.0)
                        card = location_map.render_info_card(point, location_map.tile_image(self._location_frame, key_index))
                        self._set_key_image(key_index, card)
                        self.device.end_batch()
                return
            key = self._current_page_keys().get(key_index)
            if key is None:
                self._press_started.pop(key_index, None)
                return

            if pressed:
                # Aktion wird erst beim Loslassen ausgeloest (siehe unten) -
                # nur so laesst sich ueberhaupt unterscheiden, ob es am Ende
                # ein kurzer oder langer Druck war. Der Zoom-Puls als
                # sofortiges taktiles Feedback bleibt trotzdem auf dem
                # Tastendruck selbst, nicht auf dem Loslassen.
                self._press_started[key_index] = time.monotonic()
                self._flash_key_press(key_index, key, key.get("action", {}).get("type"))
                return

            started = self._press_started.pop(key_index, None)
            held_s = (time.monotonic() - started) if started is not None else 0.0
            action_long = key.get("action_long")
            is_long_press = held_s >= LONG_PRESS_THRESHOLD_S and action_long
            action = action_long if is_long_press else key.get("action", {})
            action_type = action.get("type")
            logger.info(
                "DECK ONE Taste %s losgelassen (%.2fs gehalten, %s): %s (%s)",
                key_index, held_s, "lang" if is_long_press else "kurz",
                key.get("title") or key.get("name"), action_type,
            )
            if action_type == "page_next":
                self._switch_page(+1)
            elif action_type == "page_previous":
                self._switch_page(-1)
            elif action_type == "live_stat":
                self.render_current_page()  # manuelles Sofort-Auffrischen bei Druck
                metric = action.get("metric", "")
                if metric in ("cpu", "ram", "gpu_load"):
                    # Top-5-Prozesse-Popup nur fuer die drei Prozent-Kacheln (siehe
                    # process_monitor.py) - laeuft in einem eigenen Thread, da die
                    # CPU-Messung ~0.6s braucht und das sonst die Tastenverarbeitung
                    # dieses Geraets blockieren wuerde (gleiche Lehre wie beim
                    # Screenshot-Fix in actions.py).
                    process_monitor.show_top_processes_async(metric)
            elif action_type == "timer":
                duration_min = float(action.get("duration_min", 25))
                timer_engine.handle_press(self._timer_key_id(key_index), duration_min, action.get("sound"))
                self.render_current_page()  # manuelles Sofort-Auffrischen bei Druck, wie live_stat
            elif action_type == "live_view_toggle":
                live_view.toggle_enabled_flag()  # eigentliches Starten/Stoppen macht die Haupt-Loop (daemon.py)
                self.render_current_page()
            else:
                actions.dispatch(action, key.get("title") or key.get("name", ""))
