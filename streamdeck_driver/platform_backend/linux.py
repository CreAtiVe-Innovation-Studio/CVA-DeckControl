"""Linux-Backend - identische Implementierung wie vor dem Portabilitaets-
Umbau, nur aus actions.py/process_monitor.py/timer_engine.py hierher verschoben.
Getestet gegen echte Hardware (siehe SEITEN-LOGIK.md / CLAUDE.md-Historie)."""
from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from .. import vkeycode_map

logger = logging.getLogger("streamdeck_driver.platform_backend.linux")

# BUG GEFUNDEN 2026-09-09/10 (live gemeldet, zweimal): als systemd-User-Dienst
# gestartete Prozesse bekommen DISPLAY/XAUTHORITY oft NICHT verlaesslich in
# ihre Umgebung importiert - haengt von der Reihenfolge ab, in der die
# Desktop-Sitzung diese Variablen in den systemd-User-Manager importiert
# (dbus-update-activation-environment/systemctl --user import-environment),
# relativ dazu wann dieser Dienst startet. `PartOf=graphical-session.target`
# in der .service-Datei loest das NICHT zuverlaessig (nur Stop-Propagation,
# kein garantiertes Nachimportieren). Jeder ueber subprocess.Popen() ohne
# eigenes env= gestartete GUI-Kindprozess (Firefox, gnome-screenshot, eigene
# Skripte wie tools/mathlern_layout.py) erbt fehlendes DISPLAY und kann dann
# gar kein X11-Fenster oeffnen. Live verifiziert: lokale X11-Verbindungen
# brauchen auf diesem System KEIN XAUTHORITY (nur DISPLAY=:0), daher reicht
# dieser eine Fallback. os.environ.setdefault() greift nur, wenn DISPLAY
# WIRKLICH fehlt - eine echte Wayland-Session wird dadurch nicht verfaelscht.
os.environ.setdefault("DISPLAY", ":0")

# BUG GEFUNDEN 2026-09-17 (live gemeldet: "Teams oeffnet immer noch Chromium"
# trotz korrekter profiles.yaml/mimeapps.list): derselbe fehlende-Umgebung-
# Mechanismus wie oben bei DISPLAY, hier fuer XDG_CURRENT_DESKTOP - fehlt das,
# waehlt xdg-open/xdg-mime den falschen Standard-Browser (live reproduziert:
# mit exakt der Umgebung des laufenden Dienst-Prozesses, aber zusaetzlich
# XDG_CURRENT_DESKTOP gesetzt, kippt 'xdg-mime query default
# x-scheme-handler/https' von chromium_chromium.desktop auf
# firefox_firefox.desktop - einzeln unter allen abweichenden XDG_*-Variablen
# als die entscheidende identifiziert). Betrifft jede Aktion, die xdg-open
# fuer eine Website nutzt (Action-Typ 'website'), nicht nur diese eine Taste.
os.environ.setdefault("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")


def send_hotkey(vkeycode: int, ctrl: bool, shift: bool, alt: bool) -> None:
    codes = vkeycode_map.resolve(vkeycode, ctrl, shift, alt)
    if not codes:
        logger.warning("Hotkey vkeycode=%s: keine bekannte Linux-Zuordnung, ignoriert", vkeycode)
        return
    seq = [f"{c}:1" for c in codes] + [f"{codes[-1]}:0"] + [f"{c}:0" for c in reversed(codes[:-1])]
    try:
        subprocess.run(["ydotool", "key", *seq], check=True, timeout=5)
        logger.info("Hotkey ausgefuehrt: vkeycode=%s -> %s", vkeycode, codes)
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.error("Hotkey fehlgeschlagen (vkeycode=%s): %s", vkeycode, exc)


def open_command(cmd: str) -> None:
    if not cmd:
        return
    try:
        subprocess.Popen(shlex.split(cmd))
        logger.info("Programm gestartet: %s", cmd)
    except OSError as exc:
        logger.error("Programm konnte nicht gestartet werden (%s): %s", cmd, exc)


def open_url(url: str, new_window: bool = False) -> None:
    if not url:
        return
    # new_window=True startet direkt Firefox mit --new-window statt ueber
    # xdg-open: xdg-open landet beim konfigurierten Standardbrowser als
    # neuer Tab im bereits laufenden Fenster (Firefox-Snap laesst nur eine
    # Instanz zu) - fuer Keys wie Teams, die ein eigenes, frei verschieb-
    # bares Fenster brauchen, reicht das nicht.
    cmd = ["firefox", "--new-window", url] if new_window else ["xdg-open", url]
    try:
        subprocess.Popen(cmd)
        logger.info("Website geoeffnet (new_window=%s): %s", new_window, url)
    except OSError as exc:
        logger.error("Website konnte nicht geoeffnet werden (%s): %s", url, exc)


def _is_wayland_session() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get("XDG_SESSION_TYPE") == "wayland"


