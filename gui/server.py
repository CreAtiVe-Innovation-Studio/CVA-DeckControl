#!/usr/bin/env python3
"""Lokale Settings-GUI fuer den Stream-Deck-Treiber: ein einziger stdlib-
HTTP-Server (kein Flask/FastAPI noetig - haelt die Abhaengigkeiten minimal,
was auch dem geplanten Cross-Platform-Umbau entgegenkommt) der profiles.yaml
als JSON serviert/annimmt und eine Single-Page-Oberflaeche ausliefert.

Ausfuehren: python3 gui/server.py [--port 8420]
Oeffnet den Browser automatisch auf http://127.0.0.1:8420/

Kann auch eingebettet im Daemon-Prozess laufen (siehe start_in_thread() unten,
genutzt vom 'open_gui'-Aktionstyp in streamdeck_driver/actions.py) - deshalb
bewusst KEIN Import von streamdeck_driver hier oben (haette bei
`python3 gui/server.py` als eigenstaendigem Skript keinen Projekt-Root auf
sys.path), stattdessen ein eigener kleiner sys.frozen-Check lokal.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psutil
import requests
import yaml


def _app_root() -> Path:
    """Wie streamdeck_driver.paths.app_root(), aber lokal dupliziert (siehe
    Modul-Docstring oben) - in einer per PyInstaller gebauten .exe zeigt
    __file__ auf einen temporaeren Extraktionsordner, nicht auf den echten
    Installationsort, dort muss vom Ordner der .exe selbst ausgegangen werden."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent  # .../linux-driver/


PROJECT_ROOT = _app_root().parent  # .../streamdeck/ (assets/ liegt hier als Geschwister)
DRIVER_ROOT = _app_root()  # .../streamdeck/linux-driver/
CONFIG_PATH = DRIVER_ROOT / "config" / "profiles.yaml"
BACKUP_DIR = DRIVER_ROOT / "config" / "backups"
SOUND_DIR = PROJECT_ROOT / "assets" / "sounds"
DEFAULT_SOUND_FILE = (SOUND_DIR / "timer_default.wav").resolve()
CUSTOM_SOUND_DIR = SOUND_DIR / "custom"
# gui/static/index.html ist gebuendelte App-Ressource (kein Nutzer-Datenordner)
# - in der .exe liegt sie im PyInstaller-Bundle (sys._MEIPASS), nicht neben der
# .exe. Siehe 'datas' in tools/build_windows_exe.spec fuer das Mapping.
STATIC_DIR = (
    Path(getattr(sys, "_MEIPASS", "")) / "gui" / "static"
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent / "static"
)

SERVICE_NAME = "streamdeck-driver.service"
UPDATE_CHECK_REPO = "CreAtiVe-Innovation-Studio/CVA-DeckControl"


def _read_current_version() -> str:
    """Liest __version__ aus streamdeck_driver/__init__.py per Text-Regex,
    OHNE das Paket zu importieren - gui/server.py muss auch als
    eigenstaendiges Skript per `python3 gui/server.py` laufen (siehe
    Moduldocstring oben), ein direkter Import wuerde das brechen."""
    try:
        text = (DRIVER_ROOT / "streamdeck_driver" / "__init__.py").read_text(encoding="utf-8")
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
        return match.group(1) if match else "0.0.0"
    except OSError:
        return "0.0.0"


def _update_check() -> dict:
    """Wie streamdeck_driver/update_check.py, aber unabhaengig aufrufbar -
    wenn die GUI EINGEBETTET im Daemon laeuft (siehe gui/server.py's
    start_in_thread(), genutzt vom 'open_gui'-Aktionstyp), ist
    streamdeck_driver bereits importiert und wir nutzen dessen bereits
    berechnetes (gecachtes) Ergebnis statt eines redundanten API-Calls -
    beim eigenstaendigen `python3 gui/server.py` (kein Paket-Kontext, siehe
    _read_current_version()) faellt das auf einen eigenen, unabhaengigen
    Check zurueck."""
    try:
        from streamdeck_driver import update_check as _uc
        result = _uc.get_last_result()
        return result if result.get("checked") else _uc.check_now()
    except ImportError:
        pass

    current = _read_current_version()
    result = {"checked": True, "current": current, "latest": None, "update_available": False, "url": None}
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{UPDATE_CHECK_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json"}, timeout=5,
        )
        if resp.status_code != 404:
            resp.raise_for_status()
            data = resp.json()
            latest = data.get("tag_name", "")
            result["latest"], result["url"] = latest, data.get("html_url")
            cur_nums = tuple(int(x) for x in re.findall(r"\d+", current)) or (0,)
            latest_nums = tuple(int(x) for x in re.findall(r"\d+", latest)) or (0,)
            result["update_available"] = latest_nums > cur_nums
    except requests.RequestException:
        pass
    return result


