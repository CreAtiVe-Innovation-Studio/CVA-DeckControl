"""Tests fuer die Layout-Engine (windowing/engine.py) mit einem Fake-Backend -
kein echtes Fenstersystem. Siehe tests/README.md fuer die Abgrenzung: die
echten Win32-/D-Bus-Aufrufe stecken in platform_backend/windows_wm.py bzw.
linux_wm.py und sind von Hand gegen ein echtes System geprueft."""
import itertools
import time

from streamdeck_driver import windowing
from streamdeck_driver.windowing import engine
from streamdeck_driver.windowing.geometry import Rect

MONITORS = [
    {"x": 0, "y": 0, "w": 2560, "h": 1440, "work_x": 0, "work_y": 0, "work_w": 2560, "work_h": 1368, "primary": True},
    {"x": 2560, "y": 0, "w": 1920, "h": 1080, "work_x": 2560, "work_y": 0, "work_w": 1920, "work_h": 1032},
]


class FakeBackend:
    """Haelt Fenster als Dicts; 'launchers' bildet einen Startbefehl auf die
    Fenster ab, die dadurch 'erscheinen'."""

    def __init__(self, windows=None, launchers=None):
        self.windows = {w["id"]: dict(w) for w in (windows or [])}
        self.launchers = launchers or {}
        self.calls = []
        self._ids = itertools.count(1000)

    def add_window(self, app_id, title="", x=100, y=100, w=800, h=600, **extra):
        wid = str(next(self._ids))
        self.windows[wid] = {"id": wid, "app_id": app_id, "title": title, "x": x, "y": y, "w": w, "h": h, **extra}
        return wid

    def list_windows(self):
        return [dict(w) for w in self.windows.values()]

    def list_monitors(self):
        return [dict(m) for m in MONITORS]

    def move_window(self, window_id, x, y, w, h):
        self.calls.append(("move", window_id, x, y, w, h))
        self.windows[window_id].update(x=x, y=y, w=w, h=h, maximized=False, minimized=False)

    def focus_window(self, window_id):
        self.calls.append(("focus", window_id))
        for wid, win in self.windows.items():
            win["focused"] = wid == window_id
        self.windows[window_id]["minimized"] = False

    def maximize_window(self, window_id):
        self.calls.append(("maximize", window_id))
        self.windows[window_id]["maximized"] = True

    def restore_window(self, window_id):
        self.calls.append(("restore", window_id))
        self.windows[window_id]["maximized"] = False

    def minimize_window(self, window_id):
        self.calls.append(("minimize", window_id))

    def send_hotkey(self, vk, ctrl, shift, alt):
        self.calls.append(("hotkey", vk, ctrl, shift, alt))

    def open_command(self, cmd):
        self.calls.append(("open", cmd))
        for spec in self.launchers.get(cmd, []):
            self.add_window(**spec)

    def open_url(self, url):
        self.calls.append(("url", url))
        for spec in self.launchers.get(url, []):
            self.add_window(**spec)

    def start_minimized(self, command, cwd=None):
        self.calls.append(("service", command, cwd))

    def calls_of(self, kind):
        return [c for c in self.calls if c[0] == kind]


def _fake_clock():
    t = itertools.count(0, 1)
    return lambda: float(next(t))


def make_engine(backend, raw_layout, **kwargs):
    layout = engine.parse_layout("unterricht", raw_layout, platform_key="windows")
    return engine.LayoutEngine({"unterricht": layout}, backend=backend, sleep=lambda s: None, monotonic=_fake_clock(), **kwargs), layout


LESSON = {
    "start_timeout_s": 50,
    "services": [
        {"name": "llama", "port": 8080, "command": {"windows": "C:\\llama.bat", "linux": "/opt/llama.sh"}},
        {"name": "comfy", "port": 8188, "command": {"windows": "C:\\comfy.bat"}, "cwd": "C:\\comfy"},
    ],
    "apps": {
        "mission": {
            "match": {"process": "firefox", "order": 0},
            "slot": {"monitor": "left", "x": 0, "y": 0, "w": 1, "h": 1},
            "launch": "C:\\firefox.exe", "start": True,
        },
        "admin": {
            "match": {"process": ["firefox"], "order": 1},
            "slot": {"monitor": "right", "x": 0.5, "y": 0, "w": 0.5, "h": 1},
            "launch_with": "mission", "start": True,
        },
        "teams": {
            "match": {"process": "ms-teams"},
            "slot": {"monitor": "right", "x": 0, "y": 0, "w": 0.25, "h": 1},
            "launch_uri": "ms-teams:", "start": True,
        },
        "photos": {
            "match": {"process": "photos"},
            "slot": {"monitor": "right", "x": 0.4, "y": 0, "w": 0.6, "h": 0.8},
            "page_keys": {"next": 34, "prev": 33}, "auto_place": True,
        },
        "pdf": {
            "match": {"process": "msedge", "title": r"\.pdf"},
            "slot": {"monitor": "right", "x": 0.45, "y": 0, "w": 0.55, "h": 0.85},
            "auto_place": True,
        },
    },
}


