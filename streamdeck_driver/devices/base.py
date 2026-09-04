"""Gemeinsames Geraete-Interface fuer Elgato Stream Deck Mini und Streamplify DECK ONE.

Beide Implementierungen (elgato_mini.py, deckone.py) erben von StreamDeckDevice und
setzen dieselbe kleine Schnittstelle um, damit der Daemon (daemon.py) beide Geraete
identisch behandeln kann, ohne geraetespezifischen Code zu enthalten.
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from PIL import Image

logger = logging.getLogger(__name__)

# Signatur fuer den Tastendruck-Callback: (key_index_0basiert, pressed: bool)
KeyEventCallback = Callable[[int, bool], None]


@dataclass
class DeviceInfo:
    name: str
    vendor_id: int
    product_id: int
    num_keys: int
    grid_rows: int
    grid_cols: int
    image_size: tuple  # (width, height) in Pixeln, wie vom Geraet erwartet


class StreamDeckDevice(abc.ABC):
    """Abstraktes Interface. Alle Methoden muessen fehlertolerant sein - ein
    nicht angeschlossenes oder gerade abgezogenes Geraet darf den Daemon nicht
    zum Absturz bringen (siehe Aufgabenstellung: "grazil weiterlaufen").
    """

    info: DeviceInfo

    @abc.abstractmethod
    def connect(self) -> bool:
        """Versucht die Verbindung aufzubauen. Gibt True/False zurueck,
        wirft NIE eine Exception nach aussen (faengt intern ab und loggt)."""

    @abc.abstractmethod
    def disconnect(self) -> None:
        ...

    @property
    @abc.abstractmethod
    def connected(self) -> bool:
        ...

    @abc.abstractmethod
    def set_brightness(self, percent: int) -> bool:
        """0-100. Gibt True bei Erfolg zurueck."""

    @abc.abstractmethod
    def set_key_image(self, key_index: int, image: Image.Image) -> bool:
        """key_index ist 0-basiert (Position im Grid, geraeteinterne Adressierung
        wird von der jeweiligen Implementierung selbst umgerechnet). image ist ein
        PIL Image beliebiger Groesse - wird intern auf info.image_size skaliert."""

    @abc.abstractmethod
    def start_event_loop(self, callback: KeyEventCallback) -> None:
        """Startet einen Hintergrund-Thread, der Tastendruck-Events liest und
        callback(key_index_0basiert, pressed) aufruft."""

    @abc.abstractmethod
    def stop_event_loop(self) -> None:
        ...
