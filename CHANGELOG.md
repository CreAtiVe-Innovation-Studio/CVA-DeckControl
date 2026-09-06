# Changelog

Format loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [1.2.1] - 2026-09-06

**Not yet extensively tested** — behavior-preserving refactor, checked
against the live values it replaces, but not soaked over time.

### Changed
- `radar.py`'s wind/"clear sky" detection had a Home Assistant weather
  entity ID hardcoded in the source instead of externalized like the home
  coordinates. Moved to `config/location.yaml`'s new optional
  `weather_entity_id` field (falls back to the generic `weather.home` if
  not set).

## [1.2.0] - 2026-09-06

### Added
- **Weather forecast tiles**: a new `weather_forecast` action type showing
  temperature/condition for any day or hour ahead, via Home Assistant's
  `weather.get_forecasts` service. Tested against live forecast data.
- **Rain forecast map**: a new `wetter_vorhersage` profile, built like the
  radar but stripped down to show only RainViewer's precipitation
  *forecast* (nowcast, next ~30-60 min) with no live traffic/lightning.
  Shows a "no data" placeholder when RainViewer has no forecast frames for
  the current location/time, rather than an empty or broken map - tested
  against the live API, but the actual forecast overlay itself couldn't be
  verified against real rain (none was forecast at the time).
- `ha_client.py::get_forecast()`: new helper for the above, 15-minute
  cached.

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
