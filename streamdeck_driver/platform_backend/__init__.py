"""OS-Abstraktionsschicht fuer alles, was zwingend plattformspezifische
System-Aufrufe braucht (Hotkey-Injection, Screenshot, App-Lautstaerke,
URL/Programm oeffnen, Ton abspielen, Popup-Anzeige). Der Rest des Treibers
(USB/HID-Geraetezugriff, Icon-Rendering, Radar, Home-Assistant-Client,
Timer-Zustandsautomat, CPU/RAM-Monitoring) ist BEREITS OS-unabhaengig -
entweder reines Python/PIL, oder baut auf echten Cross-Platform-Bibliotheken
auf (psutil, hidapi, PyUSB/libusb, requests) und brauchte fuer den geplanten
Portabilitaets-Umbau keine Aenderung.

WICHTIG: Nur der Linux-Pfad ist gegen echte Hardware/echtes System getestet
(alles andere in diesem Projekt laeuft ausschliesslich auf Linux). Windows-
und macOS-Backend sind nach den jeweils dokumentierten Standard-APIs
geschrieben, aber UNGETESTET - vor produktivem Einsatz auf einer echten
Windows-/Mac-Maschine verifizieren, siehe die '# UNGETESTET'-Kommentare in
windows.py/macos.py fuer die riskanteren Stellen."""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger("streamdeck_driver.platform_backend")

if sys.platform.startswith("linux"):
    from . import linux as backend
    PLATFORM = "linux"
elif sys.platform == "win32":
    from . import windows as backend
    PLATFORM = "windows"
elif sys.platform == "darwin":
    from . import macos as backend
    PLATFORM = "darwin"
else:
    from . import unsupported as backend
    PLATFORM = "unsupported"

logger.info("Platform-Backend geladen: %s", PLATFORM)

# Oeffentliche Schnittstelle, von actions.py/timer_engine.py/process_monitor.py
# genutzt - jedes Backend-Modul (linux/windows/macos/unsupported) implementiert
# exakt diese Funktionen mit identischer Signatur.
send_hotkey = backend.send_hotkey
open_command = backend.open_command
open_url = backend.open_url
take_screenshot_interactive = backend.take_screenshot_interactive
set_app_volume = backend.set_app_volume
play_sound = backend.play_sound
show_message_popup = backend.show_message_popup
get_active_app_id = backend.get_active_app_id
