"""Zustands-Engine fuer den 'timer'-Aktionstyp (Countdown, der bei Erreichen
der Zielzeit einen Ton abspielt und dann als Stoppuhr in die Ueberzeit
weiterzaehlt, bis eine Taste ihn stoppt). Zustand liegt hier (nicht im
DeckOneController), weil ein eigener 1s-Ticker die Zielzeit pruefen und den
Ton ausloesen muss, UNABHAENGIG von der langsameren Seiten-Refresh-Rate
(~3s) - sonst koennte der Ton je nach Zufall des Seiten-Timings bis zu 3s
zu spaet kommen."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import platform_backend
from .paths import project_root

logger = logging.getLogger("streamdeck_driver.timer_engine")

PROJECT_ROOT = project_root()
DEFAULT_SOUND = PROJECT_ROOT / "assets" / "sounds" / "timer_default.wav"
RESULT_DISPLAY_S = 60.0
TICK_INTERVAL_S = 1.0


@dataclass
class TimerState:
    phase: str = "ready"  # ready | running | overtime | result
    target_s: float = 0.0
    sound_path: str | None = None
    start_ts: float | None = None
    result_elapsed_s: float = 0.0
    result_over_s: float = 0.0
    result_until: float = 0.0

    def elapsed(self) -> float:
        if self.start_ts is None:
            return 0.0
        return max(0.0, time.monotonic() - self.start_ts)


_timers: dict[str, TimerState] = {}
_lock = threading.RLock()


def _resolve_sound(sound_path: str | None) -> Path:
    if not sound_path or sound_path == "default":
        return DEFAULT_SOUND
    p = Path(sound_path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def get_state(key_id: str, duration_min: float, sound_path: str | None = None) -> TimerState:
    """Liefert den (persistenten) Zustand einer Timer-Taste, legt ihn beim
    ersten Aufruf an. duration_min/sound_path werden bei jedem Aufruf
    aktualisiert (billig), damit ein Config-Reload ohne Treiber-Neustart
    wirksam wird, sobald die Taste als naechstes im 'ready'-Zustand ist."""
    with _lock:
        st = _timers.get(key_id)
        if st is None:
            st = TimerState()
            _timers[key_id] = st
        if st.phase == "ready":
            st.target_s = duration_min * 60.0
        st.sound_path = sound_path
        return st


def handle_press(key_id: str, duration_min: float, sound_path: str | None = None) -> TimerState:
    """Ein Tastendruck durchlaeuft: ready -> running -> (automatisch bei
    Zielzeit) overtime -> (Druck) result -> (Druck oder 60s) ready.
    Ein Druck waehrend 'running' ODER 'overtime' stoppt gleichermassen und
    zeigt das Ergebnis - 'wie weit drueber' bei overtime, sonst einfach die
    bis dahin gelaufene Gesamtzeit."""
    with _lock:
        st = get_state(key_id, duration_min, sound_path)
        now = time.monotonic()
        if st.phase == "ready":
            st.target_s = duration_min * 60.0
            st.start_ts = now
            st.phase = "running"
        elif st.phase in ("running", "overtime"):
            elapsed = st.elapsed()
            st.result_elapsed_s = elapsed
            st.result_over_s = max(0.0, elapsed - st.target_s)
            st.result_until = now + RESULT_DISPLAY_S
            st.phase = "result"
            st.start_ts = None
        elif st.phase == "result":
            st.phase = "ready"
            st.start_ts = None
        logger.info("Timer '%s': Taste gedrueckt -> Phase '%s'", key_id, st.phase)
        return st


_SUBLABELS = {"ready": "BEREIT", "running": "LÄUFT", "overtime": "ÜBER"}


def describe(state: TimerState) -> tuple[str, float, str]:
    """Fasst den rohen Zustand in (render_phase, display_seconds, sublabel)
    zusammen - das ist, was icon_render.render_timer_card() tatsaechlich
    anzeigen soll. 'result' (Anzeige nach dem Stoppen) wird dabei auf
    'running' (gruen, wenn unter der Zielzeit gestoppt -> 'GESAMT') oder
    'overtime' (rot, wenn drueber -> 'ÜBER') abgebildet, damit auf einen
    Blick sichtbar ist, ob man drunter oder drueber geblieben ist."""
    if state.phase == "ready":
        return "ready", state.target_s, _SUBLABELS["ready"]
    if state.phase == "running":
        return "running", max(0.0, state.target_s - state.elapsed()), _SUBLABELS["running"]
    if state.phase == "overtime":
        return "overtime", state.elapsed() - state.target_s, _SUBLABELS["overtime"]
    if state.phase == "result":
        if state.result_over_s > 0:
            return "overtime", state.result_over_s, _SUBLABELS["overtime"]
        return "running", state.result_elapsed_s, "GESAMT"
    return "ready", state.target_s, _SUBLABELS["ready"]


def _play_sound(sound_path: str | None) -> None:
    sound = _resolve_sound(sound_path)
    if not sound.exists():
        logger.warning("Timer-Sound nicht gefunden: %s", sound)
        return
    platform_backend.play_sound(sound)


def _tick() -> None:
    now = time.monotonic()
    with _lock:
        due_sounds: list[str | None] = []
        for key_id, st in _timers.items():
            if st.phase == "running" and st.start_ts is not None and (now - st.start_ts) >= st.target_s:
                st.phase = "overtime"
                due_sounds.append(st.sound_path)
                logger.info("Timer '%s': Zielzeit erreicht - Ton + Ueberzeit-Zaehlung", key_id)
            elif st.phase == "result" and now >= st.result_until:
                st.phase = "ready"
                st.start_ts = None
    for sound_path in due_sounds:
        threading.Thread(target=_play_sound, args=(sound_path,), daemon=True).start()


_ticker_thread: threading.Thread | None = None
_ticker_stop = threading.Event()


def start_ticker() -> None:
    global _ticker_thread
    if _ticker_thread is not None:
        return
    _ticker_stop.clear()

    def _run():
        while not _ticker_stop.wait(TICK_INTERVAL_S):
            try:
                _tick()
            except Exception:
                logger.exception("Fehler im Timer-Ticker")

    _ticker_thread = threading.Thread(target=_run, name="timer-ticker", daemon=True)
    _ticker_thread.start()
    logger.info("Timer-Ticker gestartet (Intervall %ss)", TICK_INTERVAL_S)


def stop_ticker() -> None:
    global _ticker_thread
    _ticker_stop.set()
    if _ticker_thread is not None:
        _ticker_thread.join(timeout=2)
        _ticker_thread = None
