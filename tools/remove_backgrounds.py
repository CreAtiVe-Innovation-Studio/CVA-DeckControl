#!/usr/bin/env python3
"""Stanzt den Hintergrund aus den generierten Avatar-Posen aus, per
ML-Subjekt-Segmentierung (rembg, Modell 'isnet-anime' - auf Anime-/Comic-
Stil-Kunst trainiert, passt zum valent1n-Charakterstil).

Ausfuehren mit einem Python, das rembg+onnxruntime installiert hat, z.B.:
  /home/alien/cva-linux/comfyui-venv/bin/python3 tools/remove_backgrounds.py
(dort schon vorhanden, siehe 'uv pip install --python .../comfyui-venv/bin/python3 rembg onnxruntime')

WARUM nicht mehr die urspruengliche Flood-Fill-Variante (nur reinweisser,
zusammenhaengender Rand-Hintergrund wird transparent): funktioniert nur bei
Bildern mit echtem Weiss-Hintergrund. Einige Posen (v.a. 'gewitter'/
'gewitter_massive' mit Regen-/Gewitterhimmel im Hintergrund) haben einen
farbigen/verlaufenden Hintergrund, den ein reiner Weiss-Schwellwert komplett
uebersieht - blieb dann faelschlich voll deckend (Bug gefunden 2026-09-03,
User-Report: "manche der bilder bei gewitter haben noch hintergrund").
ML-Segmentierung erkennt das Subjekt unabhaengig von der Hintergrundfarbe.

Ueberschreibt die PNGs unter assets/generated-avatars/ in place (RGBA).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from rembg import new_session, remove

AVATAR_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "generated-avatars"
MODEL = "isnet-anime"


def main() -> None:
    pngs = sorted(AVATAR_DIR.rglob("*.png"))
    if not pngs:
        print(f"Keine PNGs unter {AVATAR_DIR} gefunden.")
        return
    session = new_session(MODEL)
    for path in pngs:
        img = Image.open(path).convert("RGBA")
        out = remove(img, session=session)
        out.save(path)
        print(f"freigestellt: {path}")


if __name__ == "__main__":
    main()
