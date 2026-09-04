"""Streamplify DECK ONE - Treiber ueber pyusb (libusb).

KORRIGIERT 2026-08-20 (zweite Runde): Die vorherige Version dieses Moduls
implementierte ein aus (falsch zugeordneten) Windows-Captures rekonstruiertes
Protokoll gegen die FALSCHE VID/PID (0x320F:0x505A = die Tastatur des
Nutzers, siehe dokumentation/README.md "KRITISCHE KORREKTUR"). Gegen die
echte VID/PID (0x0100:0x1000, per Aus-/Einstecken-Diff bestaetigt) lief das
Bild-Upload-Kommando dann in einen Timeout - das Geraet nahm gar keine
Interrupt-OUT-Daten an.

Ursache gefunden per Web-Recherche: das DECK ONE ist ein Rebrand eines
weitverbreiteten "HotSpot/Mirabox StreamDock"-OEM-Chips. Das quelloffene
Referenzprojekt https://github.com/rigor789/mirabox-streamdock-node
dokumentiert exakt dasselbe "CRT"/"BAT"-Token-Protokoll wie unsere eigene
(urspruenglich fehlzugeordnete) Doku - UND einen bisher komplett fehlenden
Schritt: ein explizites "Wach"-Kommando (CRT+DIS), das vor jedem anderen
Befehl gesendet werden muss, sonst ignoriert das Geraet alles (passt exakt
zum beobachteten Timeout und zum vom Nutzer bestaetigten "Software aus"-
Sperrbild-Zustand).

Bestaetigtes Protokoll (aus der Referenzimplementierung uebernommen, NICHT
mehr aus den urspruenglichen - moeglicherweise kontaminierten - eigenen
Captures):

Alle Kommandos: CMD_PREFIX (5 Byte: b"CRT\\x00\\x00") + Sub-Kommando,
aufgefuellt mit 0x00 auf 512 Byte Gesamtlaenge, per Interrupt-OUT auf
Endpoint 0x01 gesendet.

- Wake/Bildschirm aufwecken:  b"DIS\\x00\\x00"                         (vor JEDEM anderen Kommando noetig)
- Helligkeit setzen:          b"LIG\\x00\\x00" + bytes([0-100])
- Bildschirm loeschen:        b"CLE\\x00\\x00\\x00" + bytes([target])
- Tastenbild setzen (Header): b"BAT" + size_u32_be + bytes([key_id])   (OHNE Padding zwischen "BAT" und der Groesse!)
                               gefolgt von den rohen JPEG-Bytes in
                               512-Byte-Folgepaketen (kein eigener Header
                               pro Chunk, letztes Paket mit 0x00 aufgefuellt)
- Abschluss/Refresh:          b"STP\\x00\\x00"                         (1x nach dem letzten Bild eines Batches)

Bildformat: JPEG, 100x100 Pixel, um 180 Grad gedreht (wie in der eigenen,
strukturell weiterhin plausiblen Doku vermerkt - dieser Teil hat sich durch
die VID/PID-Korrektur nicht geaendert, nur der Transportkanal drumherum).

Tastendruck-Event (Interrupt-IN, vermutete Groesse 512 Byte, NICHT mehr
"ACK"/"OK"-Praefix wie in der alten - vermutlich kontaminierten - Doku,
sondern gemaess Referenzimplementierung):
    byte[9]  = roher Tastenindex (0x1-0xf), per KEY_MAP auf logischen Index
               0-14 abgebildet (Referenz-Mapping: 0x1-0xf -> 0x0b-0x05,
               absteigend - hier 1:1 uebernommen, ungetestet gegen unsere
               eigene Hardware, siehe SETUP.md)
    byte[10] = 1=gedrueckt, 0=losgelassen

Die Endian-Richtung des 4-Byte-Groessenfelds bei BAT ist in der
Referenzimplementierung nicht explizit dokumentiert (nur "sizeBytes(size,4)")
- big-endian wird hier als Erstversuch angenommen (ueblicher fuer
Netzwerk-/Firmware-Protokolle), muss ggf. bei Fehlschlag auf little-endian
umgestellt werden.

STAND 2026-08-20, zweiter Durchlauf: WEITERHIN NICHT FUNKTIONSFAEHIG.
GET_REPORT (Firmware-Version auslesen, Control-Transfer bmRequestType=0xA1,
bRequest=0x01, wValue=0x0100, wIndex=0, wLength=512) funktioniert einwandfrei
und liefert echte Daten zurueck: "V2.One.00.001" - beweist zweifelsfrei, dass
0x0100:0x1000 das richtige Geraet ist und der Lesekanal funktioniert.

ABER: jeder Versuch, IRGENDETWAS zum Geraet zu schreiben, scheitert mit
Timeout (Errno 110), unabhaengig von Methode:
- Interrupt-OUT auf Endpoint 0x01 (mit/ohne fuehrendem 0x00-Report-ID-Byte,
  verschiedene Gesamtlaengen 512/513 Byte, verschieden lange Nutzlasten)
- Control-Transfer SET_REPORT (bmRequestType=0x21, bRequest=0x09) sowohl mit
  Output-Report-Type (wValue=0x0200) als auch Feature-Report-Type (0x0300)
- hidapi (Python `hid`-Paket) write() - liefert -1, Fehlermeldung nicht
  verfuegbar (hid_error nicht implementiert in diesem Backend)
- Schreibversuch waehrend ein Hintergrund-Thread parallel den IN-Endpoint
  aktiv abfragt (Verdacht: Firmware braucht aktives Auslesen um OUT zu
  bedienen) - ebenfalls Timeout

EIN Test verhielt sich anders: ein bewusst FALSCHER Control-Request
(bmRequestType=0x41, "vendor"-Typ statt "class") ergab SOFORT einen Pipe-
Error/STALL (0.00s), nicht Timeout - das Geraet unterscheidet also zwischen
"Request-Typ nicht unterstuetzt -> sofort ablehnen" und "Request-Typ
grundsaetzlich richtig, aber wird nicht abgearbeitet -> haengt". Das deutet
auf einen fehlenden Zustands-/Freischalt-Schritt hin, keinen reinen
Formatfehler.

Referenz-Fund (Rust-Crate `mirajazz`, https://github.com/4ndv/mirajazz,
`src/device.rs`, dediziert fuer genau diese Mirabox/Ajazz/HotSpot-Chip-
Familie): dortige initialize()-Sequenz sendet ZWEI Pakete mit fuehrendem
0x00-Report-ID-Byte (`00 43 52 54 00 00 44 49 53` = ReportID+CRT+DIS, dann
ein zweites mit CRT+LIG) ueber `write_extended_data()`/`write_output_report()`
- strukturell identisch zu dem, was hier bereits probiert wurde, aber ueber
eine andere HID-Backend-Bibliothek (Rust `hidapi`-Crate). Nicht ausgeschlossen,
dass diese Rust-Bibliothek auf Linux einen anderen Syscall-Pfad nimmt
(z.B. direktes hidraw-ioctl statt libusb-Interrupt-Transfer) als das hier
verwendete pyusb/Python-hid - das waere der naechste zu pruefende Unterschied,
konnte in dieser Session aber nicht mehr verifiziert werden.

NACHTRAG: auch /dev/hidraw direkt (roher os.write() Syscall, sowohl mit
detachtem als auch mit wieder angehaengtem Kernel-Treiber) probiert -
gleicher Timeout. Damit sind alle unter Linux ueblichen Zugriffswege
(pyusb Interrupt-OUT, pyusb Control-SET_REPORT, Python-hidapi, rohes
hidraw) erschoepft, ohne Erfolg. Der Lesekanal (GET_REPORT) funktioniert
in allen Varianten einwandfrei.

Einzig verbleibender sinnvoller naechster Schritt (siehe SETUP.md):
echte USB-Traffic-Aufnahme der ECHTEN Windows-Software (Streamplify Link)
gegen genau dieses Geraet (z.B. via Windows-VM mit USB-Passthrough) - das
ist die einzige Methode, die "raten" durch "wissen" ersetzt. Alternativ:
mirajazz-Rust-Crate lokal kompilieren und dessen Beispielcode gegen dieses
Geraet testen, um zu pruefen ob ein bibliotheksspezifischer Unterschied
(anderer Syscall-Pfad in Rust-hidapi) die Ursache ist.

NACHTRAG 2026-08-21 (Windows-Session, echter USBPcap-Mitschnitt gegen
Streamplify Link + echtes DECK ONE, siehe dokumentation/usb-protokoll-analyse.md
Teil 3 fuer die vollstaendige Analyse): Kommando-Bytes, Endpoint (0x01,
Interrupt-OUT) und Framing (512 Byte, Nullen aufgefuellt) dieses Moduls sind
BYTE-IDENTISCH zum echten Windows-Traffic bestaetigt - das ist NICHT die
Fehlerursache fuer den Timeout. Zwei konkrete Aenderungen aus dem Mitschnitt:

1. **CLE-Kommando fehlte bisher komplett in connect().** Echte Reihenfolge
   beim Verbindungsaufbau: DIS -> LIG(<Helligkeit>) -> CLE(0xff) -> BAT(...).
   CLE ist jetzt unten ergaenzt (mit Parameter 0xff, so im Mitschnitt
   beobachtet). Das ist die naheliegendste konkrete Hypothese fuer den
   Timeout: falls das Geraet einen internen Zustandsautomaten hat, der ohne
   CLE nicht in einen schreibbereiten Zustand wechselt, wuerde das exakt den
   beobachteten "nimmt DIS an, blockt aber alles danach"-Timeout erklaeren.
   UNGETESTET gegen echte Linux-Hardware - naechster Schritt fuer die
   Linux-Session.
2. **BAT-Groessenfeld-Annahme (struct.pack(">I", len(jpeg_bytes))) ist NICHT
   bestaetigt, vermutlich falsch.** Vergleich zweier Mitschnitte mit
   unterschiedlich grossen Bildern zeigt: Byte 1 (0x1C) und Byte 3 (0x0B)
   sind in BEIDEN Faellen identisch, nur Byte 2 unterscheidet sich (0x22 vs.
   0x37) - das passt nicht zu einer einfachen 32-Bit-Grosse in einer der
   beiden Byte-Reihenfolgen. Vor einem produktiven Bild-Upload-Test unbedingt
   mit echten Grossenwerten gegenpruefen, siehe usb-protokoll-analyse.md.

Falls die Wake-Sequenz mit dem ergaenzten CLE-Kommando immer noch in den
Timeout laeuft: staerkste verbleibende Hypothese ist ein
Kernel-Treiber-Konflikt (usbhid/hidraw haelt Endpoint 1 trotz
detach_kernel_driver() weiterhin implizit offen) - testweise per udev-Regel
usbhid fuer 0100:1000 komplett blockieren, bevor der Treiber startet.
Zweitstaerkste Hypothese: Geraet braucht laenger als 1000ms/einen einzigen
Versuch, um schreibbereit zu werden - ein Retry-Loop ueber mehrere Minuten
war in der Windows-Aufnahme nicht von einem reinen App-Start-Bug (haengender
Netzwerk-Updater-Check) unterscheidbar, siehe usb-protokoll-analyse.md fuer
Details.

STAND 2026-08-21, spaeter Vormittag: GELOEST, echt gegen Hardware verifiziert.
Der CLE-Fix allein hat gereicht - connect() (inkl. DIS+CLE), set_brightness()
und set_key_image()+end_batch() laufen jetzt alle fehlerfrei durch (0.02-0.06s,
kein Timeout mehr), KEIN Kernel-Treiber-Workaround noetig. Sichtpruefung am
Geraet bestaetigt: Helligkeit reagiert, Testbild (gruener Kreis + pinke
Ellipse) wird tatsaechlich angezeigt.

NACHTRAG (gleicher Tag, direkt danach): Ursache fuer die falsche Position
gefunden UND behoben - zwei separate Bugs, beide durch eigene Analyse des
Windows-Mitschnitts (nicht nur Vermutung):

1. **BAT-Groessenfeld war 4 statt 2 Byte.** Vergleich von 5 echten BAT-Headern
   aus dem Mitschnitt (unterschiedliche Bildgroessen) zeigt: Format ist
   `BAT\x00\x00` + 2-Byte-Groesse (big-endian) + 1-Byte-Tastenindex - nicht
   4+1 wie vorher angenommen. Bestaetigt durch ceil(groesse/512) == exakte
   Chunk-Anzahl in allen 5 Faellen. Der bisherige 4-Byte-Header hat den
   Tastenindex um 2 Byte verschoben, wodurch das Geraet ihn falsch gelesen hat.
2. **Geraete-eigene Tastennummerierung zaehlt von UNTEN LINKS zeilenweise nach
   OBEN** (Zeile 1 unten = Tasten 1-5, Zeile 2 = 6-10, Zeile 3 oben = 11-15,
   je Zeile links nach rechts) - GENAU umgekehrt zu unserer eigenen
   Konvention (key_index 0 = oben links, zeilenweise nach unten, passend zu
   den geparsten Profil-Manifesten). Empirisch bestaetigt: alle 15 Tasten mit
   ihrer eigenen Nummer beschriftet hochgeladen, Nutzer hat die tatsaechliche
   Anordnung am Geraet abgelesen und bestaetigt. Uebersetzung jetzt in
   `_key_index_to_device_key_id()` gekapselt.

**Beide Fixes live gegen echte Hardware verifiziert** (2026-08-21): ein Testbild
mit Beschriftung "OBEN-LINKS" auf `key_index=0` hochgeladen, Nutzer hat
bestaetigt dass es tatsaechlich oben links am Geraet erscheint.

**DECK ONE ist damit vollstaendig funktionsfaehig:** connect() (Wake+Clear),
set_brightness(), set_key_image() mit korrekter Positionierung, end_batch()
funktionieren alle nachweislich.

NACHTRAG (gleicher Tag): auch der Tastendruck-Lesepfad jetzt geloest und
verifiziert. Rohdaten-Format (Interrupt-IN, Endpoint 0x82) bestaetigt per
gezieltem Druecken/Loslassen mehrerer verschiedener Tasten mit Rohdaten-
Logging: `byte[9]` = 1-basierter Tastenindex in EINFACHER Lesereihenfolge
(oben-links=1, zeilenweise nach unten - identisch zu unserer eigenen
key_index-Konvention, KEINE Umrechnung wie beim Bild-Upload noetig),
`byte[10]` = 1 (gedrueckt) / 0 (losgelassen). Die vorherige `RAW_KEY_MAP`-
Tabelle (ungeprueft aus der Referenzbibliothek uebernommen) war falsch und
lieferte fuer die meisten Tasten ungueltige Indizes - jetzt durch die simple
Umrechnung `key_index = raw_key - 1` ersetzt. Vier verschiedene Tasten mit
sauberen Press+Release-Paaren getestet, alle korrekt.

**Damit ist DECK ONE komplett fertig: Verbindung, Helligkeit, Bild-Upload
(korrekt positioniert) und Tastendruck-Erkennung (Press+Release, korrekte
Tastenindizes) sind alle live gegen echte Hardware verifiziert.**

NACHTRAG 2026-09-03 (Windows-Testsession, siehe Z:/STREAMDECK_WINDOWS_TESTING.md):
Windows-Pfad ergaenzt. WICHTIGER FUND: die in der Testdoku vorgeschlagene
Zadig-Treiberumstellung (WinUSB/libusbK) ist NICHT noetig UND kontraproduktiv.
Getestet ohne jede Systemaenderung:
- `usb.backend.libusb1.get_backend()` liefert `None` - auf dieser Windows-
  Maschine fehlt komplett die libusb-1.0.dll (PyUSB waere so oder so nicht
  nutzbar, unabhaengig vom Treiber).
- Das Geraet ist ganz normal per Standard-HID sichtbar (`hid.enumerate(0x0100,
  0)` findet es sofort, Seriennummer 355499441494 - identisch zu der, die
  Streamplify Link selbst in seinen Logs meldet). Genau wie beim Elgato Mini
  spricht auch Streamplify Link DECK ONE offenbar ganz normal ueber HID an,
  nicht ueber ein WinUSB-Interface.
Deshalb: Windows-Pfad nutzt jetzt `hid` (dieselbe Bibliothek wie
elgato_mini.py), KEIN pyusb, KEIN Zadig, KEIN Treiberkonflikt mit Streamplify
Link. Einziger Unterschied zum Linux-Pfad: jedes Schreib-Kommando braucht ein
fuehrendes 0x00-Report-ID-Byte (Windows-HID-API-Konvention, wird von HidD_*
vor dem eigentlichen USB-Transfer wieder entfernt - deckt sich mit dem, was
die mirajazz-Rust-Referenz schon vor Monaten zeigte: "ReportID+CRT+DIS").
Live gegen echte Hardware verifiziert: connect() (DIS+CLE), set_brightness(),
set_key_image()+end_batch() UND der Tastendruck-Event-Loop laufen alle
fehlerfrei, gleiche Byte-Offsets wie im Linux-Pfad (kein Verschieben durch
die HID-Kapselung feststellbar, da das Geraet Report-ID 0 nutzt).
"""
from __future__ import annotations

