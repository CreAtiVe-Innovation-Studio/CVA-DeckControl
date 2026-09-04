"""Live-Browser-Spiegel beider Stream Decks - rein zum Spass: zeigt in einem
lokalen Webbrowser-Tab (per ~1s-Polling) exakt das, was gerade wirklich auf
den beiden echten Geraeten zu sehen ist, grob in ihrer physischen 2x3- bzw.
5x3-Rasterform nachgebaut.

Standardmaessig AUS (Nutzerwunsch: "Standard beim Systemstart ist aus").
An/Aus per Datei-Flag (ENABLED_FLAG_PATH - existiert die Datei, ist es an),
nicht per direktem Funktionsaufruf: die Settings-GUI (gui/server.py) laeuft
als EIGENER Prozess und kann daemon.py deshalb nicht direkt ansprechen -
die Datei ist der gemeinsame Schaltpunkt, die UnifiedDaemon-Hauptschleife in
daemon.py pollt sie (siehe dort) und ruft start()/stop() entsprechend auf."""
from __future__ import annotations

import io
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from PIL import Image

from .paths import app_root

logger = logging.getLogger("streamdeck_driver.live_view")

PORT = 8421
ENABLED_FLAG_PATH = app_root() / "config" / "live_view.enabled"


_enabled = False  # Standard: aus - siehe set_enabled()/is_enabled(), von daemon.py per Datei-Flag gesteuert


def is_enabled() -> bool:
    return _enabled


def set_enabled(value: bool) -> None:
    global _enabled
    _enabled = value


