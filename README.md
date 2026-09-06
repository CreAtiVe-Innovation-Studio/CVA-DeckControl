# CVA-DeckControl

[![Tests](https://github.com/CreAtiVe-Innovation-Studio/CVA-DeckControl/actions/workflows/tests.yml/badge.svg)](https://github.com/CreAtiVe-Innovation-Studio/CVA-DeckControl/actions/workflows/tests.yml)

**Read this in other languages:** 🇩🇪 [Deutsch](docs/README_DE.md) · [Changelog](CHANGELOG.md)

Self-built driver with openly viewable source (source-available, see
"License" below) for the **Elgato Stream Deck Mini** and the **Streamplify
DECK ONE** — fully YAML-configured, no code needed for your own keys/pages/
profiles. Not an official driver, no third-party SDK: both devices' USB
protocols were reverse-engineered directly against real hardware for this.

Built as a personal project because the official software didn't offer
some features (live weather radar? an analog-clock timer? a reactive
avatar that reacts to air traffic outside the window?) — and because it
was simply fun to talk to the hardware directly.

## What it can do

- **Any number of keys/pages/profiles**, defined purely in YAML — adding a
  new key means: add a YAML block, restart the driver, done
- **Live radar**: air traffic (adsb.lol) + precipitation + lightning
  detection, composed into one 15-tile map image, including a reactive
  Mii/VTuber avatar that reacts to weather/air traffic
- **Timer/stopwatch** with digital or analog display directly on the key
- **Browser settings GUI** for editing all keys/pages/profiles without
  touching YAML by hand — including creating/renaming/deleting pages and
  profiles, copying a key from an existing template
- **Live web view** of both devices (just for fun — shows in the browser
  what's currently on the real hardware)
- **Import/export** for Elgato/Streamplify profiles AND for its own YAML
  format, to share setups with others
- **Location map ("Where is?")**: same one-big-image-cut-into-tiles idea as
  the radar, showing tracked people via Home Assistant (`person`/
  `device_tracker` entities) with auto-fit zoom — tested, but not
  extensively (see the dedicated section below)
- **Rain forecast map**: a separate, stripped-down map page showing only
  RainViewer's precipitation *forecast* (next ~30-60 min), no live traffic/
  lightning clutter — tested, but not extensively (see below)
- **Weather forecast tiles**: a `weather_forecast` action type for simple
  per-key forecast cards (temperature/condition, any day or hour ahead),
  via Home Assistant's forecast service
- Action types: hotkeys, launching programs/URLs, per-app volume, live
  system metrics (CPU/RAM/GPU), Home Assistant control, and more — full
  list in [SEITEN-LOGIK.md](SEITEN-LOGIK.md) (German, technical reference)

## Performance

Built to sit quietly in the background, not to be a resource hog:

- **Idle memory footprint: ~20MB RSS**, CPU usage effectively 0% between
  key presses/render cycles (measured on the reference Linux install —
  actual numbers will vary with your hardware).
- Network-heavy features are cached instead of queried live: radar
  precipitation tiles for 5 minutes, Windows GPU stats refreshed and
  cached every 5s in the background — no render cycle ever waits on a
  network round-trip.
- Icon rendering happens once per config change/page switch, not per frame.
- The live web view is fully inert when switched off (the default) — the
  snapshot store behind it is then a plain no-op call, no measurable
  overhead.
- Background threads (GPU stats, timer ticker, USB event loops) are
  lightweight polling loops with multi-second intervals, not tight loops
  pinning a CPU core.

## Supported hardware

| Device | Keys | Status |
|---|---|---|
| Elgato Stream Deck Mini | 6 | Verified |
| Streamplify DECK ONE | 15 | Verified |
| Elgato Original / MK.2 / XL | 15 / 15 / 32 | Experimental, see below |

Other Elgato models run through a generic code path
(`streamdeck_driver/devices/elgato_generic.py`), but without real hardware
to test against it stays unverified — see "Platform support" below.

## Setup

**Linux:** `./install.sh` handles venv + dependencies + config templates in
one step (never overwrites an existing `config/*.yaml`). Then:

```
.venv/bin/python3 -m streamdeck_driver.daemon
```

**Windows:** either install Python yourself + `pip install -r requirements.txt`,
or check [Releases](https://github.com/CreAtiVe-Innovation-Studio/CVA-DeckControl/releases)
for a prebuilt `.exe` (no Python needed) — see "Prebuilt Windows .exe"
below for the current status. To build it YOURSELF: `tools\build_windows_exe.bat`
(needs Python on PATH) — the build path is verified live against real
hardware (both devices connect, icons/config load correctly, autostart works).

**Manual (any platform):**
1. `pip install -r requirements.txt`
2. Create your config from the templates:
   ```
   cp config/profiles.example.yaml config/profiles.yaml
   cp config/location.example.yaml config/location.yaml
   cp config/ha_secrets.example.yaml config/ha_secrets.yaml   # only if you use Home Assistant
   ```
   Fill in your own coordinates/credentials, adapt `profiles.yaml` to your
   needs (see SEITEN-LOGIK.md for every action/icon type, or just use the
   Settings GUI, see below).
3. `assets/` must sit as a sibling folder NEXT TO this repo folder (not
   inside it) — for generated icons/sounds/avatars, see `tools/generate_*.py`.
   Without your own assets, icon rendering falls back to procedurally drawn
   placeholders; the driver still runs fine.
4. Start: `python3 -m streamdeck_driver.daemon`

## Prebuilt Windows .exe

The complete source code here is free for non-commercial use (see
"License" below) — anyone can build their own `.exe` with
`tools\build_windows_exe.bat`, at no cost. A prebuilt `.exe` is planned to
be attached to a [Release](https://github.com/CreAtiVe-Innovation-Studio/CVA-DeckControl/releases)
— check there first; if none is attached yet, building your own is quick
and no strings attached either way. If you'd like to support the project
anyway, there's an optional
[Buy Me a Coffee](https://buymeacoffee.com/creativeinw) — entirely
voluntary, not tied to the download in any way.

The build result lands under `dist\CVA-DeckControl\`. `config\` (your own
`profiles.yaml`/`location.yaml`/`ha_secrets.yaml`, see step 2 above) needs
to be copied IN there, `assets\` next to it, as a sibling folder of
`CVA-DeckControl\` itself (mirrors the source layout exactly):
```
dist\
  assets\
  CVA-DeckControl\
    CVA-DeckControl.exe
    config\
```
The settings GUI is built into the `.exe` (no separate Python script
needed) — reachable via the `open_gui` key or directly at
`http://127.0.0.1:8420` once `CVA-DeckControl.exe` is running.

## Settings GUI

`python3 gui/server.py` — a local browser interface (no Flask/FastAPI,
pure Python standard library) for editing every key/page/profile instead
of hand-editing YAML, at `http://127.0.0.1:8420`. Can also be opened from a
physical key (action type `open_gui` — starts the GUI if it isn't running
yet and opens it in the browser).

Besides editing individual keys (free choice from every action/icon type),
the GUI also lets you **create, rename, and delete pages and profiles**
directly (+/✎/✕ icons next to every entry in the sidebar) — new DECK ONE
pages automatically get `page_next`/`page_previous` keys wired up, as long
as those key slots are free. The key editor also has "Copy from an
existing key" — a list of every key already configured anywhere in the
system, letting you reuse an existing key's action+icon as a starting
point instead of typing everything again.

## Building your own features

Three levels, depending on what you need:

1. **New key/page/profile** — entirely through the Settings GUI (see
   above) or by hand in `profiles.yaml`. No code, no restart risk: bad
   YAML values land as an `unmapped` key at worst, nothing crashes.
2. **Recombine an existing action/icon type** — e.g. your own hotkeys,
   programs, live metrics, Home Assistant entities. Full field reference
   with example YAML for every type: [SEITEN-LOGIK.md](SEITEN-LOGIK.md).
3. **A brand-new action type** (something that doesn't exist yet) — one
   function in `streamdeck_driver/actions.py` plus a branch in
   `dispatch()`, optionally a color in `icon_render.py`. Recipe with exact
   code locations: section 6 in [SEITEN-LOGIK.md](SEITEN-LOGIK.md).

[SEITEN-LOGIK.md](SEITEN-LOGIK.md) is deliberately written so both an AI
(Claude Code or similar) and a human can work with it directly — every
statement in it is verified against the actual code, nothing guessed. It's
currently German-only.

## Importing/sharing profiles

- Adopt a real Elgato/Streamplify profile (export file/folder):
  `python3 tools/import_deck_profile.py <path> --name <profilename>`
- Share your own profile with someone else:
  `python3 tools/export_profile.py <profilename>`
- Import a profile you received from someone else:
  `python3 tools/import_native_profile.py <file> --name <your-name>`

Unknown actions land as `needs_review`/`unmapped` instead of crashing or
being guessed at — clean them up afterward in the Settings GUI.

## Location map ("Where is?")

**Tested, but not extensively** — the rendering/zoom logic has been checked
against simulated tracker data, but not against a real long-running
tracking setup over days/weeks. If something looks off (wrong zoom, a pin
in the wrong spot, a crash), please open an issue.

A separate profile, built the same way as the radar (one big map image cut
into tiles), that shows where tracked people currently are, auto-zoomed so
everyone (and home) stays visible. It deliberately does **not** talk to
Apple Find My or WhatsApp directly — neither has a stable API to build
against (Find My only has unofficial, easily-broken wrappers; WhatsApp's
live location has no API at all). Instead it reads whatever Home Assistant
already exposes as `person`/`device_tracker` entities, so any source HA
supports works: the official HA Companion App's own GPS, Life360, or the
community [iCloud3](https://github.com/gcobb321/icloud3) integration for
Apple Find My.

**Setup:**
1. Get at least one `person.*` or `device_tracker.*` entity with GPS
   coordinates into Home Assistant (any integration works, see above).
2. `config/ha_secrets.yaml` must be filled in (see FAQ above) — same
   credentials used for the other Home Assistant features.
3. Switch to the `wo_ist` profile (add a `switch_profile` key somewhere,
   see [SEITEN-LOGIK.md](SEITEN-LOGIK.md) for the general pattern).

`person.*` entities are preferred (they carry a proper display name);
`device_tracker.*` is used as a fallback if no `person` has coordinates.
Without any tracker configured, the page shows a "no trackers found" card
instead of an empty or broken map. Press a pin's key to see the tracked
person's name/distance/direction from home; press again to hide it.

## Weather forecast

**Tested, but not extensively** — same caveat as the location map: checked
against live data, but not over an extended period. If something looks
off, please open an issue.

Two independent pieces, both via Home Assistant's weather forecast service
(no separate setup beyond `config/ha_secrets.yaml` and a `weather.*`
entity — the same one HA already uses for its own forecast card):

- **`weather_forecast` action type** — a simple per-key card (see
  [SEITEN-LOGIK.md](SEITEN-LOGIK.md) section 4.10) showing temperature and
  condition for any day/hour ahead you configure.
- **`wetter_vorhersage` profile** — a separate map page (own profile, not
  part of the radar) showing *only* RainViewer's precipitation forecast
  (the next ~30-60 minutes, in ~10-minute steps) with no live traffic/
  lightning on it. Press the bottom-right key to step through the
  available forecast frames. RainViewer doesn't guarantee forecast data is
  always available for every location — the page shows "no data" instead
  of an empty or broken map when that's the case.

## Platform support

| Platform | Status |
|---|---|
| Linux | Tested, in daily production use |
| Windows | Tested against real hardware (DECK ONE + Elgato Mini, hotkeys, volume, screenshot, sound, GUI, built `.exe`) |
| macOS | **Experimental, untested** — no Mac machine available |
| Elgato Original/MK.2/XL | **Experimental, untested** — only the Mini is verified |

If something breaks on one of the experimental platforms/devices: please
open an issue (platform/model + log output) instead of silently giving up
— without real hardware feedback these spots can't be hardened further.
Details/caveats live directly in the affected module
(`streamdeck_driver/platform_backend/macos.py`,
`streamdeck_driver/devices/elgato_generic.py`).

**Linux system tools used by some action types** (not installed by
`install.sh`, which only handles Python packages): `ydotool`/`ydotoold`
(hotkeys), `gnome-screenshot` + `zenity` (screenshot/popups, GNOME-specific),
`wpctl`/PipeWire (per-app volume). The screenshot action also copies to the
clipboard, and picks the right tool automatically for the running
session — `wl-copy` (package `wl-clipboard`) under Wayland, `xclip` under
X11 — so both need to actually be installed for whichever session type you
use; missing the right one logs a clear one-line warning instead of failing
silently.

## FAQ

**Do I need Home Assistant?** No — only for the optional
`ha_toggle`/`ha_cover`/`ha_sensor` action types and the lightning
detection in the radar. Without `config/ha_secrets.yaml` those features
simply don't come online, everything else is unaffected.

**Is my configuration/location public if I use this repo?** No —
`config/*.yaml` (your real keys, coordinates, credentials) is excluded via
`.gitignore`. Only `*.example.yaml` templates with placeholder values are
committed.

**I have no idea about Python — can I still build my own keys?** Yes, via
the Settings GUI (see above) or directly in `profiles.yaml` following the
examples in [SEITEN-LOGIK.md](SEITEN-LOGIK.md) — no code changes needed
for that.

**What if my device/OS is marked "experimental"?** The code for it exists
and was written to the best of my knowledge, but isn't hardened without
real hardware to check it against. An issue with a log/error helps more
than silently giving up.

## Contributing / reporting issues

Issues are welcome — most helpful are: which device/platform, what
exactly doesn't work, and log output if possible. For the parts marked
experimental (macOS, other Elgato models) especially, real feedback is
the only way to harden them.

There's an automated test suite (`pip install -r requirements.txt -r requirements-dev.txt && pytest`,
runs on every push via GitHub Actions) covering the pure logic — tile
geometry, zoom math, the timer state machine. It intentionally doesn't
(and can't) cover anything needing real hardware or a live Home Assistant
instance — see [tests/README.md](tests/README.md) for the exact scope.

## License

[PolyForm Noncommercial License 1.0.0](LICENSE) — free to use, modify, and
redistribute for **non-commercial purposes** (personal, hobby, learning,
research, charitable/public institutions). **Commercial use** (a company
using it, building it into your own product/offering) requires a separate
license — just get in touch: creative.info@gmx.de.

## Hands off

`streamdeck_driver/devices/base.py`, `deckone.py`, `elgato_mini.py`
(USB/HID protocol, reverse-engineered against real hardware — only change
for genuine hardware issues) as well as `manifest_parser.py`/
`action_translation.py` (the original one-time migration script; for your
own imports use `tools/import_deck_profile.py` instead).