def take_screenshot_interactive() -> None:
    """Siehe actions.py-Historie: ydotool-PrintScreen loest unter GNOME/
    Wayland keinen Screenshot aus, direkter D-Bus-Aufruf scheitert an
    Portal-Berechtigungen -> 'gnome-screenshot' CLI direkt.

    BUG GEFUNDEN 2026-09-06 (live gemeldet: nach Wechsel von einer Wayland-
    auf eine X11-Session "klappt alles nicht mehr") - das Clipboard-Werkzeug
    war fest auf 'wl-copy' verdrahtet, das unter X11 nur lautlos mit
    'Failed to connect to a Wayland server' auf stderr fehlschlaegt (live
    reproduziert). Erkennung jetzt zur LAUFZEIT ueber WAYLAND_DISPLAY/
    XDG_SESSION_TYPE (nicht einmalig beim Import), damit ein Wechsel
    zwischen X11- und Wayland-Login ohne Neuinstallation funktioniert -
    xclip fuer X11, wl-copy fuer Wayland. Ausserdem: die alte '&&'-Kette
    hat bei einem fehlschlagenden Copy-Schritt auch das 'rm -f' uebersprungen,
    also verwaiste Temp-Screenshots in /tmp hinterlassen - jetzt mit ';'
    verkettet, Aufraeumen passiert immer."""
    wayland = _is_wayland_session()
    copy_tool = "wl-copy" if wayland else "xclip"
    if shutil.which(copy_tool) is None:
        logger.error(
            "Screenshot-Clipboard: '%s' nicht installiert (noetig fuer diese %s-Session) - "
            "Bild wird trotzdem aufgenommen, landet aber nicht im Clipboard. Installieren: %s",
            copy_tool, "Wayland" if wayland else "X11",
            "sudo apt install wl-clipboard" if wayland else "sudo apt install xclip",
        )
    copy_cmd = 'wl-copy < "$f"' if wayland else 'xclip -selection clipboard -t image/png < "$f"'
    try:
        subprocess.Popen([
            "bash", "-c",
            f'f=$(mktemp --suffix=.png) && gnome-screenshot --area --file="$f"; {copy_cmd}; rm -f "$f"',
        ])
        logger.info("Screenshot-Bereichsauswahl gestartet (Datei + %s)", copy_tool)
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.error("Screenshot fehlgeschlagen: %s", exc)


def set_app_volume(app_name: str, direction: str, step_percent: int = 5) -> None:
    """App-spezifische Lautstaerke ueber wpctl (PipeWire) - sucht im
    'Streams'-Abschnitt von 'wpctl status' nach einem laufenden Audio-Stream,
    dessen Name app_name enthaelt, kein Fehler falls die App keinen Ton spielt."""
    try:
        result = subprocess.run(["wpctl", "status"], capture_output=True, text=True, check=True, timeout=5)
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.error("App-Lautstaerke: wpctl status fehlgeschlagen: %s", exc)
        return

    lines = result.stdout.splitlines()
    try:
        # .strip() entfernt nur Whitespace, nicht das Box-Zeichnungs-Praefix
        # ("└─ Streams:"), das wpctl vor den Abschnittsnamen setzt - daher
        # Teilstring-Suche statt startswith().
        start = next(i for i, l in enumerate(lines) if "streams:" in l.strip().lower())
    except StopIteration:
        logger.warning("App-Lautstaerke: kein 'Streams'-Abschnitt in wpctl-Ausgabe gefunden")
        return

    # Aktuelle wpctl-Versionen zeigen bei "Streams" kein "[vol: ...]" mehr
    # inline an (nur Sinks/Sources haben das) - eine Top-Level-Stream-Zeile
    # ("118. Firefox") ist stattdessen daran zu erkennen, dass sie (anders als
    # ihre eingerueckten Port-Unterzeilen wie "119. output_FL > ...") keinen
    # Verbindungspfeil "> " enthaelt.
    stream_line_re = re.compile(r"^\s*[│├└\-\s]*(\d+)\.\s*(.+?)\s*$")
    matched_ids: list[str] = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        stripped_lower = stripped.lower()
        if any(h in stripped_lower for h in ("sinks:", "sources:", "filters:", "devices:")) or (
            stripped == "" and matched_ids
        ):
            break
        if ">" in line:
            continue  # Port-/Verbindungs-Unterzeile, kein eigener Stream
        m = stream_line_re.match(line)
        if m and app_name.lower() in m.group(2).lower():
            matched_ids.append(m.group(1))

    if not matched_ids:
        logger.info("App-Lautstaerke: kein aktiver Audio-Stream fuer '%s' gefunden - keine Aktion", app_name)
        return

    sign = "+" if direction == "up" else "-"
    for sid in matched_ids:
        try:
            subprocess.run(["wpctl", "set-volume", sid, f"{step_percent}%{sign}"], check=True, timeout=5)
            logger.info("App-Lautstaerke: '%s' (Stream-ID %s) %s%% %s", app_name, sid, step_percent, direction)
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            logger.error("App-Lautstaerke: wpctl set-volume fehlgeschlagen (ID %s): %s", sid, exc)


