"""EXPERIMENTELL - Parametrisierter Treiber fuer ANDERE Elgato-Stream-Deck-
Modelle (Original, MK.2, XL, ...), jedes einzelne Modell hier UNGETESTET
gegen echte Hardware (siehe verified=False je MODEL_TABLE-Eintrag). NICHT
die Mini - die hat ihren eigenen, gegen echte Hardware verifizierten Treiber
in elgato_mini.py und wird von diesem Modul bewusst nicht angetastet
(Null-Risiko fuer den bereits funktionierenden Pfad). Bei Fehlern/falscher
Bildausrichtung bitte ein Issue im Repo aufmachen (mit Modellname + einem
Foto der Fehldarstellung) statt es stillschweigend hinzunehmen.

WICHTIGER VORBEHALT, unbedingt lesen bevor ein neues Modell eingesetzt wird:
Nur die Mini (VID:PID 0x0FD9:0x0063) ist gegen echte Hardware verifiziert.
Die Eintraege in MODEL_TABLE fuer andere Modelle stammen aus oeffentlich
bekannten VID:PID-Zuordnungen und gaengigen Community-Treiber-Konventionen
(aehnliche Report-Struktur wie bei der Mini: Report-ID + Tastenindex +
Chunk-Index + Bild-Payload), sind aber NICHT gegen echte Hardware getestet.

Dieses Projekt hat bei der Mini UND bei der DECK ONE mehrfach erlebt, dass
genau solche Details (Bildformat, Rotation/Spiegelung, Tastennummerierung,
Byte-Offsets) erst durch echte USBPcap-Captures + Testbilder gegen
angeschlossene Hardware sicher zu klaeren waren (siehe elgato_mini.py- und
deckone.py-Kommentare) - blindes Vertrauen in eine "sollte passen"-Tabelle
waere hier unehrlich. Jedes 'verified': False-Modell MUSS vor produktivem
Einsatz an echter Hardware ueberprueft werden (siehe SETUP-Hinweis in
tools/detect_elgato_device.py) - Bildausrichtung ist der wahrscheinlichste
Stolperstein, danach Bildformat (BMP vs. JPEG)."""
from __future__ import annotations

import io
import logging
import threading
from dataclasses import dataclass
from typing import Callable, Optional

import hid
from PIL import Image

from .base import DeviceInfo, KeyEventCallback, StreamDeckDevice

logger = logging.getLogger(__name__)

VENDOR_ID_ELGATO = 0x0FD9


@dataclass(frozen=True)
class ElgatoModel:
    name: str
    product_id: int
    num_keys: int
    grid_rows: int
    grid_cols: int
    image_size: tuple[int, int]
    image_format: str = "jpeg"  # "jpeg" oder "bmp" - Mini nutzt BMP, die meisten neueren Modelle JPEG
    # PIL-Transform vor dem Kodieren - siehe elgato_mini.py fuer den Hintergrund,
    # warum das je Modell empirisch ermittelt werden muss (dort: TRANSPOSE, keine Rotation).
    transform: Optional[str] = None  # None | "transpose" | "rotate180" | "fliph" | "flipv"
    verified: bool = False

    def apply_transform(self, img: Image.Image) -> Image.Image:
        if self.transform is None:
            return img
        if self.transform == "transpose":
            return img.transpose(Image.TRANSPOSE)
        if self.transform == "rotate180":
            return img.transpose(Image.ROTATE_180)
        if self.transform == "fliph":
            return img.transpose(Image.FLIP_LEFT_RIGHT)
        if self.transform == "flipv":
            return img.transpose(Image.FLIP_TOP_BOTTOM)
        return img