# -- Konfiguration --------------------------------------------------------------------------

def test_pick_os_selects_platform_value_and_default():
    assert engine.pick_os({"windows": "a", "linux": "b"}, "linux") == "b"
    assert engine.pick_os({"windows": "a", "default": "z"}, "macos") == "z"
    assert engine.pick_os("plain", "windows") == "plain"
    assert engine.pick_os(None, "windows") is None


def test_parse_layout_skips_service_without_command_for_platform():
    layout = engine.parse_layout("x", LESSON, platform_key="linux")
    assert [s.name for s in layout.services] == ["llama"]
    assert layout.services[0].command == "/opt/llama.sh"


def test_configure_without_block_is_inactive():
    assert engine.configure({}) is None
    assert engine.get_engine() is None


def test_configure_builds_engine():
    eng = engine.configure({"window_layouts": {"unterricht": LESSON}}, backend=FakeBackend())
    assert eng is not None and engine.get_engine() is eng
    engine.configure({})  # wieder aufraeumen, damit andere Tests nicht beeinflusst werden


# -- Zuordnung Fenster <-> App ----------------------------------------------------------------

def test_order_distinguishes_two_windows_of_one_process_by_position_not_title():
    b = FakeBackend()
    b.add_window("firefox", "Mission - Mozilla Firefox", x=0, w=2560)
    b.add_window("firefox", "irgendwas Privates", x=3000)
    eng, layout = make_engine(b, LESSON)
    wins = eng._windows()
    assert eng.matching_windows(layout.apps["mission"], wins)[0].rect.x == 0
    assert eng.matching_windows(layout.apps["admin"], wins)[0].rect.x == 3000


def test_order_beyond_window_count_matches_nothing():
    b = FakeBackend()
    b.add_window("firefox", x=0)
    eng, layout = make_engine(b, LESSON)
    assert eng.matching_windows(layout.apps["admin"], eng._windows()) == []


def test_title_regex_and_exclusion():
    b = FakeBackend()
    b.add_window("msedge", "Bericht.pdf - Profil 1 - Microsoft Edge")
    b.add_window("msedge", "Startseite - Microsoft Edge")
    eng, layout = make_engine(b, LESSON)
    found = eng.matching_windows(layout.apps["pdf"], eng._windows())
    assert len(found) == 1 and found[0].title.startswith("Bericht")


def test_best_window_prefers_largest_visible_over_minimized_and_helper_windows():
    b = FakeBackend()
    b.add_window("ms-teams", "Hilfsfenster", w=200, h=100)
    big = b.add_window("ms-teams", "Hauptfenster", w=900, h=900)
    b.add_window("ms-teams", "versteckt", w=3000, h=3000, minimized=True)
    eng, layout = make_engine(b, LESSON)
    assert eng.best_window(layout.apps["teams"], eng._windows()).id == big


# -- Start-Taste ----------------------------------------------------------------------------------

def _no_ports(monkeypatch, open_ports=()):
    monkeypatch.setattr(engine, "port_is_open", lambda host, port, timeout_s=0.4: port in open_ports)


def test_start_places_open_windows_and_launches_missing_ones(monkeypatch):
    _no_ports(monkeypatch)
    b = FakeBackend(launchers={"ms-teams:": [{"app_id": "ms-teams", "title": "Teams", "w": 400, "h": 900}]})
    b.add_window("firefox", "mission", x=100)
    b.add_window("firefox", "admin", x=3000)
    eng, layout = make_engine(b, LESSON)
    eng._run_start(layout)

    assert b.calls_of("open") == []  # Firefox laeuft schon, kein zweiter Start
    assert b.calls_of("url") == [("url", "ms-teams:")]
    moved = {c[1]: c[2:] for c in b.calls_of("move")}
    by_app = {w["app_id"] + w["title"]: wid for wid, w in b.windows.items()}
    assert moved[by_app["firefoxmission"]] == (0, 0, 2560, 1368)
    assert moved[by_app["firefoxadmin"]] == (3520, 0, 960, 1032)
    assert moved[by_app["ms-teamsTeams"]] == (2560, 0, 480, 1032)
    engine_placer = eng._placer
    eng.stop_auto_placer()
    if engine_placer:
        engine_placer.join(timeout=3)


