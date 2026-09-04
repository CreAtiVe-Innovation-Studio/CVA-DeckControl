"""Elgato Stream Deck Mini - Treiber ueber hidapi.

Protokoll wurde aus echten USBPcap-Captures rekonstruiert
(../../dokumentation/usb-captures/20260820-*_elgato-*.pcapng) und live gegen die
angeschlossene Hardware verifiziert (siehe SETUP.md, Abschnitt "Was wirklich
getestet wurde"). Zusammenfassung der WICHTIGSTEN KORREKTUR gegenueber der
urspruenglichen Doku (usb-protokoll-analyse.md):

Die Doku beschrieb das Helligkeits-/Vorbereitungskommando als 5-Byte-Payload
"55 AA D1 01 <Wert>" per Control-Transfer. Die exakte Byte-fuer-Byte-Analyse des
rohen Capture-Payloads zeigt: das ist tatsaechlich ein HID SET_REPORT(Feature),
Report-ID 5, mit insgesamt 17 Byte Report-Inhalt:
    [reportID=0x05, 0x55, 0xAA, 0xD1, 0x01, <Helligkeit 0-100>,
     0x00,0x00,0x00,0x00,0x00,0x00, 0x01, 0x00,0x00,0x00, 0x60]
Die Doku hatte "wIndex=0x0011, wLength=0x0005" aus den rohen Hex-Bytes "00 11 00
05" abgelesen, ohne Little-Endian-Byteorder anzuwenden - tatsaechlich ist
wIndex=0x0000 und wLength=0x0011(=17). Die "5 Byte Payload" der Doku sind nur die
ersten 5 Byte NACH der Report-ID des tatsaechlich 17 Byte langen Feature-Reports.
Ueber hidapi ist das unerheblich: hid.send_feature_report() kapselt das exakt
richtig, wenn man ihr den vollen 17-Byte-Puffer (inkl. Report-ID als erstes Byte)
uebergibt.

Tastenbild setzen: HID Output-Report, Report-ID 2, 1024 Byte total, Format:
    byte0 = 0x02 (Report-ID)
    byte1 = key_index (0-basiert, 0-5 bei der Mini mit 6 Tasten)
    byte2 = Chunk-/Seitennummer (0-basiert, steigt pro Paket)
    byte3 = 1 wenn letzter Chunk dieses Bildes, sonst 0
    byte4 = 0x00 (konstant, Bedeutung unklar)
    byte5 = 0x05 (konstant, Bedeutung unklar)
    byte6..15 = 0x00 Padding
    byte16..1023 = rohe BMP-Bytes (1008 Byte/Chunk, letzter Chunk mit 0x00
                   aufgefuellt), BMP = Pillow-Standardausgabe 80x80x24bpp
                   (bottom-up, passt exakt zum Capture-Header)

Tastendruck-Event: HID Input-Report, Report-ID 1, 17 Byte:
    byte0 = 0x01 (Report-ID, konstant)
    byte1..6 = je 1 Byte Status pro Taste (0-5), 0x01=gedrueckt, 0x00=losgelassen
    byte7..16 = reserviert/0x00

Live gegen echte Hardware verifiziert am 2026-08-20 (siehe SETUP.md).
"""
from __future__ import annotations

import io
import logging
import threading
import time
from typing import Optional

import hid
from PIL import Image

from .base import DeviceInfo, KeyEventCallback, StreamDeckDevice

logger = logging.getLogger(__name__)

VENDOR_ID = 0x0FD9
PRODUCT_ID = 0x0063

REPORT_ID_FEATURE = 0x05
REPORT_ID_IMAGE = 0x02
REPORT_ID_KEYPRESS = 0x01

IMAGE_REPORT_SIZE = 1024
IMAGE_HEADER_SIZE = 16
IMAGE_PAYLOAD_PER_CHUNK = IMAGE_REPORT_SIZE - IMAGE_HEADER_SIZE  # 1008

KEYPRESS_REPORT_SIZE = 17
NUM_KEYS = 6


