"""Layout-Engine: oeffnet fehlende Apps, positioniert Fenster in vorab definierte
Slots und bietet die 'intelligenten' Einzelaktionen (Fokus-oder-Start,
Blaettern, Maximieren/Zurueck). Siehe SEITEN-LOGIK.md Abschnitt 4.14 fuer das
Konfigurationsformat.

Alle OS-Zugriffe laufen ueber ein 'backend'-Objekt (standardmaessig
streamdeck_driver.platform_backend) - die Engine selbst ist reine Logik und in
tests/test_windowing_engine.py mit einem Fake-Backend durchgetestet."""
from __future__ import annotations

import logging
import re
import socket
import threading
import time
from dataclasses import dataclass, field

from .geometry import (
    Monitor, Rect, WindowInfo, monitors_from_dicts, slot_rect, windows_from_dicts,
)

logger = logging.getLogger("streamdeck_driver.windowing.engine")

DEFAULT_PAGE_KEYS = {"prev": 37, "next": 39}  # Windows-VK: Pfeil links / rechts
DEFAULT_START_TIMEOUT_S = 30.0
POLL_INTERVAL_S = 0.4
AUTO_PLACE_INTERVAL_S = 1.0
# Viele Apps (Fotos, Edge, Explorer) setzen ihre Groesse kurz NACH dem
# Erscheinen noch einmal selbst - deshalb wird nach dem Platzieren einmal
# nachgeprueft und bei Abweichung erneut verschoben.
RECHECK_DELAY_S = 1.2
FOCUS_SETTLE_S = 0.25  # Pause zwischen "Fenster nach vorn" und gesendeter Taste (layout_hotkey)


def _platform_key() -> str:
    import sys
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "other"


def pick_os(value, platform_key: str | None = None):
    """Wert, der je Betriebssystem verschieden sein darf: entweder direkt ein
    String, oder ein Dict {windows: ..., linux: ..., macos: ..., default: ...}."""
    if isinstance(value, dict):
        key = platform_key or _platform_key()
        return value.get(key, value.get("default"))
    return value


@dataclass
class AppSpec:
    name: str
    process: list[str]
    slot: dict | None = None
    title: re.Pattern | None = None
    title_exclude: re.Pattern | None = None
    order: int | None = None  # bei mehreren Treffern: Index von links nach rechts
    launch: str | None = None
    launch_uri: str | None = None
    launch_with: str | None = None  # wird mit der anderen App zusammen gestartet (z.B. 2. Firefox-Fenster)
    start: bool = False  # vom Start-Button geoeffnet
    auto_place: bool = False  # automatisch positioniert, wenn der Nutzer es selbst oeffnet
    page_keys: dict = field(default_factory=lambda: dict(DEFAULT_PAGE_KEYS))
    layout_name: str = ""


@dataclass
class ServiceSpec:
    name: str
    port: int
    command: str
    cwd: str | None = None
    host: str = "127.0.0.1"


@dataclass
class LayoutSpec:
    name: str
    apps: dict[str, AppSpec]
    services: list[ServiceSpec]
    start_timeout_s: float = DEFAULT_START_TIMEOUT_S


def _compile(pattern):
    return re.compile(pattern, re.IGNORECASE) if pattern else None


def parse_layout(name: str, raw: dict, platform_key: str | None = None) -> LayoutSpec:
    apps: dict[str, AppSpec] = {}
    for app_name, a in (raw.get("apps") or {}).items():
        match = a.get("match") or {}
        process = match.get("process", a.get("process", []))
        process = [process] if isinstance(process, str) else list(process)
        keys = dict(DEFAULT_PAGE_KEYS)
        keys.update(a.get("page_keys") or {})
        apps[app_name] = AppSpec(
            name=app_name, process=[p.lower() for p in process], slot=a.get("slot"),
            title=_compile(match.get("title")), title_exclude=_compile(match.get("title_exclude")),
            order=match.get("order"), launch=pick_os(a.get("launch"), platform_key),
            launch_uri=pick_os(a.get("launch_uri"), platform_key), launch_with=a.get("launch_with"),
            start=bool(a.get("start", False)), auto_place=bool(a.get("auto_place", False)),
            page_keys=keys, layout_name=name,
        )
    services = []
    for s in raw.get("services") or []:
        command = pick_os(s.get("command"), platform_key)
        if not command:
            logger.info("Dienst '%s' hat auf dieser Plattform keinen Startbefehl - uebersprungen", s.get("name"))
            continue
        services.append(ServiceSpec(
            name=s["name"], port=int(s["port"]), command=command, cwd=pick_os(s.get("cwd"), platform_key),
            host=s.get("host", "127.0.0.1"),
        ))
    return LayoutSpec(name, apps, services, float(raw.get("start_timeout_s", DEFAULT_START_TIMEOUT_S)))