import io
import logging
import struct
import sys
import threading
import time
from typing import Optional

from PIL import Image

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import hid
else:
    import usb.core
    import usb.util

from .base import DeviceInfo, KeyEventCallback, StreamDeckDevice

logger = logging.getLogger(__name__)

# KORREKTUR 2026-08-20: 0x320F:0x505A ist NICHT das DECK ONE, sondern die
# GMMK V2 96 Tastatur des Nutzers (Verwechslung in der urspruenglichen
# Windows-Analyse, siehe dokumentation/README.md "KRITISCHE KORREKTUR" und
# Claude-Memory project_streamdeck_vidpid_mixup). Echte DECK-ONE-ID per
# Aus-/Einstecken-Diff bestaetigt:
VENDOR_ID = 0x0100
PRODUCT_ID = 0x1000

_FORBIDDEN_KEYBOARD_VID_PID = (0x320F, 0x505A)

PACKET_SIZE = 512
NUM_KEYS = 15

CMD_PREFIX = b"CRT\x00\x00"
CMD_WAKE = b"DIS\x00\x00"
CMD_LIGHT_PREFIX = b"LIG\x00\x00"
# NEU 2026-08-21 (Windows-Mitschnitt): fehlte bisher komplett, gehoert laut
# echtem Traffic zwischen LIG und BAT in die connect()-Sequenz. Achtung, DREI
# Nullbytes zwischen "CLE" und dem Parameter (nicht zwei wie bei DIS/LIG) -
# exakt so im Mitschnitt bestaetigt: 43 4c 45 00 00 00 ff. Parameter 0xff so
# beobachtet (Bedeutung selbst unklar, evtl. "clear target = alle Tasten").
CMD_CLEAR = b"CLE\x00\x00\x00" + bytes([0xFF])
CMD_STOP = b"STP\x00\x00"
CMD_IMAGE_TOKEN = b"BAT\x00\x00"
EVENT_TOKEN = b"ACK\x00\x00OK"