def test_start_launches_shared_owner_only_once(monkeypatch):
    _no_ports(monkeypatch)
    b = FakeBackend(launchers={"C:\\firefox.exe": [
        {"app_id": "firefox", "title": "a", "x": 50}, {"app_id": "firefox", "title": "b", "x": 3100},
    ]})
    eng, layout = make_engine(b, LESSON)
    eng._run_start(layout)
    assert b.calls_of("open") == [("open", "C:\\firefox.exe")]
    assert len(b.calls_of("move")) >= 2
    eng.stop_auto_placer()


def test_start_runs_services_only_when_port_closed(monkeypatch):
    _no_ports(monkeypatch, open_ports={8080})
    b = FakeBackend()
    eng, layout = make_engine(b, LESSON)
    assert eng.ensure_services(layout) == ["comfy"]
    assert b.calls_of("service") == [("service", "C:\\comfy.bat", "C:\\comfy")]


def test_start_survives_app_that_never_appears(monkeypatch):
    _no_ports(monkeypatch)
    b = FakeBackend()  # nichts erscheint
    eng, layout = make_engine(b, LESSON)
    eng._run_start(layout)  # darf nicht haengen/werfen (gefaelschte Uhr laeuft ab)
    assert b.calls_of("move") == []
    eng.stop_auto_placer()


def test_second_start_press_is_ignored_while_running(monkeypatch):
    _no_ports(monkeypatch)
    b = FakeBackend()
    eng, layout = make_engine(b, LESSON)
    eng._start_lock.acquire()
    eng.start("unterricht")  # soll sofort zurueckkehren, ohne Thread
    assert b.calls == []
    eng._start_lock.release()


def test_unknown_layout_name_is_ignored():
    eng, _ = make_engine(FakeBackend(), LESSON)
    eng.start("gibts-nicht")
    eng.arrange("gibts-nicht")
    eng.focus_app("x", "gibts-nicht")


def test_start_does_not_launch_when_process_already_runs_with_other_windows(monkeypatch):
    """Ein zweiter Firefox-Start wuerde nur ein leeres Zusatzfenster oeffnen."""
    _no_ports(monkeypatch)
    b = FakeBackend()
    b.add_window("firefox", "irgendein privater Tab", x=400)
    eng, layout = make_engine(b, LESSON)
    eng._run_start(layout)
    assert b.calls_of("open") == []
    eng.stop_auto_placer()


def test_bound_window_is_found_again_after_its_title_changed():
    """Im Unterricht wechseln die Tabs, damit der Fenstertitel - die Taste muss
    das beim Start platzierte Fenster trotzdem wiederfinden."""
    raw = {"apps": {"admin": {
        "match": {"process": "firefox", "title": "^MathLern"},
        "slot": {"monitor": "right", "x": 0.5, "y": 0, "w": 0.5, "h": 1},
    }}}
    b = FakeBackend()
    wid = b.add_window("firefox", "MathLern - Mozilla Firefox", x=3000)
    b.add_window("firefox", "Rezepte - Mozilla Firefox", x=100, w=3000, h=3000)
    eng, layout = make_engine(b, raw)
    eng.arrange("unterricht")
    b.windows[wid]["title"] = "Whiteboard - Mozilla Firefox"  # anderer Tab gewaehlt
    eng.focus_app("admin", "unterricht")
    assert b.calls_of("focus") == [("focus", wid)]


def test_bound_window_that_was_closed_is_not_used_any_more():
    raw = {"apps": {"x": {"match": {"process": "app"}, "slot": {"x": 0, "y": 0, "w": 1, "h": 1}}}}
    b = FakeBackend()
    old = b.add_window("app", "alt")
    eng, layout = make_engine(b, raw)
    eng.arrange("unterricht")
    del b.windows[old]
    new = b.add_window("app", "neu")
    eng.focus_app("x", "unterricht")
    assert b.calls_of("focus") == [("focus", new)]


def test_focus_does_not_launch_when_process_runs_but_no_window_matches():
    b = FakeBackend()
    b.add_window("msedge", "Startseite - Edge")
    raw = {"apps": {"pdf": {
        "match": {"process": "msedge", "title": r"\.pdf"}, "launch": "edge.exe",
        "slot": {"x": 0, "y": 0, "w": 1, "h": 1},
    }}}
    eng, _ = make_engine(b, raw)
    eng.focus_app("pdf", "unterricht")
    assert b.calls == []


