#!/usr/bin/env python3
"""Nimmt die aktuell offenen Fenster als Layout fuer profiles.yaml auf.

Einmal alles so hinschieben, wie es spaeter automatisch aussehen soll, dann:

    python tools/capture_layout.py --name unterricht > layout.yaml

Das Ergebnis ist ein fertiger 'window_layouts'-Block (siehe SEITEN-LOGIK.md
Abschnitt 4.14) mit pro Fenster:
  * Prozessname (match.process),
  * Position als Anteil der Arbeitsflaeche des jeweiligen Monitors (slot) -
    damit funktioniert dasselbe Layout auch auf anderen Aufloesungen,
  * 'order', wenn mehrere Fenster derselben App offen sind (Index von links
    nach rechts),
  * Startbefehl-Vorschlag ('launch'), soweit der Prozess ihn verraet.

Fenstertitel werden NICHT geschrieben (sie enthalten oft private Inhalte wie
Seitentitel oder Dateinamen); mit --with-titles als Kommentar anhaengbar, falls
man bewusst darueber unterscheiden will. Danach von Hand pruefen: welche Apps
'start: true' (vom Start-Knopf geoeffnet) und welche 'auto_place: true'
(nur positioniert, wenn man sie selbst oeffnet) sein sollen."""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from streamdeck_driver import platform_backend  # noqa: E402
from streamdeck_driver.windowing.geometry import monitors_from_dicts, rect_to_slot, windows_from_dicts  # noqa: E402

# Prozesse, die nie Teil eines Layouts sein sollen (Shell, eigene Konsole, dieser Treiber)
DEFAULT_IGNORE = {"textinputhost", "searchhost", "startmenuexperiencehost", "streamdeckdriver"}


def _launch_hint(pid: int | None) -> str:
    if not pid:
        return ""
    try:
        import psutil
        return psutil.Process(pid).exe()
    except Exception:
        return ""


def _yaml_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_yaml(name: str, with_titles: bool, ignore: set[str]) -> str:
    raw_windows = platform_backend.list_windows()
    pid_of = {str(w["id"]): w.get("pid") for w in raw_windows}
    monitors = monitors_from_dicts(platform_backend.list_monitors())
    windows = [w for w in windows_from_dicts(raw_windows) if not w.minimized and w.app_id not in ignore]
    if not monitors or not windows:
        raise SystemExit("Keine Monitore/Fenster erkannt - laeuft das Backend auf dieser Plattform?")

    by_app: dict[str, list] = defaultdict(list)
    for w in windows:
        by_app[w.app_id].append(w)

    lines = [
        "window_layouts:",
        f"  {name}:",
        "    apps:",
    ]
    for app_id, group in sorted(by_app.items()):
        group.sort(key=lambda w: (w.rect.x, w.rect.y))
        for order, w in enumerate(group):
            slot = rect_to_slot(w.rect, monitors)
            if slot is None:
                continue
            key = app_id if order == 0 else f"{app_id}_{order + 1}"
            lines.append(f"      {key}:")
            lines.append("        match:")
            lines.append(f"          process: [{app_id}]")
            if len(group) > 1:
                lines.append(f"          order: {order}    # {order + 1}. von {len(group)} Fenstern, von links nach rechts")
            if with_titles:
                lines.append(f"          # Titel zum Zeitpunkt der Aufnahme: {w.title!r}")
            lines.append(
                "        slot: {monitor: %d, x: %s, y: %s, w: %s, h: %s}"
                % (slot["monitor"], slot["x"], slot["y"], slot["w"], slot["h"])
            )
            exe = _launch_hint(pid_of.get(w.id))
            if exe and order == 0:
                lines.append(f"        launch: {_yaml_str(exe)}")
            elif order > 0:
                lines.append(f"        launch_with: {app_id}    # wird mit dem ersten Fenster geoeffnet")
            else:
                lines.append("        # launch: ''     # Startbefehl eintragen, falls der Start-Knopf die App oeffnen soll")
            lines.append("        start: false        # true = vom Start-Knopf geoeffnet")
            lines.append("        auto_place: false   # true = positioniert, sobald man die App selbst oeffnet")
    lines.append("")
    lines.append("# Monitore bei der Aufnahme (von links nach rechts):")
    for m in monitors:
        lines.append(
            f"#   {m.index}: {m.bounds.w}x{m.bounds.h} @ {m.bounds.x},{m.bounds.y}"
            f"{'  (primaer)' if m.primary else ''}, Arbeitsflaeche {m.work.w}x{m.work.h}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", default="unterricht", help="Name des Layouts in profiles.yaml")
    parser.add_argument("--with-titles", action="store_true", help="Fenstertitel als Kommentar anhaengen (kann Privates enthalten)")
    parser.add_argument("--ignore", default="", help="Zusaetzliche Prozessnamen, kommagetrennt, die uebersprungen werden")
    args = parser.parse_args()
    ignore = DEFAULT_IGNORE | {p.strip().lower() for p in args.ignore.split(",") if p.strip()}
    sys.stdout.write(build_yaml(args.name, args.with_titles, ignore))


if __name__ == "__main__":
    main()