class ElgatoMini(StreamDeckDevice):
    def __init__(self) -> None:
        self.info = DeviceInfo(
            name="Elgato Stream Deck Mini",
            vendor_id=VENDOR_ID,
            product_id=PRODUCT_ID,
            num_keys=NUM_KEYS,
            grid_rows=2,
            grid_cols=3,
            image_size=(80, 80),
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
            d.open(VENDOR_ID, PRODUCT_ID)
            d.set_nonblocking(False)
            self._dev = d
            logger.info("Elgato Stream Deck Mini verbunden")
            return True
        except (IOError, OSError) as exc:
            logger.warning("Elgato Stream Deck Mini nicht erreichbar: %s", exc)
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
        # KORRIGIERT 2026-08-20 gegen die offizielle Elgato-Protokoll-Doku +
        # Referenzimplementierung (python-elgato-streamdeck, StreamDeckMini.py):
        # nur die ersten 6 Bytes sind belegt, der Rest des 17-Byte-Feature-Reports
        # ist Null-Padding - die vorherige Version hatte an Offset 12/16
        # faelschlich 0x01/0x60 gesetzt (Fehlinterpretation der Doku), was das
        # Geraet vermutlich als ungueltigen Report verworfen hat.
        if self._dev is None:
            return False
        percent = max(0, min(100, int(percent)))
        report = bytes([REPORT_ID_FEATURE, 0x55, 0xAA, 0xD1, 0x01, percent]) + bytes(11)
        try:
            n = self._dev.send_feature_report(report)
            ok = n == len(report)
            if not ok:
                logger.warning("Helligkeit setzen: send_feature_report gab %s zurueck", n)
            return ok
        except (IOError, OSError) as exc:
            logger.error("Helligkeit setzen fehlgeschlagen: %s", exc)
            return False

    def set_key_image(self, key_index: int, image: Image.Image, force: bool = False) -> bool:
        if self._dev is None:
            return False
        if not (0 <= key_index < NUM_KEYS):
            logger.error("Elgato: ungueltiger key_index %s", key_index)
            return False

        # KORRIGIERT 2026-08-20: Bild muss vor dem BMP-Export 90 Grad im
        # Uhrzeigersinn gedreht UND vertikal gespiegelt werden (offizielle
        # Elgato-Doku + Referenzimplementierung, KEY_ROTATION=90/KEY_FLIP=
        # (False, True)) - fehlte komplett in der vorherigen Version.
        # KORREKTUR 2026-08-20 (empirisch mit Testbild verifiziert, nicht nur
        # aus Doku uebernommen): weder rotate(-90)+FlipV noch rotate(+90)+FlipV
        # waren richtig (erst "auf dem Kopf", dann "spiegelverkehrt"). Echter
        # Test mit einem Pfeil+4-Ecken-Testbild (siehe SETUP.md) zeigt: TL
        # bleibt TL, Pfeil "oben" wird zu "links" - das ist exakt eine
        # Transponierung (Spiegelung an der TL-BR-Diagonale), KEINE Rotation.
        w, h = self.info.image_size
        img = image.convert("RGB").resize((w, h))
        img = img.transpose(Image.TRANSPOSE)
        buf = io.BytesIO()
        img.save(buf, format="BMP")
        bmp_bytes = buf.getvalue()

        img_hash = bmp_bytes[:64] + bmp_bytes[-64:] + len(bmp_bytes).to_bytes(4, "little")
        if not force and self._sent_image_hash.get(key_index) == img_hash:
            # Bild wurde fuer diese Taste bereits mit identischem Inhalt gesendet.
            # Laut Doku cached das Geraet selbst - kein Reupload noetig.
            logger.debug("Elgato Taste %s: Bild unveraendert, kein Reupload", key_index)
            return True

        chunks = [
            bmp_bytes[i : i + IMAGE_PAYLOAD_PER_CHUNK]
            for i in range(0, len(bmp_bytes), IMAGE_PAYLOAD_PER_CHUNK)
        ]
        try:
            for page, chunk in enumerate(chunks):
                is_last = 1 if page == len(chunks) - 1 else 0
                padded_chunk = chunk + bytes(IMAGE_PAYLOAD_PER_CHUNK - len(chunk))
                # KORRIGIERT 2026-08-20 gegen offizielle Doku + Referenz-Lib:
                # Feldreihenfolge war komplett verschoben (key_index/page/is_last
                # standen an den falschen Offsets, byte5 war faelschlich eine
                # Konstante 0x05 statt des 1-basierten Tastenindex).
                header = bytes(
                    [
                        REPORT_ID_IMAGE,   # 0x02
                        0x01,              # Kommando
                        page & 0xFF,       # Chunk-/Seitenindex
                        0x00,              # reserviert
                        is_last,           # "Show Image"-Flag (1 = letzter Chunk)
                        key_index + 1,     # Tastenindex, 1-basiert
                        0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                    ]
                )
                report = header + padded_chunk
                assert len(report) == IMAGE_REPORT_SIZE
                n = self._dev.write(report)
                if n < 0:
                    logger.error("Elgato Taste %s Chunk %s: write() fehlgeschlagen", key_index, page)
                    return False
            self._sent_image_hash[key_index] = img_hash
            return True
        except (IOError, OSError) as exc:
            logger.error("Elgato Bild setzen fehlgeschlagen (Taste %s): %s", key_index, exc)
            return False

    def start_event_loop(self, callback: KeyEventCallback) -> None:
        if self._dev is None:
            return
        self._stop_event.clear()

        def _run():
            self._dev.set_nonblocking(True)
            last_state = [False] * NUM_KEYS
            while not self._stop_event.is_set():
                try:
                    data = self._dev.read(KEYPRESS_REPORT_SIZE, timeout_ms=200)
                except (IOError, OSError) as exc:
                    logger.warning("Elgato Event-Loop: Lesefehler, breche ab: %s", exc)
                    return
                if not data:
                    continue
                if data[0] != REPORT_ID_KEYPRESS:
                    continue
                for i in range(NUM_KEYS):
                    pressed = bool(data[1 + i])
                    if pressed != last_state[i]:
                        last_state[i] = pressed
                        try:
                            callback(i, pressed)
                        except Exception:
                            logger.exception("Fehler im Elgato Key-Callback (Taste %s)", i)

        self._event_thread = threading.Thread(
            target=_run, name="elgato-mini-events", daemon=True
        )
        self._event_thread.start()

    def stop_event_loop(self) -> None:
        self._stop_event.set()
        if self._event_thread is not None:
            self._event_thread.join(timeout=2)
            self._event_thread = None