# -- Anordnen / Fokus --------------------------------------------------------------------------------

def test_arrange_moves_only_open_windows_and_launches_nothing():
    b = FakeBackend()
    b.add_window("ms-teams", "T", w=300, h=900)
    eng, layout = make_engine(b, LESSON)
    eng.arrange("unterricht")
    assert b.calls_of("open") == [] and b.calls_of("url") == []
    assert [c[2:] for c in b.calls_of("move")] == [(2560, 0, 480, 1032)]


def test_focus_existing_app_raises_it_without_launching():
    b = FakeBackend()
    wid = b.add_window("ms-teams", "T")
    eng, _ = make_engine(b, LESSON)
    eng.focus_app("teams", "unterricht")
    assert b.calls == [("focus", wid)]


def test_focus_restores_minimized_window_via_focus_call():
    b = FakeBackend()
    wid = b.add_window("ms-teams", "T", minimized=True)
    eng, _ = make_engine(b, LESSON)
    eng.focus_app("teams", "unterricht")
    assert b.windows[wid]["minimized"] is False


def test_focus_missing_app_launches_then_places_and_focuses():
    b = FakeBackend(launchers={"ms-teams:": [{"app_id": "ms-teams", "title": "T", "w": 400, "h": 900}]})
    eng, layout = make_engine(b, LESSON)
    eng.focus_app("teams", "unterricht")
    deadline = time.time() + 3
    while time.time() < deadline and not b.calls_of("focus"):
        time.sleep(0.02)
    assert b.calls_of("url") == [("url", "ms-teams:")]
    assert b.calls_of("move") and b.calls_of("focus")


def test_focus_missing_app_without_launch_entry_does_nothing():
    b = FakeBackend()
    eng, _ = make_engine(b, LESSON)
    eng.focus_app("photos", "unterricht")
    assert b.calls == []


# -- Maximieren / Blaettern ------------------------------------------------------------------------------

def test_maximize_then_restore_returns_to_original_position():
    b = FakeBackend()
    wid = b.add_window("photos", "4.PNG", x=3400, y=20, w=1100, h=850, focused=True)
    eng, _ = make_engine(b, LESSON)
    eng.toggle_maximize("unterricht")
    assert b.windows[wid]["maximized"] is True
    eng.toggle_maximize("unterricht")
    assert b.windows[wid]["maximized"] is False
    assert (b.windows[wid]["x"], b.windows[wid]["y"], b.windows[wid]["w"], b.windows[wid]["h"]) == (3400, 20, 1100, 850)


def test_restore_of_externally_maximized_window_goes_to_its_slot():
    b = FakeBackend()
    wid = b.add_window("photos", "4.PNG", maximized=True, focused=True)
    eng, layout = make_engine(b, LESSON)
    eng._slot_of[wid] = "photos"
    eng.toggle_maximize("unterricht")
    assert (b.windows[wid]["x"], b.windows[wid]["y"], b.windows[wid]["w"], b.windows[wid]["h"]) == (3328, 0, 1152, 826)


def test_maximize_without_focused_window_does_nothing():
    b = FakeBackend()
    b.add_window("photos", "x")
    eng, _ = make_engine(b, LESSON)
    eng.toggle_maximize("unterricht")
    assert b.calls == []


def test_page_sends_default_arrow_keys():
    b = FakeBackend()
    b.add_window("msedge", "x.pdf", focused=True)
    eng, _ = make_engine(b, LESSON)
    eng.page("next", "unterricht")
    eng.page("prev", "unterricht")
    assert [c[1] for c in b.calls_of("hotkey")] == [39, 37]


def test_page_uses_per_app_key_override():
    b = FakeBackend()
    b.add_window("photos", "4.PNG", focused=True)
    eng, _ = make_engine(b, LESSON)
    eng.page("next", "unterricht")
    eng.page("prev", "unterricht")
    assert [c[1] for c in b.calls_of("hotkey")] == [34, 33]


def test_page_without_focused_window_still_sends_default_key():
    b = FakeBackend()
    eng, _ = make_engine(b, LESSON)
    eng.page("next", "unterricht")
    assert b.calls_of("hotkey") == [("hotkey", 39, False, False, False)]


# -- Automatisches Platzieren selbst geoeffneter Fenster -----------------------------------------------------------