# Referenz-KEY_MAP aus mirabox-streamdock-node (roher Report-Wert -> logischer
# Index), ungetestet gegen unsere eigene Hardware - siehe SETUP.md.
RAW_KEY_MAP = {i: (0x0B - (i - 1)) for i in range(1, 16)}  # 0x1->0x0b ... 0xf->0x?? (siehe SETUP.md Vorbehalt)

IMAGE_OUT_ENDPOINT = 0x01
EVENT_IN_ENDPOINT = 0x82

GRID_ROWS = 3
GRID_COLS = 5


def _key_index_to_device_key_id(key_index: int) -> int:
    """Uebersetzt unseren key_index (0-basiert, Lesereihenfolge oben-links zuerst,
    zeilenweise nach unten - passend zu den geparsten Profil-Manifesten) in die
    physische Geraete-Tastennummer (1-basiert). Empirisch am echten Geraet
    bestaetigt 2026-08-21 (15 durchnummerierte Testbilder hochgeladen, Nutzer hat
    die tatsaechliche Anordnung abgelesen): DECK ONE zaehlt seine Tasten von UNTEN
    LINKS zeilenweise nach OBEN, je Zeile links nach rechts (Zeile 1 unten = 1-5,
    Zeile 2 = 6-10, Zeile 3 oben = 11-15) - also genau umgekehrte Zeilenreihenfolge
    zu unserer eigenen (oben-links-zuerst) Konvention."""
    our_row, our_col = divmod(key_index, GRID_COLS)
    device_row = (GRID_ROWS - 1) - our_row
    return device_row * GRID_COLS + our_col + 1


