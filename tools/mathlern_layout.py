#!/usr/bin/env python3
"""Oeffnet MathLern (192.168.255.222:3002) zweimal in getrennten Firefox-
Fenstern und positioniert sie praezise ueber die 'Window Calls'-GNOME-Shell-
Extension (D-Bus org.gnome.Shell.Extensions.Windows, Pfad
/org/gnome/Shell/Extensions/Windows):
  - linker Bildschirm (2560x1440 @ 0,0):            /mission (voll)
  - rechter Bildschirm (1920x1080 @ 2560,64), nur linke Haelfte: /admin/schueler

Faellt automatisch auf die alte Tastenkuerzel-Simulation zurueck (Super+Pfeil
via ydotool), falls die Extension noch nicht aktiv ist (braucht nach der
Installation einmalig Ab-/Anmelden, da GNOME unter Wayland Extensions nicht
live nachladen kann).
"""
import json
import subprocess
import time

BASE = "http://192.168.255.222:3002"
LEFT = (0, 0, 2560, 1440)
RIGHT_HALF = (2560, 64, 960, 1080)

BUS = "org.gnome.Shell"
PATH = "/org/gnome/Shell/Extensions/Windows"
IFACE = "org.gnome.Shell.Extensions.Windows"


def dbus_call(method, *args):
    cmd = ["gdbus", "call", "--session", "--dest", BUS, "--object-path", PATH,
           "--method", f"{IFACE}.{method}"] + [str(a) for a in args]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return out.stdout.strip()


def list_windows():
    raw = dbus_call("List")
    # gdbus gibt sowas wie ('[{"wm_class": ...}]',) zurueck
    json_str = raw.strip()
    if json_str.startswith("("):
        json_str = json_str[1:]
    if json_str.endswith(",)"):
        json_str = json_str[:-2]
    json_str = json_str.strip().strip("'")
    json_str = json_str.encode().decode("unicode_escape")
    return json.loads(json_str)


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
    dbus_call("MoveResize", win1, *LEFT)

    ids_before = {w["id"] for w in list_windows()}
    subprocess.Popen(["firefox", "--new-window", f"{BASE}/admin/schueler"])
    win2 = wait_for_new_firefox_window(ids_before)
    dbus_call("MoveResize", win2, *RIGHT_HALF)


def place_via_hotkeys_fallback():
    def key(*codes):
        subprocess.run(["ydotool", "key", *codes])

    subprocess.Popen(["firefox", "--new-window", f"{BASE}/mission"])
    time.sleep(3)
    key("125:1", "42:1", "105:1", "105:0", "42:0", "125:0")  # Super+Shift+Left
    time.sleep(0.3)
    key("125:1", "103:1", "103:0", "125:0")  # Super+Up (maximize)

    subprocess.Popen(["firefox", "--new-window", f"{BASE}/admin/schueler"])
    time.sleep(3)
    key("125:1", "42:1", "106:1", "106:0", "42:0", "125:0")  # Super+Shift+Right
    time.sleep(0.3)
    key("125:1", "105:1", "105:0", "125:0")  # Super+Left (linke Haelfte)


def main():
    try:
        dbus_call("List")  # Verfuegbarkeitscheck
        place_via_dbus()
    except Exception as exc:
        print(f"Window Calls nicht verfuegbar ({exc}), Fallback auf Tastenkuerzel")
        place_via_hotkeys_fallback()


if __name__ == "__main__":
    main()
