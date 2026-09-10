# Changelog

Format loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [1.8.4] - 2026-09-10

### Fixed
- The real, recurring root cause behind the last two `mathlern_layout.py`
  fixes: as a systemd user service, the driver's own process frequently
  starts without `DISPLAY` in its environment at all (the desktop session
  imports it into systemd's user manager on its own schedule, which isn't
  reliably before this service starts) - so any GUI subprocess it spawns
  without its own explicit `DISPLAY` (Firefox, gnome-screenshot, custom
  scripts) can't open a window. `platform_backend/linux.py` now sets
  `DISPLAY=:0` as a fallback (only if actually missing) as soon as it's
  imported, fixing this for every GUI-spawning action, not just this one
  script. Verified live: local X11 connections on this system need no
  `XAUTHORITY`, so this one fallback is sufficient.

## [1.8.3] - 2026-09-09

### Fixed
- `tools/mathlern_layout.py`: after v1.8.2's fix, the key still only opened/
  positioned the first (left) window - the second never appeared. Root
  cause: the D-Bus wrapper's hand-rolled parsing of `gdbus call`'s
  pretty-printed GVariant text output was fragile (`Extra data` JSON
  errors on real calls) and, separately, crashed outright on
  `MoveResize`/`Close` (void-return methods return empty stdout, which
  the code fed straight into `json.loads`). Switched to `busctl
  --json=short` (the same approach already used in
  `platform_backend/linux.py::get_active_app_id()` for this exact class
  of problem) and made empty responses return `None` instead of crashing.
  Verified end-to-end: both windows now open and land at their exact
  target position.
- The "MathLern Layout" key also had an unrelated second step attached
  (a random desktop-theme/wallpaper switch) that made it unclear whether
  the layout itself was working - split back into its own separate step.

## [1.8.2] - 2026-09-08

### Fixed
- `tools/mathlern_layout.py`: a stray keystroke bug reported live (typing
  produced garbled digit sequences instead of normal text after using this
  key). Root cause: the script's raw-`ydotool`-keycode fallback (used only
  if the GNOME "Window Calls" D-Bus extension was unavailable) had no
  protection against overlapping runs - pressing the key again while a
  run was still in progress launched a second instance, and their
  press/release events could interleave through `ydotoold`, leaving a
  modifier key (Shift/Super) stuck down at the kernel level. Removed the
  fallback entirely (the D-Bus extension has been reliably active on this
  system throughout) and added a non-blocking lock so a second press
  while one run is in progress is ignored instead of stacking.

## [1.8.1] - 2026-09-08

### Added
- Radar auto-zoom now recognizes a nearby low-flying helicopter (checked
  before landing-approach/storm detection) and zooms in tighter than the
  previous 5km floor - down to 1.5km for one directly overhead - so it's
  actually visible on the small map instead of a barely-visible dot.
  Manual zoom (button on the radar page) also got a tighter 2km step for
  the same reason.

## [1.8.0] - 2026-09-08

### Changed
- Rain forecast map (`wetter_vorhersage`) now uses a 20km radius instead of
  the 5km radar resting-view default, so you can see which direction rain
  is moving in from, not just whether it's already raining at home.
- The page now automatically cycles through the available forecast frames
  every 3s (the existing background refresh), instead of only advancing on
  a manual key press - shows the rain movement as a running loop.

## [1.7.2] - 2026-09-06

### Fixed
- Screenshot action's clipboard copy was hardcoded to `wl-copy` (Wayland
  only) - live reported after switching a session from Wayland to X11,
  where it fails silently ("Failed to connect to a Wayland server"),
  breaking clipboard copy with no visible error. Now detects the running
  session at runtime (`WAYLAND_DISPLAY`/`XDG_SESSION_TYPE`) and picks
  `wl-copy` or `xclip` accordingly; a missing tool now logs one clear,
  actionable line instead of failing silently. Also fixed the temp
  screenshot file being left behind in `/tmp` whenever the clipboard copy
  step failed (cleanup now always runs).

## [1.7.1] - 2026-09-06

### Fixed
- v1.7.0's per-profile `switch_profile` icons had no effect if a generic
  `switch_profile.png` existed under `assets/generated-icons/` (e.g. from
  an earlier icon-generation run) - that static file was always used
  before `render_generated_icon()` got a chance to run, so every
  profile-switch tile kept looking identical despite the new per-profile
  symbols. `switch_profile` now always goes through the procedurally drawn
  icon instead. Verified against all 16 real profile-switch keys in the
  live config - previously all 16 shared one static icon, now every one
  renders distinctly.

