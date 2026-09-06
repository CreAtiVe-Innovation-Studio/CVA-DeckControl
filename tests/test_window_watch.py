"""Tests fuer den automatischen Profilwechsel je nach aktiver App
(window_watch.py) - kein echtes Fenster-System, get_active_app_id() wird
gemockt. Poll-Intervall in den Thread-Tests bewusst winzig, damit die Tests
nicht spuerbar langsam werden."""
import time

from streamdeck_driver import platform_backend, window_watch


def test_build_from_config_returns_none_when_disabled():
    config = {"auto_profile_switch": {"enabled": False, "apps": {"obs": "streaming"}}}
    assert window_watch.build_from_config(config, lambda p: None) is None


def test_build_from_config_returns_none_without_apps():
    config = {"auto_profile_switch": {"enabled": True, "apps": {}}}
    assert window_watch.build_from_config(config, lambda p: None) is None


def test_build_from_config_returns_none_without_section():
    assert window_watch.build_from_config({}, lambda p: None) is None


def test_build_from_config_returns_watcher_when_enabled():
    config = {"auto_profile_switch": {"enabled": True, "apps": {"obs": "streaming"}, "poll_interval_s": 5}}
    watcher = window_watch.build_from_config(config, lambda p: None)
    assert isinstance(watcher, window_watch.WindowWatcher)


def test_match_profile_uses_substring_and_lowercase():
    watcher = window_watch.WindowWatcher({"Firefox": "buero"}, lambda p: None)
    assert watcher._match_profile("firefox_firefox") == "buero"
    assert watcher._match_profile("com.spotify.client") is None


def test_watcher_switches_profile_on_focus_change(monkeypatch):
    calls = []
    seq = iter(["obs", "obs", "firefox"])
    monkeypatch.setattr(platform_backend, "get_active_app_id", lambda: next(seq, "firefox"))
    watcher = window_watch.WindowWatcher(
        {"obs": "streaming", "firefox": "buero"}, lambda p: calls.append(p), poll_interval_s=0.02,
    )
    watcher.start()
    time.sleep(0.15)
    watcher.stop()
    assert calls == ["streaming", "buero"]


def test_watcher_does_not_switch_when_app_unmapped(monkeypatch):
    calls = []
    monkeypatch.setattr(platform_backend, "get_active_app_id", lambda: "unmapped-app")
    watcher = window_watch.WindowWatcher({"obs": "streaming"}, lambda p: calls.append(p), poll_interval_s=0.02)
    watcher.start()
    time.sleep(0.08)
    watcher.stop()
    assert calls == []


def test_watcher_does_not_start_without_apps():
    watcher = window_watch.WindowWatcher({}, lambda p: None, poll_interval_s=0.02)
    watcher.start()
    assert watcher._thread is None
