"""Tests fuer streamdeck_driver/grid.py - reine Geometrie, kein Hardware-/
Netzwerkzugriff, deshalb ohne Mocks direkt testbar."""
from PIL import Image

from streamdeck_driver.grid import DECKONE_GRID, Grid


def test_deckone_grid_matches_known_hardware_measurements():
    """Diese Zahlen sind gegen die echte DECK ONE verifiziert (siehe
    CLAUDE.md/SEITEN-LOGIK.md) - ein versehentlicher Wertewechsel hier waere
    ein echter Hardware-Regressions-Bug, kein reines Refactoring."""
    assert (DECKONE_GRID.cols, DECKONE_GRID.rows, DECKONE_GRID.tile_px) == (5, 3, 100)
    assert DECKONE_GRID.gap_px == 69  # round(100 * 0.9 / 1.3)
    assert (DECKONE_GRID.canvas_w, DECKONE_GRID.canvas_h) == (500, 300)
    assert (DECKONE_GRID.effective_w, DECKONE_GRID.effective_h) == (776, 438)


def test_gap_px_auto_derives_from_bezel_ratio():
    g = Grid(cols=2, rows=2, tile_px=200)
    assert g.gap_px == round(200 * 0.9 / 1.3)


def test_gap_px_explicit_override_is_respected():
    g = Grid(cols=2, rows=2, tile_px=200, gap_px=10)
    assert g.gap_px == 10


def test_num_keys():
    assert DECKONE_GRID.num_keys == 15
    assert Grid(cols=6, rows=1, tile_px=80).num_keys == 6


def test_cell_origin_top_left_is_zero():
    assert DECKONE_GRID.cell_origin(0, 0) == (0, 0)


def test_cell_origin_spacing_includes_gap():
    g = DECKONE_GRID
    x0, _ = g.cell_origin(0, 0)
    x1, _ = g.cell_origin(1, 0)
    assert x1 - x0 == g.tile_px + g.gap_px


def test_key_index_to_cell_row_major():
    # Taste 0 = oben links, Taste 4 = Ende der ersten Reihe, Taste 5 = Beginn Reihe 2
    assert DECKONE_GRID.key_index_to_cell(0) == (0, 0)
    assert DECKONE_GRID.key_index_to_cell(4) == (4, 0)
    assert DECKONE_GRID.key_index_to_cell(5) == (0, 1)
    assert DECKONE_GRID.key_index_to_cell(14) == (4, 2)


def test_cell_to_key_index_is_inverse_of_key_index_to_cell():
    g = DECKONE_GRID
    for idx in range(g.num_keys):
        col, row = g.key_index_to_cell(idx)
        assert g.cell_to_key_index(col, row) == idx


def test_slice_tiles_returns_one_tile_per_key_at_correct_size():
    g = DECKONE_GRID
    canvas = Image.new("RGB", (g.effective_w, g.effective_h), (0, 0, 0))
    tiles = g.slice_tiles(canvas)
    assert len(tiles) == g.num_keys
    assert set(tiles.keys()) == set(range(g.num_keys))
    for tile in tiles.values():
        assert tile.size == (g.tile_px, g.tile_px)


def test_slice_tiles_skips_the_gap_between_tiles():
    """Faerbt nur die allererste Kachel-Flaeche ein und prueft, dass die
    NAECHSTE Kachel (durch die Luecke getrennt) das nicht mitbekommt -
    stellt sicher, dass cell_origin() wirklich den Luecken-Versatz einbaut,
    nicht nur cols*tile_px."""
    g = Grid(cols=2, rows=1, tile_px=10, gap_px=5)
    canvas = Image.new("RGB", (g.effective_w, g.effective_h), (0, 0, 0))
    for x in range(g.tile_px):
        for y in range(g.tile_px):
            canvas.putpixel((x, y), (255, 0, 0))
    tiles = g.slice_tiles(canvas)
    assert tiles[0].getpixel((0, 0)) == (255, 0, 0)
    assert tiles[1].getpixel((0, 0)) == (0, 0, 0)
