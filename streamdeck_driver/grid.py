"""Generische Tasten-Grid-Geometrie: Zeilen/Spalten, Kachelgroesse in Pixeln,
Luecken-Korrektur (Bezel zwischen physischen Tasten). Basis fuer alles, was
ein grosses Bild komponiert und in Einzelkacheln zerschneidet - urspruenglich
nur in radar.py fest auf die 5x3/15-Tasten-Geometrie der DECK ONE verdrahtet,
jetzt als eigenes Objekt extrahiert, damit `radar.py` UND neue Features
(z.B. eine Standort-Karte) dieselbe Logik fuer beliebige Geraete-Grids nutzen
koennen (Elgato Mini 2x3, XL 4x8, ...), statt jedes Mal neu zu bauen.

WICHTIG: reiner Geometrie-Umbau, keine Verhaltensaenderung - radar.py nutzt
weiterhin exakt dieselben Zahlen wie vorher (DECKONE_GRID unten), nur jetzt
aus einem gemeinsamen Objekt bezogen statt als lose Modul-Konstanten."""
from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image


@dataclass(frozen=True)
class Grid:
    cols: int
    rows: int
    tile_px: int
    # None = automatisch aus dem an der DECK ONE nachgemessenen Bezel-
    # Verhaeltnis (Taste 1,3cm, Luecke 0,9cm) abgeleitet - andere Geraete
    # koennen einen eigenen gap_px uebergeben, falls das Verhaeltnis abweicht.
    gap_px: int = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.gap_px is None:
            object.__setattr__(self, "gap_px", round(self.tile_px * 0.9 / 1.3))

    @property
    def num_keys(self) -> int:
        return self.cols * self.rows

    @property
    def canvas_w(self) -> int:
        return self.cols * self.tile_px

    @property
    def canvas_h(self) -> int:
        return self.rows * self.tile_px

    @property
    def effective_w(self) -> int:
        """Inklusive der 'verdeckten' Luecken-Pixel zwischen den Kacheln -
        das ist die Breite, die man beim Kartenbild anfordern muss, damit
        Inhalte ueber die physischen Tastenraender hinweg weiterlaufen."""
        return self.canvas_w + (self.cols - 1) * self.gap_px

    @property
    def effective_h(self) -> int:
        return self.canvas_h + (self.rows - 1) * self.gap_px

    def cell_origin(self, col: int, row: int) -> tuple[int, int]:
        """Obere linke Ecke der sichtbaren tile_px x tile_px-Flaeche fuer
        (col,row) im effective_w x effective_h-Bild."""
        return col * (self.tile_px + self.gap_px), row * (self.tile_px + self.gap_px)

    def key_index_to_cell(self, key_index: int) -> tuple[int, int]:
        """Row-major Tastenindex (0..num_keys-1) -> (col, row)."""
        row, col = divmod(key_index, self.cols)
        return col, row

    def cell_to_key_index(self, col: int, row: int) -> int:
        return row * self.cols + col

    def slice_tiles(self, canvas: Image.Image) -> dict[int, Image.Image]:
        """Zerschneidet ein effective_w x effective_h-Bild in die einzelnen
        Tasten-Kacheln (row-major Index), ueberspringt dabei die gap_px-
        Luecken zwischen den Zellen (siehe cell_origin)."""
        tiles = {}
        for row in range(self.rows):
            for col in range(self.cols):
                x0, y0 = self.cell_origin(col, row)
                box = (x0, y0, x0 + self.tile_px, y0 + self.tile_px)
                tiles[self.cell_to_key_index(col, row)] = canvas.crop(box)
        return tiles


# Bekannte Geraete-Grids - bei Bedarf um weitere Modelle ergaenzen (siehe
# streamdeck_driver/devices/elgato_generic.py fuer die jeweilige
# Tasten-/Bildgroesse; gap_px muesste am echten Geraet nachgemessen werden,
# bis dahin faellt es auf die DECK-ONE-Naeherung zurueck).
DECKONE_GRID = Grid(cols=5, rows=3, tile_px=100)
ELGATO_MINI_GRID = Grid(cols=3, rows=2, tile_px=80)