# UNGETESTET (siehe Modul-Docstring) bis auf die Mini, die hier absichtlich
# NICHT gelistet ist (eigener Treiber, siehe elgato_mini.py).
MODEL_TABLE: dict[int, ElgatoModel] = {
    0x0060: ElgatoModel(
        name="Elgato Stream Deck (Original, v1)", product_id=0x0060,
        num_keys=15, grid_rows=3, grid_cols=5, image_size=(72, 72),
        image_format="bmp", transform="rotate180", verified=False,
    ),
    0x006D: ElgatoModel(
        name="Elgato Stream Deck (Original, v2)", product_id=0x006D,
        num_keys=15, grid_rows=3, grid_cols=5, image_size=(72, 72),
        image_format="jpeg", transform="rotate180", verified=False,
    ),
    0x0080: ElgatoModel(
        name="Elgato Stream Deck MK.2", product_id=0x0080,
        num_keys=15, grid_rows=3, grid_cols=5, image_size=(72, 72),
        image_format="jpeg", transform="rotate180", verified=False,
    ),
    0x006C: ElgatoModel(
        name="Elgato Stream Deck XL", product_id=0x006C,
        num_keys=32, grid_rows=4, grid_cols=8, image_size=(96, 96),
        image_format="jpeg", transform="rotate180", verified=False,
    ),
    0x008F: ElgatoModel(
        name="Elgato Stream Deck XL (v2)", product_id=0x008F,
        num_keys=32, grid_rows=4, grid_cols=8, image_size=(96, 96),
        image_format="jpeg", transform="rotate180", verified=False,
    ),
}

# Bewusst NICHT unterstuetzt: Stream Deck + (Tasten UND Drehregler UND
# Touch-Strip - kein reines Tastenraster mehr, braucht eigene UI-Konzepte)
# und Stream Deck Neo (fest eingebautes Zusatz-Info-Display) - beides
# architektonisch zu verschieden von "15/32 gleichartige Bild-Tasten", um es
# hier einfach mitzuparametrisieren statt es sauber neu zu durchdenken.

REPORT_ID_IMAGE = 0x02
IMAGE_REPORT_SIZE = 1024
IMAGE_HEADER_SIZE = 16
IMAGE_PAYLOAD_PER_CHUNK = IMAGE_REPORT_SIZE - IMAGE_HEADER_SIZE  # 1008
REPORT_ID_KEYPRESS = 0x01
KEYPRESS_REPORT_SIZE = 17


def detect_connected_model() -> Optional[ElgatoModel]:
    """Sucht unter allen bekannten (auch unverifizierten) Modell-PIDs nach
    einem gerade angeschlossenen Geraet - fuer ein einfaches Erkennungs-Tool,
    nicht fuer den Normalbetrieb (der laedt ein Modell explizit)."""
    for pid, model in MODEL_TABLE.items():
        try:
            devices = hid.enumerate(VENDOR_ID_ELGATO, pid)
        except Exception:
            devices = []
        if devices:
            return model
    return None