## [1.7.0] - 2026-09-06

### Added
- `switch_profile` tiles now get an icon matching their target profile
  instead of always the same generic arrow (`icon_render.py::
  _resolve_profile_symbol()`, keyword-matched against the profile name -
  timer→clock, wo_ist→pin, wetter→cloud, nachhilfe/studium→book, and 11
  more). Matters most on the Elgato Mini, whose whole purpose is switching
  between potentially 10+ profiles across several pages - those tiles used
  to be indistinguishable except for their title text. No keyword match
  (e.g. a made-up profile name) falls back to the original arrow icon.

## [1.6.1] - 2026-09-06

### Fixed
- Five action types (`app_volume`, `open_gui`, `unmapped`, `ha_toggle`,
  `ha_cover`) had no dedicated generated-icon symbol and all fell back to
  the same plain circle, making tiles for genuinely different actions look
  identical. Added distinct symbols (speaker, gear, warning triangle,
  lightbulb, up/down chevrons) and dedicated colors for `ha_toggle`/
  `ha_cover`, which previously also shared the generic default color.

## [1.6.0] - 2026-09-06

### Added
- `auto_profile_switch`: optional automatic DECK ONE profile switching based
  on the currently focused application, configured as a top-level
  `profiles.yaml` key (`apps: {app-id-substring: profile}`). Only fires on
  an actual focus change, never repeatedly, so it doesn't fight a manual
  profile switch made while the same app stays focused. Off by default.
  Active-app detection is platform-specific
  (`platform_backend.get_active_app_id()`): on Linux/Wayland it needs the
  GNOME Shell extension "Window Calls" (falls back to inactive, logged
  once, on KDE/Sway/without it); Windows and macOS backends are
  implemented but, like the rest of `platform_backend`, untested on real
  hardware.

## [1.5.0] - 2026-09-06

### Added
- Visible error badge on Home-Assistant-backed tiles (`ha_sensor`,
  `weather_forecast`, `ha_toggle`, `ha_cover`): a small red badge appears
  when the last request to Home Assistant failed, instead of the failure
  only being logged while the tile keeps showing a harmless `--`. Tracked
  via `ha_client.is_healthy()`, a whole-client reachability flag updated by
  every kind of HA API call. Clears itself on the next successful call, no
  separate health-check request needed.

## [1.4.0] - 2026-09-06

### Added
- `action_long`: an optional second action on any key, triggered when the
  key is held past 0.6s instead of the normal `action`. Keys now fire on
  release rather than press so short vs. long can be distinguished — no
  visible difference for a normal tap. Doesn't apply to the procedurally
  rendered special pages (radar/weather-map/location-map), which keep their
  original press-only behavior.
- CI now installs the full `requirements.txt` instead of a hand-picked
  minimal set, after discovering `deckone_controller.py` transitively needs
  `psutil`/`pyusb`/`hidapi` to even import (verified: these install cleanly
  from prebuilt wheels on `ubuntu-latest`, no system dev-libraries needed
  just to import them).

## [1.3.1] - 2026-09-06

### Fixed
- Radar avatar false-positive "rain" event: RainViewer tiles are fetched with
  smoothing enabled, which creates a soft alpha halo (~41-62/255) around real
  precipitation areas. The old detection threshold (30) was catching that
  halo as rain even with no actual precipitation nearby. Raised to 110,
  verified live against real (non-raining) data.

## [1.3.0] - 2026-09-06

### Added
- Automated test suite (`tests/`, pytest) covering the pure-logic modules:
  `grid.py`'s tile geometry, the Web-Mercator/zoom math in `radar.py` and
  `location_map.py`, the timer state machine, and `update_check.py`'s
  version comparison. 39 tests, all passing. Deliberately does not (and
  cannot) cover anything needing real hardware or a live Home Assistant
  instance — see `tests/README.md`.
- GitHub Actions CI (`.github/workflows/tests.yml`) runs the suite on every
  push/PR, with a minimal dependency set (not the full `requirements.txt` —
  `hidapi`/`pyusb` need system libraries a bare CI runner doesn't have and
  aren't imported by anything the tests touch).
- `requirements-dev.txt` for local test running.

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
