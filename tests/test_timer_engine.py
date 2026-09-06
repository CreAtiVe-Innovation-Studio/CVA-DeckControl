"""Tests fuer den Timer-Zustandsautomaten (timer_engine.py) - reine
Zustandslogik, kein echter Sound/Hintergrund-Thread noetig (start_ticker()
wird hier bewusst NICHT gestartet, Phasenwechsel bei Zielzeit-Erreichen wird
stattdessen direkt ueber _tick() getestet)."""
import uuid

import pytest

from streamdeck_driver import timer_engine


@pytest.fixture
def key_id():
    """Eigene, zufaellige Taste pro Test - timer_engine haelt Zustand in
    einem MODUL-globalen Dict, ohne das wuerden sich Tests gegenseitig
    Zustand ueberschreiben."""
    return f"test:{uuid.uuid4()}"


def test_new_timer_starts_in_ready_phase(key_id):
    state = timer_engine.get_state(key_id, duration_min=25)
    assert state.phase == "ready"
    assert state.target_s == 25 * 60.0


def test_first_press_starts_the_timer(key_id):
    state = timer_engine.handle_press(key_id, duration_min=1)
    assert state.phase == "running"
    assert state.start_ts is not None


def test_press_while_running_shows_result(key_id):
    timer_engine.handle_press(key_id, duration_min=25)  # ready -> running
    state = timer_engine.handle_press(key_id, duration_min=25)  # running -> result
    assert state.phase == "result"
    assert state.start_ts is None
    assert state.result_over_s == 0.0  # noch nicht ueber der Zielzeit gestoppt


def test_press_while_result_returns_to_ready(key_id):
    timer_engine.handle_press(key_id, duration_min=1)  # ready -> running
    timer_engine.handle_press(key_id, duration_min=1)  # running -> result
    state = timer_engine.handle_press(key_id, duration_min=1)  # result -> ready
    assert state.phase == "ready"


def test_tick_moves_running_to_overtime_after_target_reached(key_id):
    state = timer_engine.handle_press(key_id, duration_min=1)
    state.target_s = 0.0  # Zielzeit ist "sofort" erreicht, ohne echt zu warten
    timer_engine._tick()
    assert state.phase == "overtime"


def test_describe_ready_shows_full_target_duration(key_id):
    state = timer_engine.get_state(key_id, duration_min=10)
    phase, seconds, sublabel = timer_engine.describe(state)
    assert phase == "ready"
    assert seconds == 10 * 60.0
    assert sublabel == "BEREIT"


def test_describe_overtime_result_reports_over_seconds(key_id):
    state = timer_engine.handle_press(key_id, duration_min=1)
    state.target_s = 0.0
    timer_engine._tick()  # running -> overtime
    state.result_over_s = 42.0
    phase, seconds, _ = timer_engine.describe(
        timer_engine.TimerState(phase="result", target_s=state.target_s, result_over_s=42.0),
    )
    assert phase == "overtime"
    assert seconds == 42.0


def test_describe_under_target_result_reports_total_elapsed(key_id):
    state = timer_engine.TimerState(phase="result", result_over_s=0.0, result_elapsed_s=17.0)
    phase, seconds, sublabel = timer_engine.describe(state)
    assert phase == "running"
    assert seconds == 17.0
    assert sublabel == "GESAMT"