class SnapshotStore:
    """Thread-sicherer Cache: letztes gerendertes Bild pro Taste, schon als
    PNG-Bytes (spart wiederholtes Encodieren bei jedem Browser-Poll). update()
    ist bei ausgeschalteter Live-Ansicht ein No-Op (kein PNG-Encode-Overhead
    bei jedem Tasten-Rendern, nicht nur ein verstecktes Frontend)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._png: dict[int, bytes] = {}

    def update(self, key_index: int, img: Image.Image) -> None:
        if not _enabled:
            return
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        with self._lock:
            self._png[key_index] = buf.getvalue()

    def get(self, key_index: int) -> bytes | None:
        with self._lock:
            return self._png.get(key_index)


elgato_snapshot = SnapshotStore()
deckone_snapshot = SnapshotStore()


def _blank_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (15, 15, 18)).save(buf, format="PNG")
    return buf.getvalue()


_PLACEHOLDER_PNG = _blank_png()

INDEX_HTML = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>CVA-DeckControl – Live-Ansicht</title>
<style>
  :root { color-scheme: dark; }
  body {
    margin: 0; min-height: 100vh; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 40px;
    background: radial-gradient(1100px 650px at 20% -10%, rgba(56,189,248,0.12), transparent 60%),
                radial-gradient(900px 650px at 100% 10%, rgba(167,139,250,0.10), transparent 55%),
                #05070d;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #e8ecf7; padding: 30px 16px;
  }
  h1 { font-size: 14px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
       color: #8890a6; margin: 0 0 14px; text-align: center; }
  .device {
    background: rgba(255,255,255,0.045); border: 1px solid rgba(255,255,255,0.09);
    border-radius: 22px; padding: 22px 26px; backdrop-filter: blur(18px);
    box-shadow: 0 20px 50px -20px rgba(0,0,0,0.6);
  }
  .grid { display: grid; }
  .key {
    border-radius: 8px; overflow: hidden; background: #0d0f16;
    border: 1px solid rgba(255,255,255,0.08);
  }
  .key img { display: block; width: 100%; height: 100%; object-fit: cover; }
  .elgato .grid { grid-template-columns: repeat(3, 66px); grid-template-rows: repeat(2, 66px); gap: 8px; }
  /* DECK-ONE-Kachelluecke im echten Verhaeltnis (0,9cm Luecke / 1,3cm Taste,
     siehe radar.py::GAP_PX) statt eines geratenen Werts - bei 78px Kachel-
     groesse also 78 * 0.9/1.3 ~= 54px, nicht die vorher zu kleinen 8px. */
  .deckone .grid { grid-template-columns: repeat(5, 78px); grid-template-rows: repeat(3, 78px); gap: 54px; }
  footer { color: #565d70; font-size: 11px; text-align: center; }
</style>
</head>
<body>
  <div class="device elgato">
    <h1>Elgato Stream Deck Mini</h1>
    <div class="grid" id="grid-elgato"></div>
  </div>
  <div class="device deckone">
    <h1>Streamplify DECK ONE</h1>
    <div class="grid" id="grid-deckone"></div>
  </div>
  <footer>aktualisiert automatisch · nur Spiegelbild, keine Steuerung</footer>
<script>
function buildGrid(id, count, prefix) {
  const el = document.getElementById(id);
  const imgs = [];
  for (let i = 0; i < count; i++) {
    const cell = document.createElement("div");
    cell.className = "key";
    const img = document.createElement("img");
    img.dataset.idx = i;
    cell.appendChild(img);
    el.appendChild(cell);
    imgs.push(img);
  }
  return imgs;
}
const elgatoImgs = buildGrid("grid-elgato", 6, "elgato");
const deckoneImgs = buildGrid("grid-deckone", 15, "deckone");

function refresh(imgs, prefix) {
  const t = Date.now();
  imgs.forEach(img => { img.src = `/tile/${prefix}/${img.dataset.idx}.png?t=${t}`; });
}
setInterval(() => { refresh(elgatoImgs, "elgato"); refresh(deckoneImgs, "deckone"); }, 1000);
refresh(elgatoImgs, "elgato");
refresh(deckoneImgs, "deckone");
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # weniger Konsolen-Rauschen
        pass

    def _send_png(self, data: bytes | None) -> None:
        body = data if data is not None else _PLACEHOLDER_PNG
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/tile/elgato/"):
            idx = int(path.rsplit("/", 1)[-1].split(".")[0])
            self._send_png(elgato_snapshot.get(idx))
            return
        if path.startswith("/tile/deckone/"):
            idx = int(path.rsplit("/", 1)[-1].split(".")[0])
            self._send_png(deckone_snapshot.get(idx))
            return
        self.send_response(404)
        self.end_headers()


_server: ThreadingHTTPServer | None = None
_thread: threading.Thread | None = None


def start() -> None:
    global _server, _thread
    set_enabled(True)
    if _server is not None:
        return
    try:
        _server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    except OSError as exc:
        logger.warning("Live-Ansicht konnte nicht gestartet werden (Port %s): %s", PORT, exc)
        return
    _thread = threading.Thread(target=_server.serve_forever, name="live-view-server", daemon=True)
    _thread.start()
    logger.info("Live-Ansicht laeuft auf http://127.0.0.1:%s/", PORT)


def stop() -> None:
    global _server, _thread
    set_enabled(False)
    if _server is not None:
        _server.shutdown()
        _server = None
    _thread = None
    logger.info("Live-Ansicht gestoppt")


def toggle_enabled_flag() -> bool:
    """Kippt den Datei-Flag direkt um - fuer die physische Umschalt-Taste auf
    der Timer-Seite (siehe deckone_controller.py). Gibt den NEUEN Zustand
    zurueck. Das eigentliche Starten/Stoppen passiert weiterhin ueber
    sync_with_flag_file() im Haupt-Loop, nicht hier direkt - selbe Logik wie
    beim GUI-Pfad (gui/server.py), nur ohne den Umweg ueber HTTP."""
    if ENABLED_FLAG_PATH.exists():
        ENABLED_FLAG_PATH.unlink()
        return False
    ENABLED_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENABLED_FLAG_PATH.write_text("")
    return True


def sync_with_flag_file() -> None:
    """Von der UnifiedDaemon-Hauptschleife (daemon.py) regelmaessig aufgerufen:
    startet/stoppt den Server je nachdem, ob ENABLED_FLAG_PATH gerade
    existiert - das ist der einzige Kanal, ueber den die (in einem eigenen
    Prozess laufende) Settings-GUI die Live-Ansicht an/ausschalten kann."""
    should_run = ENABLED_FLAG_PATH.exists()
    if should_run and _server is None:
        start()
    elif not should_run and _server is not None:
        stop()