def _framed(payload: bytes) -> bytes:
    packet = CMD_PREFIX + payload
    if len(packet) > PACKET_SIZE:
        raise ValueError(f"Kommando zu lang: {len(packet)} > {PACKET_SIZE}")
    return packet + bytes(PACKET_SIZE - len(packet))


class DeckOne(StreamDeckDevice):
    def __init__(self) -> None:
        self.info = DeviceInfo(
            name="Streamplify DECK ONE",
            vendor_id=VENDOR_ID,
            product_id=PRODUCT_ID,
            num_keys=NUM_KEYS,
            grid_rows=GRID_ROWS,
            grid_cols=GRID_COLS,
            image_size=(100, 100),
        )
        self._dev: Optional[object] = None
        self._detached_interfaces: list[int] = []
        self._event_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def connected(self) -> bool:
        return self._dev is not None

    def _write_frame(self, framed_payload: bytes) -> None:
        """Sendet ein bereits auf PACKET_SIZE aufgefuelltes Kommando-/Datenpaket.
        Wirft eine Exception bei Fehlschlag, sonst kein Rueckgabewert - identisch
        zum bisherigen usb.core-Verhalten, damit die aufrufenden Methoden
        unveraendert bleiben koennen."""
        if _IS_WINDOWS:
            # Windows-HID-API-Konvention: fuehrendes Report-ID-Byte (hier 0x00,
            # das Geraet nutzt keine echten Report-IDs) - wird von HidD_SetOutputReport
            # vor dem eigentlichen USB-Transfer entfernt, siehe Modul-Docstring.
            #
            # NEU 2026-09-03: live beobachtet, dass ein einzelner write() auch
            # NACH erfolgreichem open() gelegentlich mit Rueckgabewert -1
            # fehlschlaegt (gleiche USB-Instabilitaet wie beim Oeffnen selbst,
            # siehe connect()) - deshalb auch hier ein kurzer Retry, statt
            # sofort die ganze aufrufende Aktion (z.B. den kompletten
            # Verbindungsaufbau) scheitern zu lassen.
            last_exc: Optional[Exception] = None
            for attempt in range(3):
                try:
                    sent = self._dev.write(bytes([0x00]) + framed_payload)
                    if sent < 0:
                        raise OSError(f"HID write() fehlgeschlagen (Rueckgabewert {sent})")
                    return
                except OSError as exc:
                    last_exc = exc
                    time.sleep(0.2)
            raise last_exc
        else:
            self._dev.write(IMAGE_OUT_ENDPOINT, framed_payload, timeout=1000)

    def connect(self) -> bool:
        assert (VENDOR_ID, PRODUCT_ID) != _FORBIDDEN_KEYBOARD_VID_PID, (
            "Sicherheitssperre: 0x320F:0x505A ist die Tastatur des Nutzers, "
            "niemals per detach_kernel_driver()/claim_interface() anfassen."
        )
        if _IS_WINDOWS:
            # NEU 2026-09-03: kein pyusb/Zadig noetig, siehe Modul-Docstring -
            # das Geraet ist ganz normaler HID, exakt wie elgato_mini.py.
            # Live gegen echte Hardware beobachtet: das erste Oeffnen schlaegt
            # gelegentlich mit "open failed" fehl (Geraet kurzzeitig nicht
            # erreichbar, vermutlich dieselbe USB-Instabilitaet wie in der
            # urspruenglichen Wake-Analyse dokumentiert), ein zweiter Versuch
            # nach kurzer Pause funktioniert dann zuverlaessig - daher Retry.
            dev = None
            last_exc: Optional[Exception] = None
            OPEN_ATTEMPTS = 12
            for attempt in range(OPEN_ATTEMPTS):
                try:
                    dev = hid.device()
                    dev.open(VENDOR_ID, PRODUCT_ID)
                    break
                except (IOError, OSError) as exc:
                    last_exc = exc
                    dev = None
                    time.sleep(0.5)
            if dev is None:
                logger.warning(
                    "DECK ONE nicht erreichbar (HID), nach %s Versuchen: %s", OPEN_ATTEMPTS, last_exc,
                )
                return False
            dev.set_nonblocking(False)
            self._dev = dev
        else:
            try:
                dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
            except Exception as exc:
                logger.warning("DECK ONE: usb.core.find() fehlgeschlagen: %s", exc)
                return False
            if dev is None:
                logger.info("DECK ONE nicht gefunden (nicht angeschlossen?)")
                return False

            self._dev = dev
            self._detached_interfaces = []
            intf_num = 0
            try:
                if dev.is_kernel_driver_active(intf_num):
                    dev.detach_kernel_driver(intf_num)
                    self._detached_interfaces.append(intf_num)
            except (usb.core.USBError, NotImplementedError) as exc:
                logger.debug("DECK ONE: detach interface %s: %s", intf_num, exc)
            try:
                usb.util.claim_interface(dev, intf_num)
            except usb.core.USBError as exc:
                logger.debug("DECK ONE: claim interface %s: %s", intf_num, exc)

        # KORREKTUR: Wake-Kommando VOR jeder anderen Aktion - ohne dieses
        # Kommando nimmt das Geraet keinerlei weitere Interrupt-OUT-Daten an
        # (bestaetigt per Timeout-Test, behoben nach Fund der Referenz-Lib).
        try:
            self._write_frame(_framed(CMD_WAKE))
            logger.info("DECK ONE: Wake-Kommando gesendet")
        except Exception as exc:
            logger.warning("DECK ONE: Wake-Kommando fehlgeschlagen: %s", exc)
            return False

        # NEU 2026-08-21: im echten Windows-Mitschnitt folgt CLE direkt nach
        # DIS/LIG und vor dem ersten BAT-Bild-Upload - fehlte bisher komplett,
        # war die Ursache fuer den urspruenglichen Linux-Timeout, siehe
        # dokumentation/usb-protokoll-analyse.md Teil 3.
        try:
            self._write_frame(_framed(CMD_CLEAR))
            logger.info("DECK ONE: Clear-Kommando gesendet")
        except Exception as exc:
            logger.warning("DECK ONE: Clear-Kommando fehlgeschlagen: %s", exc)
            return False

        logger.info("DECK ONE verbunden")
        return True

    def disconnect(self) -> None:
        self.stop_event_loop()
        if self._dev is not None:
            if _IS_WINDOWS:
                try:
                    self._dev.close()
                except Exception:
                    pass
            else:
                try:
                    usb.util.dispose_resources(self._dev)
                except Exception:
                    pass
                for intf_num in self._detached_interfaces:
                    try:
                        self._dev.attach_kernel_driver(intf_num)
                    except Exception:
                        pass
            self._dev = None

    def set_brightness(self, percent: int) -> bool:
        if self._dev is None:
            return False
        percent = max(0, min(100, int(percent)))
        try:
            self._write_frame(_framed(CMD_LIGHT_PREFIX + bytes([percent])))
            return True
        except Exception as exc:
            logger.warning("DECK ONE: Helligkeit setzen fehlgeschlagen: %s", exc)
            return False

    def set_key_image(self, key_index: int, image: Image.Image, force: bool = True) -> bool:
        if self._dev is None:
            return False
        if not (0 <= key_index < NUM_KEYS):
            logger.error("DECK ONE: ungueltiger key_index %s", key_index)
            return False

        w, h = self.info.image_size
        img = image.convert("RGB").resize((w, h)).rotate(180)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        jpeg_bytes = buf.getvalue()

        key_id = _key_index_to_device_key_id(key_index)
        # KORRIGIERT 2026-08-21: eigene Analyse des Windows-Mitschnitts
        # (deckone-korrekt-20260821-wake-longwait.pcapng, 5 echte BAT-Header
        # verglichen) zeigt: Groesse ist 2 Byte big-endian (nicht 4), direkt
        # gefolgt vom 1-basierten Tastenindex - bestaetigt durch
        # ceil(groesse/512) == tatsaechliche Chunk-Anzahl in allen 5 Faellen
        # (z.B. 0x1c37=7223 Byte -> 15 Chunks, 0x13ed=5101 Byte -> 10 Chunks).
        # Die vorherige 4-Byte-Version hat den Tastenindex um 2 Byte
        # verschoben - das war vermutlich die Ursache fuer die falsch
        # positionierte Bildanzeige (unten links statt auf der Taste).
        header_payload = CMD_IMAGE_TOKEN + struct.pack(">H", len(jpeg_bytes)) + bytes([key_id])

        try:
            self._write_frame(_framed(header_payload))
            for i in range(0, len(jpeg_bytes), PACKET_SIZE):
                chunk = jpeg_bytes[i : i + PACKET_SIZE]
                if len(chunk) < PACKET_SIZE:
                    chunk = chunk + bytes(PACKET_SIZE - len(chunk))
                # Reine Datenpakete (keine CRT-Kommandohuelle) brauchen KEIN
                # _framed() - sie sind schon exakt PACKET_SIZE lang.
                self._write_frame(chunk)
            return True
        except Exception as exc:
            logger.error("DECK ONE Bild setzen fehlgeschlagen (Taste %s): %s", key_index, exc)
            return False

    def end_batch(self) -> bool:
        """Sendet das Abschluss-/Refresh-Kommando nach dem Hochladen aller
        Tasten einer Seite/eines Profils."""
        if self._dev is None:
            return False
        try:
            self._write_frame(_framed(CMD_STOP))
            return True
        except Exception as exc:
            logger.warning("DECK ONE: Abschluss-Kommando fehlgeschlagen: %s", exc)
            return False

    def start_event_loop(self, callback: KeyEventCallback) -> None:
        if self._dev is None:
            return
        self._stop_event.clear()

        # KORRIGIERT 2026-08-21: Lesepuffer war exakt PACKET_SIZE (512) - fuehrte
        # zu Errno 75 (EOVERFLOW) bei jedem einzelnen Leseversuch (bestaetigt
        # per Log, nachdem der Fehler durch das Logging-Level-Problem sichtbar
        # wurde), vermutlich weil mehrere Tastendruck-Reports beim Geraet
        # aufgestaut waren (nicht rechtzeitig ausgelesen) und zusammen mehr als
        # 512 Byte ergaben. Groesserer Lesepuffer (nur fuer den Lesevorgang,
        # das Schreib-Framing bleibt bei den protokoll-vorgegebenen 512 Byte).
        READ_BUFFER_SIZE = 4096

        def _run():
            last_state = [False] * NUM_KEYS
            consecutive_errors = 0
            if _IS_WINDOWS:
                self._dev.set_nonblocking(True)
            while not self._stop_event.is_set():
                if _IS_WINDOWS:
                    # hid.read() wirft bei Timeout KEINE Exception, sondern
                    # liefert einfach eine leere Liste zurueck - anderes
                    # Fehlermodell als usb.core, deshalb eigener Zweig statt
                    # in den bestehenden except-Block gequetscht.
                    try:
                        raw = self._dev.read(READ_BUFFER_SIZE, timeout_ms=300)
                    except (IOError, OSError) as exc:
                        consecutive_errors += 1
                        logger.warning(
                            "DECK ONE Event-Loop Lesefehler (#%s): %s", consecutive_errors, exc,
                        )
                        time.sleep(min(2.0, 0.2 * consecutive_errors))
                        continue
                    if not raw:
                        consecutive_errors = 0
                        continue
                    data = bytes(raw)
                    consecutive_errors = 0
                else:
                    try:
                        data = self._dev.read(EVENT_IN_ENDPOINT, READ_BUFFER_SIZE, timeout=300)
                        consecutive_errors = 0
                    except usb.core.USBError as exc:
                        if exc.errno in (110, None):  # 110 = ETIMEDOUT, normaler Poll-Timeout
                            continue
                        # KORRIGIERT 2026-08-21: vorher logger.debug() - bei INFO-Log-
                        # Level (Standard-Daemon-Config) war das komplett unsichtbar,
                        # daher schien die Ursache eines beobachteten Busy-Loop-Bugs
                        # (Thread bei 100% CPU, keine Events kommen mehr an) unklar.
                        # Echte Fehler NICHT-Timeout-Errno's koennen instant statt
                        # nach 300ms zurueckkommen (z.B. bei Geraete-Reset/Kabel-
                        # Wackelkontakt) - ohne diesen Sleep dreht die Schleife dann
                        # mit voller CPU-Last leer, ohne je wieder echte Daten zu
                        # bekommen.
                        consecutive_errors += 1
                        logger.warning(
                            "DECK ONE Event-Loop Lesefehler (errno=%s, #%s): %s",
                            exc.errno, consecutive_errors, exc,
                        )
                        # NEU 2026-09-03: bei dauerhaftem EOVERFLOW (leeres
                        # Zurueckweichen alleine half nicht - live beobachtet:
                        # Fehler #1 direkt nach frischem connect() bereits
                        # vorhanden, vermutlich ein am Geraet selbst
                        # aufgestauter Report-Puffer, der durch reines
                        # Schliessen/Neu-Oeffnen des Handles NICHT geleert
                        # wird) nach einer Weile einen echten USB-Port-Reset
                        # versuchen statt fuer immer alle 2s erfolglos weiter
                        # zu pollen - per usb.core.Device.reset() live
                        # getestet, danach war die Overflow-Schleife weg.
                        if consecutive_errors == 15:
                            logger.warning("DECK ONE: versuche USB-Reset nach anhaltendem Lesefehler")
                            try:
                                self._dev.reset()
                                time.sleep(1.0)
                                usb.util.claim_interface(self._dev, 0)
                                logger.info("DECK ONE: USB-Reset abgeschlossen, Event-Loop laeuft weiter")
                            except usb.core.USBError as reset_exc:
                                logger.warning("DECK ONE: USB-Reset fehlgeschlagen: %s", reset_exc)
                        time.sleep(min(2.0, 0.2 * consecutive_errors))
                        continue
                    data = bytes(data)
                # KORRIGIERT 2026-08-21: der vergroesserte Lesepuffer (siehe
                # oben, Fix fuer Errno 75) kann jetzt MEHRERE aufgestaute
                # Event-Reports in einem einzigen read() zurueckgeben, nicht
                # mehr nur den ersten - deshalb nach jedem Vorkommen des
                # "ACK..OK"-Tokens suchen statt nur Byte 9/10 vom Pufferanfang
                # zu lesen.
                offset = 0
                while True:
                    idx = data.find(EVENT_TOKEN, offset)
                    if idx == -1 or idx + 11 > len(data):
                        break
                    raw_key = data[idx + 9]
                    pressed = bool(data[idx + 10])
                    # KORRIGIERT 2026-08-21: empirisch mit gezieltem Druecken
                    # zweier verschiedener Tasten bestaetigt (oben-links ->
                    # raw_key=1, unten-rechts -> raw_key=15, Press=1/Release=0)
                    # - der Tastendruck-Report nutzt bereits unsere eigene
                    # Lesereihenfolge (oben-links zuerst), KEINE Umrechnung wie
                    # beim Bild-Upload noetig. Die vorherige RAW_KEY_MAP-
                    # Tabelle stammte ungeprueft aus einer fremden Referenz-
                    # bibliothek und lieferte fuer die meisten raw_key-Werte
                    # ungueltige/negative Indizes.
                    key_index = raw_key - 1
                    if 0 <= key_index < NUM_KEYS:
                        if pressed != last_state[key_index]:
                            last_state[key_index] = pressed
                            try:
                                callback(key_index, pressed)
                            except Exception:
                                logger.exception("Fehler im DECK ONE Key-Callback")
                    else:
                        logger.debug("DECK ONE: unbekannter Rohindex %s, Rohdaten: %s", raw_key, data[idx:idx + 16].hex())
                    offset = idx + 11

        self._event_thread = threading.Thread(
            target=_run, name="deckone-events", daemon=True
        )
        self._event_thread.start()

    def stop_event_loop(self) -> None:
        self._stop_event.set()
        if self._event_thread is not None:
            self._event_thread.join(timeout=2)
            self._event_thread = None