def port_is_open(host: str, port: int, timeout_s: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


class LayoutEngine:
    def __init__(self, layouts: dict[str, LayoutSpec], backend=None, sleep=time.sleep, monotonic=time.monotonic):
        if backend is None:
            from .. import platform_backend as backend  # spaet importieren: Tests brauchen kein echtes Backend
        self.layouts = layouts
        self.backend = backend
        self._sleep = sleep
        self._now = monotonic
        self._start_lock = threading.Lock()
        # (Layout, App) -> Fenster-ID, gemerkt beim Platzieren. Im Unterricht wechseln
        # die Tabs und damit die Fenstertitel; die Zuordnung ueber Titel/Reihenfolge
        # taugt deshalb nur fuers ERSTE Finden, danach zaehlt die gemerkte ID.
        self._bound: dict[tuple[str, str], str] = {}
        self._saved_rect: dict[str, Rect] = {}  # Fenster-ID -> Position vor dem Maximieren
        self._slot_of: dict[str, str] = {}  # Fenster-ID -> App-Name, in dessen Slot es zuletzt platziert wurde
        self._active_layout: str | None = None
        self._placer: threading.Thread | None = None
        self._placer_stop = threading.Event()

    # -- Bestandsaufnahme ----------------------------------------------------

    def _windows(self) -> list[WindowInfo]:
        return windows_from_dicts(self.backend.list_windows())

    def _monitors(self) -> list[Monitor]:
        return monitors_from_dicts(self.backend.list_monitors())

    def _layout(self, name: str | None) -> LayoutSpec | None:
        if name is None and len(self.layouts) == 1:
            return next(iter(self.layouts.values()))
        layout = self.layouts.get(name or "")
        if layout is None:
            logger.warning("Unbekanntes Fenster-Layout '%s' (vorhanden: %s)", name, ", ".join(self.layouts) or "keine")
        return layout

    @staticmethod
    def _process_matches(app: AppSpec, window: WindowInfo) -> bool:
        return any(p in window.app_id for p in app.process)

    def matching_windows(self, app: AppSpec, windows: list[WindowInfo]) -> list[WindowInfo]:
        """Alle Fenster der App, von links nach rechts (dann oben nach unten)
        sortiert. Mehrere Fenster derselben App (z.B. zwei Firefox-Fenster)
        werden NICHT ueber den Titel unterschieden, wenn der keine Rolle spielt:
        der Titel enthaelt oft private Inhalte (Seitentitel, Dateinamen), und
        Firefox-Fenster tragen den Titel ihres gerade gewaehlten Tabs. Stattdessen
        reicht meist 'order' (Index von links nach rechts)."""
        found = [w for w in windows if self._process_matches(app, w)]
        if app.title is not None:
            found = [w for w in found if app.title.search(w.title)]
        if app.title_exclude is not None:
            found = [w for w in found if not app.title_exclude.search(w.title)]
        found.sort(key=lambda w: (w.rect.x, w.rect.y))
        if app.order is not None:
            return [found[app.order]] if app.order < len(found) else []
        return found

    @staticmethod
    def largest(found: list[WindowInfo]) -> WindowInfo | None:
        """Hauptfenster unter bereits zugeordneten Fenstern: das groesste
        sichtbare (Apps wie Zoom/Teams haben neben dem Hauptfenster kleine
        Hilfsfenster)."""
        if not found:
            return None
        visible = [w for w in found if not w.minimized] or found
        return max(visible, key=lambda w: w.rect.w * w.rect.h)

    def resolve(self, app: AppSpec, windows: list[WindowInfo], exclude: set[str] | frozenset = frozenset()) -> WindowInfo | None:
        """Das Fenster der App: zuerst das beim Platzieren gemerkte (solange es
        noch existiert), sonst per Prozess/Titel/Reihenfolge das groesste."""
        bound_id = self._bound.get((app.layout_name, app.name))
        if bound_id is not None and bound_id not in exclude:
            bound = next((w for w in windows if w.id == bound_id), None)
            if bound is not None:
                return bound
        return self.largest([w for w in self.matching_windows(app, windows) if w.id not in exclude])

    def best_window(self, app: AppSpec, windows: list[WindowInfo]) -> WindowInfo | None:
        return self.resolve(app, windows)

    def _has_any_window(self, app: AppSpec, windows: list[WindowInfo]) -> bool:
        """Laeuft der Prozess schon (egal mit welchem Fenster)? Dann NICHT noch
        einmal starten - ein zweiter Firefox-Start oeffnet z.B. nur ein
        zusaetzliches leeres Fenster."""
        return any(self._process_matches(app, w) for w in windows)

    # -- Platzieren ----------------------------------------------------------

    def place(self, app: AppSpec, window: WindowInfo, monitors: list[Monitor] | None = None) -> bool:
        if not app.slot:
            return False
        monitors = monitors or self._monitors()
        target = slot_rect(app.slot, monitors)
        if target is None:
            logger.warning("Keine Monitore erkannt - '%s' nicht platziert", app.name)
            return False
        self.backend.move_window(window.id, target.x, target.y, target.w, target.h)
        self._slot_of[window.id] = app.name
        self._bound[(app.layout_name, app.name)] = window.id
        logger.info("Fenster '%s' -> %s", app.name, target)
        return True

    def _recheck_later(self, layout: LayoutSpec, app: AppSpec, window_id: str) -> None:
        def _run():
            self._sleep(RECHECK_DELAY_S)
            monitors = self._monitors()
            target = slot_rect(app.slot, monitors) if app.slot else None
            current = next((w for w in self._windows() if w.id == window_id), None)
            if target is not None and current is not None and not current.maximized \
                    and not current.rect.close_to(target):
                self.backend.move_window(window_id, target.x, target.y, target.w, target.h)
                logger.info("Fenster '%s' nach Selbst-Resize erneut platziert", app.name)
        threading.Thread(target=_run, name="layout-recheck", daemon=True).start()

    # -- Dienste (llama-swap, ComfyUI, ...) ------------------------------------

    def ensure_services(self, layout: LayoutSpec) -> list[str]:
        started = []
        for svc in layout.services:
            if port_is_open(svc.host, svc.port):
                logger.info("Dienst '%s' laeuft bereits (Port %s) - nicht erneut gestartet", svc.name, svc.port)
                continue
            self.backend.start_minimized(svc.command, svc.cwd)
            logger.info("Dienst '%s' gestartet (minimiert), wartet auf Port %s", svc.name, svc.port)
            started.append(svc.name)
        return started

    # -- Start-Taste -------------------------------------------------------------

    def start(self, layout_name: str | None = None) -> None:
        """Laeuft in einem eigenen Thread (Tastendruck-Schleife nicht blockieren);
        ein zweiter Druck waehrend des Durchlaufs wird ignoriert."""
        layout = self._layout(layout_name)
        if layout is None:
            return
        if not self._start_lock.acquire(blocking=False):
            logger.info("Layout-Start laeuft bereits - zweiter Druck ignoriert")
            return

        def _run():
            try:
                self._run_start(layout)
            except Exception:
                logger.exception("Layout-Start fehlgeschlagen")
            finally:
                self._start_lock.release()

        threading.Thread(target=_run, name="layout-start", daemon=True).start()

    def _launch(self, app: AppSpec) -> bool:
        if app.launch:
            self.backend.open_command(app.launch)
            return True
        if app.launch_uri:
            self.backend.open_url(app.launch_uri)
            return True
        logger.warning("App '%s' ist nicht geoeffnet und hat keinen 'launch'-Eintrag", app.name)
        return False

    def _run_start(self, layout: LayoutSpec) -> None:
        self._active_layout = layout.name
        self.ensure_services(layout)
        start_apps = [a for a in layout.apps.values() if a.start]
        windows = self._windows()
        launched: set[str] = set()
        for app in start_apps:
            if self.resolve(app, windows) is not None or self._has_any_window(app, windows):
                continue
            # Zwei Apps mit launch_with teilen sich EINEN Start (z.B. die zwei
            # Firefox-Fenster: Firefox oeffnet beim Start per Sitzungs-
            # Wiederherstellung beide selbst) - nur der Eigentuemer startet.
            owner = app.launch_with or app.name
            if owner in launched:
                continue
            owner_spec = layout.apps.get(owner, app)
            if self._launch(owner_spec):
                launched.add(owner)

        pending = {a.name for a in start_apps if a.slot}
        placed: dict[str, str] = {}
        deadline = self._now() + layout.start_timeout_s
        monitors = self._monitors()
        while pending and self._now() < deadline:
            windows = self._windows()
            for name in sorted(pending):
                app = layout.apps[name]
                window = self.resolve(app, windows, exclude=set(placed.values()))
                if window is None:
                    continue
                self.place(app, window, monitors)
                placed[name] = window.id
                self._recheck_later(layout, app, window.id)
                pending.discard(name)
            if pending:
                self._sleep(POLL_INTERVAL_S)
        if pending:
            logger.warning("Layout '%s': nicht erschienen/platziert: %s", layout.name, ", ".join(sorted(pending)))
        self.start_auto_placer(layout)

    # -- Anordnen (nur offene Fenster, nichts starten) ------------------------------

    def arrange(self, layout_name: str | None = None) -> None:
        layout = self._layout(layout_name)
        if layout is None:
            return
        windows, monitors = self._windows(), self._monitors()
        used: set[str] = set()
        for app in layout.apps.values():
            if not app.slot:
                continue
            window = self.resolve(app, windows, exclude=used)
            if window is not None:
                self.place(app, window, monitors)
                used.add(window.id)

    # -- Intelligente Einzeltasten ---------------------------------------------------

    def focus_app(self, app_name: str, layout_name: str | None = None) -> None:
        layout = self._layout(layout_name)
        if layout is None:
            return
        app = layout.apps.get(app_name)
        if app is None:
            logger.warning("Layout '%s' kennt keine App '%s'", layout.name, app_name)
            return
        windows = self._windows()
        window = self.resolve(app, windows)
        if window is not None:
            self.backend.focus_window(window.id)
            return
        if self._has_any_window(app, windows):
            logger.info("App '%s' laeuft, aber kein passendes Fenster gefunden - nicht erneut gestartet", app.name)
            return
        if not self._launch(app):
            return
        threading.Thread(target=self._place_after_launch, args=(layout, app), name="layout-launch", daemon=True).start()

    def _place_after_launch(self, layout: LayoutSpec, app: AppSpec) -> None:
        deadline = self._now() + layout.start_timeout_s
        while self._now() < deadline:
            window = self.best_window(app, self._windows())
            if window is not None:
                if app.slot:
                    self.place(app, window)
                    self._recheck_later(layout, app, window.id)
                self.backend.focus_window(window.id)
                return
            self._sleep(POLL_INTERVAL_S)

    def focus_then_hotkey(self, app_name: str, layout_name: str | None, vk: int,
                          ctrl: bool = False, shift: bool = False, alt: bool = False) -> None:
        """Fenster der App in den Vordergrund holen (nur wenn es schon existiert,
        NICHT starten) und dann eine Tastenkombination hineinschicken. Ein Hotkey
        geht sonst an das zufaellig aktive Fenster (z.B. Teams) statt an die App."""
        layout = self._layout(layout_name)
        app = layout.apps.get(app_name) if layout is not None else None
        if app is None:
            logger.warning("layout_hotkey: App '%s' im Layout '%s' unbekannt", app_name, layout_name)
            return
        window = self.resolve(app, self._windows())
        if window is None:
            logger.info("layout_hotkey: kein Fenster fuer '%s' - Taste nicht gesendet", app_name)
            return
        if not window.focused:
            self.backend.focus_window(window.id)
            self._sleep(FOCUS_SETTLE_S)
        self.backend.send_hotkey(vk, ctrl, shift, alt)

    def toggle_maximize(self, layout_name: str | None = None) -> None:
        """Vordergrundfenster: normal -> maximiert (bis zur Taskleiste), maximiert
        -> zurueck in seinen Slot (bzw. an die vorher gemerkte Position)."""
        fg = next((w for w in self._windows() if w.focused), None)
        if fg is None:
            return
        if fg.maximized:
            self.backend.restore_window(fg.id)
            target = self._saved_rect.pop(fg.id, None)
            if target is None:
                target = self._slot_rect_of(fg.id, layout_name)
            if target is not None:
                self.backend.move_window(fg.id, target.x, target.y, target.w, target.h)
        else:
            self._saved_rect[fg.id] = fg.rect
            self.backend.maximize_window(fg.id)

    def _slot_rect_of(self, window_id: str, layout_name: str | None) -> Rect | None:
        app_name = self._slot_of.get(window_id)
        layout = self._layout(layout_name)
        if app_name is None or layout is None:
            return None
        app = layout.apps.get(app_name)
        return slot_rect(app.slot, self._monitors()) if app and app.slot else None

    def page(self, direction: str, layout_name: str | None = None) -> None:
        """Blaettern im Vordergrundfenster (PDF-Seite, naechstes Foto, ...): sendet
        die konfigurierte Taste (Standard Pfeil links/rechts). Geht an das Fenster
        im Vordergrund, nicht an ein bestimmtes - ein Stream-Deck-Tastendruck
        nimmt dem Fenster nicht den Fokus."""
        key = "next" if direction in ("next", "right", "forward") else "prev"
        vk = DEFAULT_PAGE_KEYS[key]
        layout = self._layout(layout_name)
        fg = next((w for w in self._windows() if w.focused), None)
        if layout is not None and fg is not None:
            app = next((a for a in layout.apps.values() if self._process_matches(a, fg)), None)
            if app is not None:
                vk = app.page_keys.get(key, vk)
        self.backend.send_hotkey(vk, False, False, False)

    # -- Automatisches Platzieren selbst geoeffneter Fenster ---------------------------

    def start_auto_placer(self, layout: LayoutSpec) -> None:
        if self._placer is not None and self._placer.is_alive():
            return
        if not any(a.auto_place and a.slot for a in layout.apps.values()):
            return
        self._placer_stop.clear()
        self._placer = threading.Thread(target=self._auto_place_loop, args=(layout,), name="layout-auto-place", daemon=True)
        self._placer.start()
        logger.info("Automatisches Platzieren aktiv fuer: %s", ", ".join(a.name for a in layout.apps.values() if a.auto_place))

    def stop_auto_placer(self) -> None:
        self._placer_stop.set()

    def _auto_place_loop(self, layout: LayoutSpec) -> None:
        seen = {w.id for w in self._windows()}  # bereits offene Fenster bleiben unberuehrt
        while not self._placer_stop.wait(AUTO_PLACE_INTERVAL_S):
            try:
                windows = self._windows()
                monitors = None
                for w in windows:
                    if w.id in seen:
                        continue
                    seen.add(w.id)
                    for app in layout.apps.values():
                        if app.auto_place and app.slot and self._process_matches(app, w) \
                                and (app.title is None or app.title.search(w.title)) \
                                and (app.title_exclude is None or not app.title_exclude.search(w.title)):
                            monitors = monitors or self._monitors()
                            self.place(app, w, monitors)
                            self._recheck_later(layout, app, w.id)
                            break
            except Exception:
                logger.exception("Automatisches Platzieren: Durchlauf fehlgeschlagen")


# -- Modulweiter Zugriff fuer actions.dispatch() ----------------------------------------

_engine: LayoutEngine | None = None


def configure(config: dict, backend=None) -> LayoutEngine | None:
    """Wird einmal beim Daemon-Start mit der geladenen profiles.yaml aufgerufen.
    Ohne 'window_layouts'-Block passiert nichts (None) - das Feature ist dann
    komplett inaktiv."""
    global _engine
    raw = config.get("window_layouts") or {}
    if not raw:
        _engine = None
        return None
    layouts = {name: parse_layout(name, body or {}) for name, body in raw.items()}
    _engine = LayoutEngine(layouts, backend=backend)
    logger.info("Fenster-Layouts geladen: %s", ", ".join(layouts))
    return _engine


def get_engine() -> LayoutEngine | None:
    return _engine
