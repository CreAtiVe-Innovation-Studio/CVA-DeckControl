# Tests

Covers the pure-logic modules only: `grid.py`'s tile geometry, the
Web-Mercator/zoom math in `radar.py` and `location_map.py`, the timer state
machine, the short/long key-press distinction in `deckone_controller.py`,
the HA-unreachable error badge (`ha_client.is_healthy()` + the tile
rendering it feeds), the automatic profile-switch matching/edge-triggering
in `window_watch.py`, and the version-comparison logic in `update_check.py`.

Deliberately **not** covered: anything that needs real hardware (USB/HID
devices), a real Home Assistant instance, a live network call
(`ha_client.py`'s actual requests, `_fetch_map`/`_fetch_tile`'s OSM/
RainViewer calls, `devices/*.py`), or the real window-focus detection
`window_watch.py` depends on (`platform_backend.get_active_app_id()` -
GNOME D-Bus / Win32 / AppleScript, mocked in tests). Those have always been
verified by hand against the real thing instead - see the project's commit
history and `SEITEN-LOGIK.md` for how. Automated tests here are a
regression net for the math/state-machine logic that's cheap and
meaningful to check on every push, not a claim that the whole driver is
covered.

Run locally:
```
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

Runs automatically on every push/PR via `.github/workflows/tests.yml`,
using the same `requirements.txt` as production (verified: `hidapi`/`pyusb`
install cleanly on `ubuntu-latest` from prebuilt wheels, no system
dev-libraries needed just to import them - only actually opening a real
device would need those).