def _restart_daemon_windows() -> None:
    """Windows-Aequivalent zu 'systemctl --user restart' (NEU 2026-09-03,
    Windows-Testsession): kein systemd unter Windows, stattdessen laufende
    Daemon-Prozesse per psutil finden+beenden und neu starten (siehe
    Z:/STREAMDECK_WINDOWS_TESTING.md).

    AKTUALISIERT 2026-09-03 (gleicher Tag, spaeter): Autostart laeuft jetzt
    ueber die per PyInstaller gebaute CVA-DeckControl.exe statt ueber
    start-daemon-windows.bat + venv (siehe README "Fertige Windows-.exe") -
    Prozess-Erkennung und Neustart-Pfad decken jetzt BEIDE Faelle ab, damit
    der Button unabhaengig davon funktioniert, welche Variante gerade laeuft."""
    exe_path = DRIVER_ROOT / "dist" / "CVA-DeckControl" / "CVA-DeckControl.exe"
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info["name"] or "").lower()
            cmdline = proc.info["cmdline"] or []
            if name == "cva-deckcontrol.exe" or any("streamdeck_driver.daemon" in part for part in cmdline):
                proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if exe_path.exists():
        subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent), creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        bat_path = DRIVER_ROOT / "start-daemon-windows.bat"
        subprocess.Popen(
            ["cmd", "/c", str(bat_path)],
            cwd=str(DRIVER_ROOT),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

# -- Aktionstyp-Schema: treibt das dynamische Formular im Frontend --------
ACTION_SCHEMA: dict[str, list[dict]] = {
    "hotkey": [
        {"name": "vkeycode", "label": "Vkeycode", "type": "text"},
        {"name": "ctrl", "label": "Strg", "type": "bool"},
        {"name": "shift", "label": "Umschalt", "type": "bool"},
        {"name": "alt", "label": "Alt", "type": "bool"},
    ],
    "open": [{"name": "linux_command", "label": "Befehl", "type": "text"}],
    "open_sequence": [{"name": "steps", "label": "Befehle (eine Zeile je Schritt)", "type": "steps"}],
    "website": [{"name": "url", "label": "URL", "type": "text"}],
    "app_volume": [
        {"name": "app_name", "label": "App-Name", "type": "text"},
        {"name": "direction", "label": "Richtung", "type": "select", "options": ["up", "down"]},
    ],
    "live_stat": [
        {
            "name": "metric", "label": "Metrik", "type": "select",
            "options": ["cpu", "cpu_temp", "ram", "ram_gb", "gpu_load", "gpu_vram", "gpu_temp", "disk"],
        },
    ],
    "ha_sensor": [{"name": "entity_id", "label": "Entity-ID", "type": "text"}],
    "ha_toggle": [{"name": "entity_id", "label": "Entity-ID", "type": "text"}],
    "ha_cover": [
        {"name": "entity_id", "label": "Entity-ID", "type": "text"},
        {"name": "direction", "label": "Richtung", "type": "select", "options": ["up", "down"]},
    ],
    "page_next": [],
    "page_previous": [],
    "switch_profile": [{"name": "profile", "label": "Profil", "type": "profile_select"}],
    "timer": [
        {"name": "duration_min", "label": "Dauer (Minuten)", "type": "number"},
        {"name": "sound", "label": "Ton", "type": "sound"},
        {"name": "style", "label": "Stil", "type": "select", "options": ["digital", "analog"]},
    ],
    "live_view_toggle": [],
    "open_gui": [{"name": "port", "label": "Port (leer = 8420)", "type": "number"}],
    "unmapped": [{"name": "note", "label": "Hinweis", "type": "readonly"}],
}
ICON_SCHEMA: dict[str, list[dict]] = {
    "generated": [],
    "asset": [{"name": "path", "label": "Datei-Pfad", "type": "text"}],
    "app_icon": [{"name": "path", "label": "Datei-Pfad", "type": "text"}],
}


def _load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8-sig") as f:
        return yaml.safe_load(f)


def _int_keys(obj):
    """YAML/JSON-Hin-und-Her: 'keys'-Dicts haben in profiles.yaml echte
    Ganzzahl-Schluessel (0,1,2,...), JSON kennt aber nur String-Schluessel -
    beim Zurueckschreiben muessen betroffene Dicts wieder auf int-Keys."""
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            nv = _int_keys(v)
            nk = int(k) if isinstance(k, str) and k.lstrip("-").isdigit() and k != "" else k
            new[nk] = nv
        return new
    if isinstance(obj, list):
        return [_int_keys(v) for v in obj]
    return obj


def _save_config(data: dict) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(CONFIG_PATH, BACKUP_DIR / f"profiles.{stamp}.yaml")
    cleaned = _int_keys(data)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cleaned, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def _profile_names(config: dict) -> list[str]:
    return list(config.get("deckone", {}).get("profiles", {}).keys())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # weniger Konsolen-Rauschen
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str):
        if not path.exists():
            self._send_json({"error": "not found"}, 404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    # -- Routing ------------------------------------------------------------

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        elif path == "/api/config":
            try:
                config = _load_config()
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)
                return
            self._send_json({
                "config": config,
                "profiles": _profile_names(config),
                "action_schema": ACTION_SCHEMA,
                "icon_schema": ICON_SCHEMA,
            })
        elif path == "/api/sounds":
            SOUND_DIR.mkdir(parents=True, exist_ok=True)
            # Der Standard-Sound wird im Frontend separat als eigene "Standard-
            # Ton"-Option gefuehrt (Wert "default") - hier ausschliessen, sonst
            # taucht dieselbe Datei doppelt in der Auswahl auf.
            sounds = sorted(
                str(p.relative_to(PROJECT_ROOT)) for p in SOUND_DIR.rglob("*")
                if p.is_file() and p.suffix.lower() in (".wav", ".mp3", ".ogg") and p.resolve() != DEFAULT_SOUND_FILE
            )
            self._send_json({"sounds": sounds})
        elif path == "/api/asset":
            rel = (qs.get("path") or [""])[0]
            asset_path = (PROJECT_ROOT / rel).resolve()
            if not str(asset_path).startswith(str(PROJECT_ROOT.resolve())) or not asset_path.exists():
                self._send_json({"error": "not found"}, 404)
                return
            ext = asset_path.suffix.lower()
            ctype = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
            }.get(ext, "application/octet-stream")
            self._send_file(asset_path, ctype)
        elif path == "/api/update-check":
            self._send_json(_update_check())
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/config":
            try:
                body = self._read_json_body()
                _save_config(body["config"])
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)
                return
            self._send_json({"ok": True})
        elif path == "/api/restart":
            try:
                if sys.platform == "win32":
                    _restart_daemon_windows()
                else:
                    subprocess.run(["systemctl", "--user", "restart", SERVICE_NAME], check=True, timeout=15)
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)
                return
            self._send_json({"ok": True})
        elif path == "/api/upload-sound":
            try:
                body = self._read_json_body()
                filename = "".join(c for c in body["filename"] if c.isalnum() or c in "._-") or "sound"
                data = base64.b64decode(body["data_base64"])
                CUSTOM_SOUND_DIR.mkdir(parents=True, exist_ok=True)
                dest = CUSTOM_SOUND_DIR / filename
                dest.write_bytes(data)
                rel = str(dest.relative_to(PROJECT_ROOT))
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)
                return
            self._send_json({"ok": True, "path": rel})
        else:
            self._send_json({"error": "not found"}, 404)


_embedded_server: ThreadingHTTPServer | None = None
_embedded_lock = threading.Lock()


def start_in_thread(port: int = 8420) -> bool:
    """Startet die GUI eingebettet im aufrufenden Prozess (eigener Daemon-
    Thread) statt als externes Subprocess - genutzt vom 'open_gui'-Aktionstyp
    (streamdeck_driver/actions.py). Funktioniert identisch im normalen
    Python-Lauf UND in der per PyInstaller gebauten .exe (dort gibt es keinen
    aufrufbaren eigenstaendigen 'python'-Interpreter mehr fuer ein separates
    Skript - `sys.executable` ist dort die .exe selbst).

    Gibt True zurueck wenn hier neu gestartet, False wenn schon eine eigene
    Instanz lief ODER der Port von einer separat gestarteten
    `python3 gui/server.py`-Instanz belegt ist (in beiden Faellen ist unter
    der URL bereits eine GUI erreichbar, der Aufrufer muss nichts weiter tun)."""
    global _embedded_server
    with _embedded_lock:
        if _embedded_server is not None:
            return False
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError:
            return False
        _embedded_server = server
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8420)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Settings-GUI laeuft auf {url} (Strg+C zum Beenden)")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