def get_app_volume(app_name: str) -> int | None:
    """Aktuelle Lautstaerke (0-100) des ersten gefundenen Audio-Streams von
    app_name, oder None falls kein Stream laeuft / Abfrage fehlschlug. Gleiche
    Streams-Suche wie set_app_volume(), dann 'wpctl get-volume <id>' statt
    'set-volume' - dessen Ausgabe sieht z.B. so aus: 'Volume: 0.45' oder
    'Volume: 0.45 [MUTED]'."""
    try:
        result = subprocess.run(["wpctl", "status"], capture_output=True, text=True, check=True, timeout=5)
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.error("App-Lautstaerke: wpctl status fehlgeschlagen: %s", exc)
        return None

    lines = result.stdout.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if "streams:" in l.strip().lower())
    except StopIteration:
        return None

    stream_line_re = re.compile(r"^\s*[│├└\-\s]*(\d+)\.\s*(.+?)\s*$")
    matched_id: str | None = None
    for line in lines[start + 1:]:
        stripped = line.strip()
        stripped_lower = stripped.lower()
        if any(h in stripped_lower for h in ("sinks:", "sources:", "filters:", "devices:")) or (
            stripped == "" and matched_id
        ):
            break
        if ">" in line:
            continue
        m = stream_line_re.match(line)
        if m and app_name.lower() in m.group(2).lower():
            matched_id = m.group(1)
            break

    if matched_id is None:
        return None

    try:
        vol_result = subprocess.run(
            ["wpctl", "get-volume", matched_id], capture_output=True, text=True, check=True, timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.error("App-Lautstaerke: wpctl get-volume fehlgeschlagen (ID %s): %s", matched_id, exc)
        return None

    m = re.search(r"([\d.]+)", vol_result.stdout)
    if not m:
        return None
    return round(float(m.group(1)) * 100)


_AUDIO_PLAYERS = ("pw-play", "aplay", "ffplay")


def play_sound(path: Path) -> None:
    for player in _AUDIO_PLAYERS:
        args = {
            "pw-play": [player, str(path)],
            "aplay": [player, "-q", str(path)],
            "ffplay": [player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
        }[player]
        try:
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except FileNotFoundError:
            continue
    logger.warning("Kein Audio-Player (pw-play/aplay/ffplay) gefunden - Ton uebersprungen")


def show_message_popup(title: str, text: str) -> None:
    try:
        subprocess.Popen(["zenity", "--info", f"--title={title}", f"--text={text}", "--width=320"])
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.error("zenity-Anzeige fehlgeschlagen: %s", exc)


_window_calls_warned = False


def get_active_app_id() -> str | None:
    """Liefert die wm_class des aktuell fokussierten Fensters (klein-
    geschrieben), z.B. 'firefox' oder 'code' - fuer automatischen Profil-
    wechsel je nach aktiver App (window_watch.py). Braucht die GNOME-Shell-
    Erweiterung 'Window Calls' (window-calls@domandoman.xyz,
    https://github.com/ickyicky/window-calls): unter Wayland gibt es sonst
    KEINEN verlaesslichen, erweiterungsfreien Weg an das fokussierte Fenster
    heranzukommen (die alten X11-Tools xdotool/wmctrl funktionieren unter
    Wayland nicht, und GNOME Shells D-Bus-Eval() ist seit GNOME 41 per
    Default deaktiviert - siehe Systemd/systemctl-Recherche, live gegen die
    eigene GNOME/Wayland-Session verifiziert). Auf KDE/Sway/anderen
    Compositors oder ohne die Erweiterung liefert das hier None (einmalig
    geloggt) - dann bleibt die automatische Profilumschaltung einfach aus,
    kein Fehler.

    Bewusst NUR wm_class, NIE der Fenstertitel: der Titel kann sensible
    Inhalte enthalten (Suchbegriffe, Chat-Vorschauen), wm_class ist nur die
    App-Kennung."""
    global _window_calls_warned
    try:
        result = subprocess.run(
            [
                "busctl", "--user", "--json=short", "call",
                "org.gnome.Shell", "/org/gnome/Shell/Extensions/Windows",
                "org.gnome.Shell.Extensions.Windows", "List",
            ],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode != 0:
            if not _window_calls_warned:
                logger.warning(
                    "Aktive App nicht ermittelbar - GNOME-Erweiterung 'Window Calls' fehlt/deaktiviert "
                    "oder kein GNOME (%s). Automatischer Profilwechsel bleibt aus.",
                    result.stderr.strip(),
                )
                _window_calls_warned = True
            return None
        envelope = json.loads(result.stdout)
        windows = json.loads(envelope["data"][0])
        focused = next((w for w in windows if w.get("focus")), None)
        return focused["wm_class"].lower() if focused else None
    except (subprocess.SubprocessError, FileNotFoundError, ValueError, KeyError) as exc:
        if not _window_calls_warned:
            logger.warning("Aktive App nicht ermittelbar: %s. Automatischer Profilwechsel bleibt aus.", exc)
            _window_calls_warned = True
        return None
