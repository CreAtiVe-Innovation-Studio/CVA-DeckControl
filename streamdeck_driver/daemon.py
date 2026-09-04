"""Vereinter Daemon fuer beide Geraete: Elgato Stream Deck Mini (Modus-Auswahl,
6 Tasten) + Streamplify DECK ONE (eigentliche Aktions-Raster der 5 Profile,
15 Tasten). Ein Tastendruck auf "Nachhilfe" etc. auf dem Elgato Mini schaltet
DECK ONE wirklich auf das passende Profil um (siehe deckone_controller.py).

Beide Geraete werden unabhaengig verbunden - fehlt eins, laeuft der Daemon mit
dem anderen trotzdem weiter (grazil, kein Absturz).

Start: python3 -m streamdeck_driver.daemon
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
import time
from pathlib import Path

import yaml

from . import actions, live_view, timer_engine
from .deckone_controller import DeckOneController
from .devices.elgato_mini import ElgatoMini
from .icon_render import blank_icon, render_key_icon, zoom_icon
from .paths import app_root

logger = logging.getLogger("streamdeck_driver.daemon")

CONFIG_PATH = app_root() / "config" / "profiles.yaml"
FLASH_DURATION_S = 0.13


class ElgatoController:
    def __init__(self, config: dict, on_switch_profile=None):
        self.config = config
        self.device = ElgatoMini()
        self.current_page = "modi"
        self._on_switch_profile = on_switch_profile

    @property
    def connected(self) -> bool:
        return self.device.connected

    def connect(self) -> bool:
        return self.device.connect()

    def disconnect(self) -> None:
        self.device.disconnect()

    def _set_key_image(self, key_index: int, img):
        """Wie device.set_key_image(), haelt aber zusaetzlich einen Schnapp-
        schuss fuer die Live-Ansicht im Browser (live_view.py) aktuell."""
        live_view.elgato_snapshot.update(key_index, img)
        return self.device.set_key_image(key_index, img)

    def start_event_loop(self) -> None:
        self.device.start_event_loop(self.handle_key)

    def _page_keys(self, page_name: str) -> dict:
        return self.config.get("elgato", {}).get("pages", {}).get(page_name, {}).get("keys", {})

    def _render_key_icon(self, key: dict, size: tuple[int, int]):
        return render_key_icon(
            key.get("icon", {}),
            size,
            title=key.get("title") or key.get("name", ""),
            action_type=key.get("action", {}).get("type", ""),
        )

    def render_current_page(self) -> None:
        keys = self._page_keys(self.current_page)
        size = self.device.info.image_size
        for idx in range(self.device.info.num_keys):
            key = keys.get(idx)
            img = blank_icon(size) if key is None else self._render_key_icon(key, size)
            ok = self._set_key_image(idx, img)
            if not ok:
                logger.warning("Elgato Taste %s: Bild setzen fehlgeschlagen", idx)
        logger.info("Elgato: Seite '%s' gerendert", self.current_page)

    def _flash_key_press(self, key_index: int, key: dict, restore: bool) -> None:
        """Kurzer Zoom-Puls als Tastendruck-Feedback, analog zur DECK ONE.
        Bei page_next/page_previous rendert gleich danach ohnehin die ganze
        Elgato-Seite neu (restore=False); bei switch_profile aendert sich
        NUR die DECK-ONE-Seite, die Elgato-Anzeige bleibt sonst dauerhaft
        gezoomt haengen - deshalb dort per Timer zurueckgesetzt."""
        size = self.device.info.image_size
        normal_img = self._render_key_icon(key, size)
        self._set_key_image(key_index, zoom_icon(normal_img))
        if not restore:
            return

        def _restore():
            time.sleep(FLASH_DURATION_S)
            self._set_key_image(key_index, normal_img)

        threading.Thread(target=_restore, daemon=True).start()

    def _switch_page(self, direction: int) -> None:
        # Seitenreihenfolge kommt direkt aus der Config (Dict-Einfuegereihenfolge
        # = YAML-Reihenfolge), nicht aus einer festen Liste - neue Elgato-Seiten
        # brauchen dadurch KEINEN Code-Change mehr, nur einen Eintrag in
        # config/profiles.yaml unter elgato.pages.
        page_order = list(self.config.get("elgato", {}).get("pages", {}).keys())
        if not page_order:
            return
        idx = page_order.index(self.current_page) if self.current_page in page_order else 0
        idx = (idx + direction) % len(page_order)
        self.current_page = page_order[idx]
        self.render_current_page()

    def handle_key(self, key_index: int, pressed: bool) -> None:
        if not pressed:
            return
        key = self._page_keys(self.current_page).get(key_index)
        if key is None:
            return
        action = key.get("action", {})
        action_type = action.get("type")
        logger.info("Elgato Taste %s gedrueckt: %s (%s)", key_index, key.get("title") or key.get("name"), action_type)
        self._flash_key_press(key_index, key, restore=(action_type not in ("page_next", "page_previous")))
        if action_type == "page_next":
            self._switch_page(+1)
        elif action_type == "page_previous":
            self._switch_page(-1)
        elif action_type == "switch_profile":
            profile = action.get("profile")
            if self._on_switch_profile is not None:
                self._on_switch_profile(profile)
            else:
                logger.info("Profilwechsel '%s' angefordert, aber kein Handler registriert", profile)
        else:
            actions.dispatch(action, key.get("title") or key.get("name", ""))


class UnifiedDaemon:
    def __init__(self, config: dict):
        self.config = config
        self.deckone = DeckOneController(config)
        self.elgato = ElgatoController(config, on_switch_profile=self.deckone.switch_profile)
        self._running = False

    def run(self) -> None:
        elgato_ok = self.elgato.connect()
        if elgato_ok:
            self.elgato.device.set_brightness(90)
            self.elgato.render_current_page()
            self.elgato.start_event_loop()
        else:
            logger.warning("Elgato Stream Deck Mini nicht gefunden - laeuft ohne Modus-Auswahl weiter")

        timer_engine.start_ticker()

        deckone_ok = self.deckone.connect()
        if deckone_ok:
            self.deckone.device.set_brightness(90)
            self.deckone.render_current_page()
            self.deckone.start_event_loop()
            self.deckone.start_stat_refresh()
        else:
            logger.warning("DECK ONE nicht gefunden - laeuft ohne Aktions-Raster weiter")

        if not elgato_ok and not deckone_ok:
            logger.error("Kein Geraet gefunden - Daemon beendet sich")
            return

        self._running = True
        logger.info("Daemon laeuft. Strg+C zum Beenden.")
        try:
            while self._running:
                if elgato_ok and not self.elgato.connected:
                    logger.warning("Elgato-Verbindung verloren")
                    elgato_ok = False
                if deckone_ok and not self.deckone.connected:
                    logger.warning("DECK-ONE-Verbindung verloren")
                    deckone_ok = False
                if not elgato_ok and not deckone_ok:
                    logger.error("Beide Geraete getrennt - beende Daemon")
                    break
                live_view.sync_with_flag_file()
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.elgato.disconnect()
            self.deckone.stop_stat_refresh()
            self.deckone.disconnect()
            timer_engine.stop_ticker()
            live_view.stop()
            logger.info("Daemon beendet")


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8-sig") as f:
        return yaml.safe_load(f)


def main() -> None:
    # Immer in eine Datei loggen, nicht nur auf die Konsole - in der windowed
    # .exe (console=False im PyInstaller-Spec) gibt es unter Windows gar kein
    # sys.stderr mehr (None), ein reines StreamHandler-basicConfig wuerde beim
    # ersten Log-Aufruf abstuerzen. Konsole bleibt zusaetzlicher Handler, wo
    # vorhanden (normaler Python-Lauf, oder console=True in der .exe).
    log_dir = app_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(
            log_dir / "daemon.log", maxBytes=5_000_000, backupCount=2, encoding="utf-8"
        )
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)
    config = load_config()
    UnifiedDaemon(config).run()


if __name__ == "__main__":
    sys.exit(main())
