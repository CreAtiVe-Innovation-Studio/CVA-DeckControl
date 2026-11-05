"""Linux-Fensterverwaltung ueber die GNOME-Shell-Erweiterung 'Window Calls'
(window-calls@domandoman.xyz, D-Bus org.gnome.Shell.Extensions.Windows) - derselbe
Weg wie get_active_app_id() in linux.py und tools/mathlern_layout.py. Unter Wayland
gibt es keinen erweiterungsfreien Weg, fremde Fenster zu verschieben.

Entwickelt auf Windows, auf Linux (GNOME/X11, zwei Monitore, Window Calls) live
getestet: Liste, Platzieren, Fokus aus minimiert, Maximieren/Zurueck, Anordnen.
Hinweis: 'List' liefert keine Geometrie, die kommt per GetFrameRect/Details. Bekannte
Naeherungen:
* Arbeitsflaeche: GNOME meldet keine Panel-Hoehe ueber diesen Weg - es wird die
  volle Monitorflaeche genutzt. Unterkante/Oberkante des Panels ggf. ueber den
  Slot (y/h) einplanen.
* Monitore kommen aus 'xrandr --listmonitors' (laeuft auch unter XWayland)."""
from __future__ import annotations

import json
import logging
import re
import shlex
import subprocess

logger = logging.getLogger("streamdeck_driver.platform_backend.linux_wm")

BUS = "org.gnome.Shell"
PATH = "/org/gnome/Shell/Extensions/Windows"
IFACE = "org.gnome.Shell.Extensions.Windows"


def _call(method: str, signature: str = "", *args):
    cmd = ["busctl", "--user", "--json=short", "call", BUS, PATH, IFACE, method]
    if signature:
        cmd += [signature, *[str(a) for a in args]]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return json.loads(out.stdout) if out.stdout.strip() else None


def _string_result(result) -> str:
    try:
        return str(result["data"][0])
    except (TypeError, KeyError, IndexError):
        return ""


def parse_window_list(raw_json: str) -> list[dict]:
    """Window-Calls-'List'-Antwort -> neutrale Fensterliste (ohne Titel; der wird
    pro Fenster separat per GetTitle geholt, weil List ihn nicht in allen
    Versionen mitliefert)."""
    windows = []
    for w in json.loads(raw_json):
        windows.append({
            "id": str(w["id"]), "app_id": str(w.get("wm_class", "")).lower(), "title": str(w.get("title", "")),
            "x": int(w.get("x", 0)), "y": int(w.get("y", 0)),
            "w": int(w.get("width", 0)), "h": int(w.get("height", 0)),
            "minimized": bool(w.get("minimized", False)), "maximized": bool(w.get("maximized", False)),
            "focused": bool(w.get("focus", False)),
            "window_type": int(w.get("window_type", 0)),
        })
    return windows


def list_windows() -> list[dict]:
    try:
        envelope = _call("List")
        windows = parse_window_list(envelope["data"][0])
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        logger.warning("Fensterliste nicht lesbar - GNOME-Erweiterung 'Window Calls' fehlt/inaktiv? (%s)", exc)
        return []
    # Window Calls 'List' liefert (je nach Version) weder Geometrie noch
    # Zustand - live geprueft: nur id/title/wm_class/focus/window_type. Geometrie
    # kommt per GetFrameRect, minimiert/maximiert per Details. Nur normale
    # Fenster (window_type 0), keine Desktop-Icons/Panels.
    result = []
    for w in windows:
        if w["window_type"] != 0:
            continue
        try:
            rect = json.loads(_string_result(_call("GetFrameRect", "u", w["id"])))
            w.update(x=int(rect["x"]), y=int(rect["y"]), w=int(rect["width"]), h=int(rect["height"]))
        except (RuntimeError, OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            pass
        try:
            details = json.loads(_string_result(_call("Details", "u", w["id"])))
            w["minimized"] = bool(details.get("minimized", w["minimized"]))
            w["maximized"] = int(details.get("maximized", 0)) >= 3 or bool(details.get("fullscreen", False))
        except (RuntimeError, OSError, subprocess.SubprocessError, ValueError, TypeError):
            pass
        if not w["title"]:
            try:
                w["title"] = _string_result(_call("GetTitle", "u", w["id"]))
            except (RuntimeError, OSError, subprocess.SubprocessError, ValueError):
                pass
        if w["w"] > 0 and w["h"] > 0:
            result.append(w)
    return result


_XRANDR_RE = re.compile(r"^\s*\d+:\s+\+(?P<star>\*?)\S+\s+(?P<w>\d+)/\d+x(?P<h>\d+)/\d+\+(?P<x>-?\d+)\+(?P<y>-?\d+)")


def parse_xrandr_monitors(output: str) -> list[dict]:
    monitors = []
    for line in output.splitlines():
        m = _XRANDR_RE.match(line)
        if m:
            monitors.append({
                "x": int(m["x"]), "y": int(m["y"]), "w": int(m["w"]), "h": int(m["h"]),
                "primary": bool(m["star"]),
            })
    return monitors


def list_monitors() -> list[dict]:
    try:
        out = subprocess.run(["xrandr", "--listmonitors"], capture_output=True, text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Monitore nicht ermittelbar (xrandr): %s", exc)
        return []
    return parse_xrandr_monitors(out.stdout)


def move_window(window_id, x: int, y: int, w: int, h: int) -> None:
    try:
        _call("Unmaximize", "u", window_id)
    except (RuntimeError, OSError, subprocess.SubprocessError):
        pass  # war nicht maximiert - dann meldet die Erweiterung ggf. einen Fehler, harmlos
    try:
        _call("MoveResize", "uiiuu", window_id, x, y, w, h)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        logger.error("Fenster %s verschieben fehlgeschlagen: %s", window_id, exc)


def _simple(method: str, window_id) -> None:
    try:
        _call(method, "u", window_id)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        logger.error("%s fuer Fenster %s fehlgeschlagen: %s", method, window_id, exc)


def focus_window(window_id) -> None:
    _simple("Unminimize", window_id)
    _simple("Activate", window_id)


def maximize_window(window_id) -> None:
    _simple("Maximize", window_id)


def restore_window(window_id) -> None:
    _simple("Unmaximize", window_id)


def minimize_window(window_id) -> None:
    _simple("Minimize", window_id)


def start_minimized(command: str, cwd: str | None = None) -> None:
    """Hintergrunddienst ohne eigenes Terminalfenster starten (Linux braucht
    dafuer kein sichtbares Fenster); Ausgabe landet im Journal des Daemons."""
    if not command:
        return
    try:
        subprocess.Popen(
            shlex.split(command), cwd=cwd or None, start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        )
        logger.info("Dienst gestartet: %s", command)
    except OSError as exc:
        logger.error("Dienst konnte nicht gestartet werden (%s): %s", command, exc)