def test_auto_placer_places_new_matching_windows_but_leaves_existing_ones(monkeypatch):
    monkeypatch.setattr(engine, "AUTO_PLACE_INTERVAL_S", 0.02)
    b = FakeBackend()
    old = b.add_window("photos", "alt", x=1, y=1, w=500, h=500)
    eng, layout = make_engine(b, LESSON)
    eng.start_auto_placer(layout)
    time.sleep(0.1)
    new_photo = b.add_window("photos", "4.PNG", x=5, y=5, w=300, h=300)
    new_pdf = b.add_window("msedge", "Buch.pdf - Edge", x=7, y=7, w=300, h=300)
    other = b.add_window("msedge", "Startseite - Edge", x=9, y=9, w=300, h=300)
    deadline = time.time() + 3
    while time.time() < deadline and len(b.calls_of("move")) < 2:
        time.sleep(0.02)
    eng.stop_auto_placer()
    eng._placer.join(timeout=3)

    moved_ids = {c[1] for c in b.calls_of("move")}
    assert moved_ids == {new_photo, new_pdf}
    assert old not in moved_ids and other not in moved_ids
    assert (b.windows[new_photo]["x"], b.windows[new_photo]["y"]) == (3328, 0)


def test_auto_placer_not_started_without_auto_place_apps():
    b = FakeBackend()
    raw = {"apps": {"x": {"match": {"process": "x"}, "slot": {"x": 0, "y": 0, "w": 1, "h": 1}}}}
    eng, layout = make_engine(b, raw)
    eng.start_auto_placer(layout)
    assert eng._placer is None


# -- Aktionen -----------------------------------------------------------------------------------------------------

def test_run_action_routes_to_engine(monkeypatch):
    calls = []

    class Spy:
        def start(self, layout): calls.append(("start", layout))
        def arrange(self, layout): calls.append(("arrange", layout))
        def focus_app(self, app, layout): calls.append(("focus", app, layout))
        def page(self, direction, layout): calls.append(("page", direction, layout))
        def toggle_maximize(self, layout): calls.append(("max", layout))
        def stop_auto_placer(self): calls.append(("stop",))

    monkeypatch.setattr(engine, "_engine", Spy())
    for action in (
        {"type": "layout_start", "layout": "u"}, {"type": "layout_arrange", "layout": "u"},
        {"type": "layout_focus", "app": "teams", "layout": "u"}, {"type": "layout_page", "direction": "prev", "layout": "u"},
        {"type": "layout_maximize", "layout": "u"}, {"type": "layout_stop"},
    ):
        windowing.run_action(action)
    assert calls == [
        ("start", "u"), ("arrange", "u"), ("focus", "teams", "u"), ("page", "prev", "u"), ("max", "u"), ("stop",),
    ]


def test_run_action_without_engine_is_harmless(monkeypatch):
    monkeypatch.setattr(engine, "_engine", None)
    windowing.run_action({"type": "layout_start"})


def test_dispatch_routes_layout_actions(monkeypatch):
    from streamdeck_driver import actions
    seen = []
    monkeypatch.setattr(windowing, "run_action", lambda action: seen.append(action["type"]))
    actions.dispatch({"type": "layout_maximize"}, "Gross")
    assert seen == ["layout_maximize"]


def test_rect_close_to_helper():
    assert Rect(0, 0, 100, 100).close_to(Rect(2, -2, 101, 99))
    assert not Rect(0, 0, 100, 100).close_to(Rect(10, 0, 100, 100))


def test_hotkey_holt_fenster_nach_vorn_und_sendet_taste():
    backend = FakeBackend()
    backend.add_window("firefox", "MathLern", x=0, y=0, w=1000, h=900, focused=False)
    wid = backend.add_window("firefox", "MathLern", x=2600, y=0, w=1000, h=900, focused=False)
    eng, _ = make_engine(backend, LESSON)
    eng.focus_then_hotkey("admin", "unterricht", 0x37, ctrl=True, shift=True, alt=True)
    assert backend.calls_of("focus") == [("focus", wid)]
    assert backend.calls_of("hotkey") == [("hotkey", 0x37, True, True, True)]
    assert backend.calls.index(("focus", wid)) < backend.calls.index(("hotkey", 0x37, True, True, True))


def test_hotkey_ohne_fenster_sendet_nichts_und_startet_nichts():
    backend = FakeBackend()
    eng, _ = make_engine(backend, LESSON)
    eng.focus_then_hotkey("admin", "unterricht", 0x37, ctrl=True)
    assert backend.calls == []


def test_hotkey_unbekannte_app_wird_ignoriert():
    backend = FakeBackend()
    eng, _ = make_engine(backend, LESSON)
    eng.focus_then_hotkey("gibtsnicht", "unterricht", 0x37)
    assert backend.calls == []