class ElgatoGenericDevice(StreamDeckDevice):
    """Wie ElgatoMini (elgato_mini.py), aber Vendor-Daten kommen aus einem
    ElgatoModel statt hart codierter Mini-Konstanten. Bild-Report-Struktur
    (Header-Layout, Chunking) ist identisch zur Mini uebernommen - das ist
    der Teil, der sich laut oeffentlicher Dokumentation ueber die meisten
    Elgato-Modelle hinweg kaum unterscheidet. Was sich WIRKLICH je Modell
    unterscheidet (Bildformat, Rotation/Spiegelung) steckt im ElgatoModel."""

    def __init__(self, model: ElgatoModel) -> None:
        self.model = model
        if not model.verified:
            logger.warning(
                "Modell '%s' ist NICHT gegen echte Hardware verifiziert (siehe "
                "devices/elgato_generic.py-Docstring) - Bildausrichtung/-format "
                "vor produktivem Einsatz mit einem Testbild pruefen!", model.name,
            )
        self.info = DeviceInfo(
            name=model.name,
            vendor_id=VENDOR_ID_ELGATO,
            product_id=model.product_id,
            num_keys=model.num_keys,
            grid_rows=model.grid_rows,
            grid_cols=model.grid_cols,
            image_size=model.image_size,
        )
        self._dev: Optional[hid.device] = None
        self._event_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._sent_image_hash: dict[int, bytes] = {}

    @property
    def connected(self) -> bool:
        return self._dev is not None

    def connect(self) -> bool:
        try:
            d = hid.device()
            d.open(VENDOR_ID_ELGATO, self.model.product_id)
            d.set_nonblocking(False)
            self._dev = d
            logger.info("%s verbunden", self.model.name)
            return True
        except (IOError, OSError) as exc:
            logger.warning("%s nicht erreichbar: %s", self.model.name, exc)
            self._dev = None
            return False

    def disconnect(self) -> None:
        self.stop_event_loop()
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

    def set_brightness(self, percent: int) -> bool:
        # UNGETESTET: uebernimmt das Mini-Feature-Report-Format 1:1 (siehe
        # elgato_mini.py::set_brightness) - fuer andere Modelle oeffentlich
        # als weitgehend gleich dokumentiert, aber nicht verifiziert.
        if self._dev is None:
            return False
        percent = max(0, min(100, int(percent)))
        report = bytes([0x05, 0x55, 0xAA, 0xD1, 0x01, percent]) + bytes(11)
        try:
            n = self._dev.send_feature_report(report)
            return n == len(report)
        except (IOError, OSError) as exc:
            logger.error("%s: Helligkeit setzen fehlgeschlagen: %s", self.model.name, exc)
            return False

    def set_key_image(self, key_index: int, image: Image.Image, force: bool = False) -> bool:
        if self._dev is None:
            return False
        if not (0 <= key_index < self.model.num_keys):
            logger.error("%s: ungueltiger key_index %s", self.model.name, key_index)
            return False

        w, h = self.model.image_size
        img = self.model.apply_transform(image.convert("RGB").resize((w, h)))
        buf = io.BytesIO()
        img.save(buf, format="BMP" if self.model.image_format == "bmp" else "JPEG")
        img_bytes = buf.getvalue()

        img_hash = img_bytes[:64] + img_bytes[-64:] + len(img_bytes).to_bytes(4, "little")
        if not force and self._sent_image_hash.get(key_index) == img_hash:
            return True

        chunks = [
            img_bytes[i : i + IMAGE_PAYLOAD_PER_CHUNK]
            for i in range(0, len(img_bytes), IMAGE_PAYLOAD_PER_CHUNK)
        ]
        try:
            for page, chunk in enumerate(chunks):
                is_last = 1 if page == len(chunks) - 1 else 0
                padded_chunk = chunk + bytes(IMAGE_PAYLOAD_PER_CHUNK - len(chunk))
                header = bytes([
                    REPORT_ID_IMAGE, 0x01, page & 0xFF, 0x00, is_last, key_index + 1,
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                ])
                report = header + padded_chunk
                n = self._dev.write(report)
                if n < 0:
                    logger.error("%s Taste %s Chunk %s: write() fehlgeschlagen", self.model.name, key_index, page)
                    return False
            self._sent_image_hash[key_index] = img_hash
            return True
        except (IOError, OSError) as exc:
            logger.error("%s Bild setzen fehlgeschlagen (Taste %s): %s", self.model.name, key_index, exc)
            return False

    def start_event_loop(self, callback: KeyEventCallback) -> None:
        if self._dev is None:
            return
        self._stop_event.clear()
        num_keys = self.model.num_keys

        def _run():
            self._dev.set_nonblocking(True)
            last_state = [False] * num_keys
            while not self._stop_event.is_set():
                try:
                    data = self._dev.read(KEYPRESS_REPORT_SIZE + num_keys, timeout_ms=200)
                except (IOError, OSError) as exc:
                    logger.warning("%s Event-Loop: Lesefehler, breche ab: %s", self.model.name, exc)
                    return
                if not data or data[0] != REPORT_ID_KEYPRESS:
                    continue
                for i in range(num_keys):
                    if 1 + i >= len(data):
                        break
                    pressed = bool(data[1 + i])
                    if pressed != last_state[i]:
                        last_state[i] = pressed
                        try:
                            callback(i, pressed)
                        except Exception:
                            logger.exception("Fehler im %s Key-Callback (Taste %s)", self.model.name, i)

        self._event_thread = threading.Thread(target=_run, name="elgato-generic-events", daemon=True)
        self._event_thread.start()

    def stop_event_loop(self) -> None:
        self._stop_event.set()
        if self._event_thread is not None:
            self._event_thread.join(timeout=2)
            self._event_thread = None
