# Tests

Covers the pure-logic modules only: `grid.py`'s tile geometry, the
Web-Mercator/zoom math in `radar.py` and `location_map.py`, the timer state
machine, and the version-comparison logic in `update_check.py`.

Deliberately **not** covered: anything that needs real hardware (USB/HID
devices), a real Home Assistant instance, or a live network call
(`ha_client.py`'s actual requests, `_fetch_map`/`_fetch_tile`'s OSM/
RainViewer calls, `devices/*.py`). Those have always been verified by hand
against the real thing instead - see the project's commit history and
`SEITEN-LOGIK.md` for how. Automated tests here are a regression net for
the math/state-machine logic that's cheap and meaningful to check on every
push, not a claim that the whole driver is covered.

Run locally:
```
pip install -r requirements-dev.txt
pytest
```

Runs automatically on every push/PR via `.github/workflows/tests.yml` (a
minimal dependency set - Pillow/requests/PyYAML/pytest - not the full
`requirements.txt`, since `hidapi`/`pyusb` need system libraries a bare CI
runner doesn't have and aren't imported by anything these tests touch).
