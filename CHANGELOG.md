# Changelog

Format loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [1.1.0] - 2026-09-06

### Added
- **Location map ("Where is?")**: a new `wo_ist` profile showing tracked
  people via Home Assistant `person`/`device_tracker` entities, composed
  the same way as the radar (one big map image cut into tiles), with
  continuous (non-integer) zoom that auto-fits everyone in view. Tested,
  but not extensively — see the README section for setup and caveats.
- **Update check**: the daemon checks GitHub Releases for a newer version
  once at startup (non-blocking, fails silently if offline or no releases
  exist yet). Result is exposed via the Settings GUI (`/api/update-check`).
- `streamdeck_driver/grid.py`: generic tile-grid geometry (rows/cols/tile
  size/gap), extracted out of `radar.py` so it can be reused by other
  features (like the location map) instead of being hardcoded to the
  DECK ONE's 5x3 layout.

### Fixed
- Race condition between the 3-second background page refresh and a key
  press/profile switch could interleave their image uploads to the DECK
  ONE, producing visibly corrupted/mixed tiles or leaving a stale tile on
  screen after switching pages. See
  [issue #1](https://github.com/CreAtiVe-Innovation-Studio/CVA-DeckControl/issues/1).

## [1.0.0] - 2026-09-04

Initial public release. Linux production-tested; Windows tested end-to-end
including a standalone `.exe` build with autostart. See the README for the
full feature list.
