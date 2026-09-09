#!/usr/bin/env python3
"""Oeffnet MathLern (192.168.255.222:3002) zweimal in getrennten Firefox-
Fenstern und positioniert sie praezise ueber die 'Window Calls'-GNOME-Shell-
Extension (D-Bus org.gnome.Shell.Extensions.Windows, Pfad
/org/gnome/Shell/Extensions/Windows):
  - linker Bildschirm (2560x1440 @ 0,0):            /mission (voll)
  - rechter Bildschirm (1920x1080 @ 2560,64), nur linke Haelfte: /admin/schueler

BUG GEFUNDEN 2026-09-08 (live gemeldet: statt des Layouts tippte der Nutzer
danach staendig Zahlenfolgen in andere Fenster): dieses Skript hatte einen
Fallback auf rohe ydotool-Tastencode-Injektion (Super+Pfeil etc.), falls der
D-Bus-Weg fehlschlug. Bei mehrfachem Tastendruck (z.B. weil es augenscheinlich
nicht reagierte) liefen mehrere Instanzen gleichzeitig, deren Press/Release-
Events sich ueber ydotoold ueberschneiden konnten - das kann eine Modifier-
Taste (Shift/Super) im Kernel als "gedrueckt" haengen lassen, wodurch normales
Tippen danach falsche/zusaetzliche Zeichen produziert. Der Fallback ist jetzt
komplett entfernt (die D-Bus-Erweiterung ist auf diesem System laengst aktiv
und verlässlich - kein Tastenkuerzel-Ersatz mehr noetig) UND ein Lockfile
verhindert, dass ein zweiter Tastendruck waehrend eines laufenden Durchgangs
ueberhaupt eine zweite Instanz startet."""
import fcntl
import json
import subprocess
import sys
import time
from pathlib import Path

BASE = "http://192.168.255.222:3002"
LEFT = (0, 0, 2560, 1440)
RIGHT_HALF = (2560, 64, 960, 1080)

BUS = "org.gnome.Shell"
PATH = "/org/gnome/Shell/Extensions/Windows"
IFACE = "org.gnome.Shell.Extensions.Windows"

LOCK_PATH = Path("/tmp/mathlern_layout.lock")


def dbus_call(method, signature="", *args):
    """busctl statt gdbus: gdbus call gibt sein Rueckgabetupel als
    pretty-gedrucktes GVariant-Textformat aus (z.B. das komplette JSON noch
    in einfache Anfuehrungszeichen samt Klammern eingebettet), das von Hand
    zuverlaessig zu parsen ist ueberraschend fehleranfaellig (live gefunden
    2026-09-09: 'Extra data'-JSONDecodeError, nachdem das urspruengliche
    manuelle Klammern/Anfuehrungszeichen-Stripping bei echten Auftrufen doch
    nicht immer griff). busctl --json=short liefert stattdessen sauberes,
    direkt geparstes JSON - dieselbe Loesung wie in platform_backend/
    linux.py::get_active_app_id() fuer genau dasselbe Problem."""
    cmd = ["busctl", "--user", "--json=short", "call", BUS, PATH, IFACE, method]
    if signature:
        cmd.append(signature)
        cmd += [str(a) for a in args]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    # Methoden ohne Rueckgabewert (z.B. MoveResize/Close) liefern LEERES
    # stdout - json.loads("") wuerde das faelschlich als Fehler werten.
    return json.loads(out.stdout) if out.stdout.strip() else None


def list_windows():
    result = dbus_call("List")
    return json.loads(result["data"][0])


def wait_for_new_firefox_window(before_ids, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for w in list_windows():
            if "firefox" in w.get("wm_class", "").lower() and w.get("id") not in before_ids:
                return w["id"]
        time.sleep(0.3)
    raise TimeoutError("Kein neues Firefox-Fenster gefunden")


def place_via_dbus():
    ids_before = {w["id"] for w in list_windows()}
    subprocess.Popen(["firefox", "--new-window", f"{BASE}/mission"])
    win1 = wait_for_new_firefox_window(ids_before)
    dbus_call("MoveResize", "uiiuu", win1, *LEFT)

    ids_before = {w["id"] for w in list_windows()}
    subprocess.Popen(["firefox", "--new-window", f"{BASE}/admin/schueler"])
    win2 = wait_for_new_firefox_window(ids_before)
    dbus_call("MoveResize", "uiiuu", win2, *RIGHT_HALF)


def _notify_failure(exc: Exception) -> None:
    msg = f"MathLern-Layout fehlgeschlagen: {exc}"
    print(msg, file=sys.stderr)
    try:
        subprocess.Popen(["notify-send", "MathLern-Layout", msg])
    except FileNotFoundError:
        pass  # notify-send optional, Fehler steht schon auf stderr/im Log


def main():
    # Non-blocking Lock: laeuft schon ein Durchgang (z.B. weil die Taste kurz
    # hintereinander mehrfach gedrueckt wurde), bricht dieser hier sofort ab,
    # statt eine zweite, ueberlappende Instanz zu starten.
    lock_file = LOCK_PATH.open("w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("MathLern-Layout laeuft schon - zweiter Tastendruck ignoriert.")
        return
    try:
        place_via_dbus()
    except Exception as exc:
        _notify_failure(exc)
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


if __name__ == "__main__":
    main()
