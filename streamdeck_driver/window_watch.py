"""Automatischer DECK-ONE-Profilwechsel je nach aktuell fokussierter
Anwendung (Fenster-Fokus-Ueberwachung via platform_backend.get_active_app_id()).
Rein optional - siehe config/profiles.yaml / profiles.example.yaml, Schluessel
'auto_profile_switch'. Wechselt NUR bei einem tatsaechlichen Fokus-WECHSEL auf
eine neue, zugeordnete App (Flanken-, kein Dauer-Trigger) - ein manuell am
Elgato Mini gewaehltes Profil wird NICHT sofort wieder zurueckgeschaltet,
solange dieselbe App fokussiert bleibt (erst der naechste Fokuswechsel loest
wieder eine Auswertung aus)."""
from __future__ import annotations

import logging
import threading

from . import platform_backend

logger = logging.getLogger("streamdeck_driver.window_watch")

DEFAULT_POLL_INTERVAL_S = 3.0


class WindowWatcher:
    def __init__(self, apps: dict[str, str], switch_profile_fn, poll_interval_s: float = DEFAULT_POLL_INTERVAL_S):
        """apps: {app-id-teilstring (klein, z.B. 'obs' oder 'firefox'): Profilname}.
        Teilstring-Vergleich analog zu platform_backend.linux.set_app_volume()
        - robust gegen z.B. wm_class 'firefox_firefox' statt 'firefox'."""
        self._apps = {pattern.lower(): profile for pattern, profile in apps.items()}
        self._switch_profile_fn = switch_profile_fn
        self._poll_interval_s = poll_interval_s
        self._last_app_id: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _match_profile(self, app_id: str) -> str | None:
        return next((profile for pattern, profile in self._apps.items() if pattern in app_id), None)

    def _run(self) -> None:
        while not self._stop.wait(self._poll_interval_s):
            app_id = platform_backend.get_active_app_id()
            if app_id is None or app_id == self._last_app_id:
                continue
            self._last_app_id = app_id
            profile = self._match_profile(app_id)
            if profile is None:
                continue
            logger.info("Automatischer Profilwechsel: aktive App '%s' -> Profil '%s'", app_id, profile)
            try:
                self._switch_profile_fn(profile)
            except Exception:
                logger.exception("Automatischer Profilwechsel zu '%s' fehlgeschlagen", profile)

    def start(self) -> None:
        if not self._apps or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="window-watch", daemon=True)
        self._thread.start()
        logger.info("Automatischer Profilwechsel aktiv fuer: %s", ", ".join(self._apps))

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None


def build_from_config(config: dict, switch_profile_fn) -> WindowWatcher | None:
    """None wenn das Feature in der Config fehlt/deaktiviert ist oder keine
    Apps zugeordnet sind - der Daemon startet dann einfach ohne Watcher."""
    cfg = config.get("auto_profile_switch", {}) or {}
    apps = cfg.get("apps", {}) or {}
    if not cfg.get("enabled", False) or not apps:
        return None
    return WindowWatcher(apps, switch_profile_fn, poll_interval_s=float(cfg.get("poll_interval_s", DEFAULT_POLL_INTERVAL_S)))
