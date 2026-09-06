"""Rendert die Tastenbilder: entweder ein vorhandenes Asset-PNG (skaliert) oder
ein generiertes Icon (Karten-Look mit abgerundeten Ecken, Farbverlauf,
zentralem Symbol + Titeltext) fuer Tasten ohne eigenes Bild-Asset."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .paths import project_root

PROJECT_ROOT = project_root()

# NEU 2026-09-03 (Windows-Testsession): Kandidatenliste enthielt nur Linux-
# Schriftpfade - unter Windows existierte keiner davon, ImageFont.load_default()
# griff (winziger Bitmap-Font, keine Groessenskalierung moeglich) - betraf ALLE
# gerenderten Icons, nicht nur die Statistik-Ansicht. Windows-Standardschriften
# ergaenzt (auf jeder Windows-Installation vorhanden, kein Extra-Download noetig).
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/tahomabd.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# Ein stimmiger dunkler Farbfamilien-Satz (Hintergrund-Start/-Ende) je
# Aktionstyp, alle mit aehnlicher Saettigung/Helligkeit fuer ein
# zusammenhaengendes Gesamtbild - nur der Farbton wechselt.
_TYPE_STYLE = {
    "hotkey":         ((64, 51, 122),  (36, 27, 74),  (255, 196, 74)),
    "open":           ((23, 97, 92),   (13, 58, 55),  (255, 255, 255)),
    "open_sequence":  ((23, 97, 92),   (13, 58, 55),  (255, 255, 255)),
    "website":        ((24, 84, 130),  (13, 48, 76),  (255, 255, 255)),
    "page_previous":  ((58, 62, 74),   (30, 33, 41),  (255, 255, 255)),
    "page_next":      ((58, 62, 74),   (30, 33, 41),  (255, 255, 255)),
    "switch_profile": ((110, 40, 110), (64, 20, 64),  (255, 255, 255)),
    "app_volume":     ((20, 90, 100),  (10, 50, 58),  (255, 255, 255)),
    "open_gui":       ((70, 70, 92),   (34, 34, 46),  (255, 255, 255)),
    "unmapped":       ((120, 45, 45),  (68, 22, 22),  (255, 200, 200)),
    "ha_toggle":      ((130, 100, 20), (74, 56, 10),  (255, 224, 130)),
    "ha_cover":       ((58, 68, 84),   (30, 36, 46),  (255, 255, 255)),
}
_DEFAULT_STYLE = ((36, 90, 150), (18, 52, 90), (255, 255, 255))


def _gradient_bg(size: tuple[int, int], top: tuple, bottom: tuple) -> Image.Image:
    w, h = size
    base = Image.new("RGB", (1, h), top)
    px = base.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
        )
    return base.resize((w, h))


# switch_profile-Tasten sahen bisher IMMER identisch aus (derselbe Pfeil-
# Wirbel), egal welches Profil sie anspringen - auf dem Elgato Mini (reine
# Moduswahl, oft >10 Profile ueber mehrere Seiten) macht das die Tasten
# untereinander ununterscheidbar bis auf den Titeltext. Keyword-Suche im
# Profilnamen statt einer festen Tabelle, damit sowohl die echten
# Profilnamen (streaming/timer/wo_ist/...) als auch frei erfundene Namen in
# profiles.example.yaml (z.B. 'musik') automatisch ein passendes Symbol
# bekommen, ohne dass fuer jedes neue eigene Profil Code angefasst werden muss.
_PROFILE_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("timer", "pomodoro"), "clock"),
    (("wo_ist", "standort", "ort", "location"), "pin"),
    (("radar",), "radar"),
    (("wetter", "weather", "regen", "rain"), "cloud"),
    (("home", "zuhause", "heim"), "house"),
    (("favorit",), "star"),
    (("system", "stats"), "gauge"),
    (("ki", "ai"), "chip"),
    (("kommunikation", "chat", "mail"), "chat"),
    (("coding", "code", "dev", "programm"), "code"),
    (("gaming", "spiel", "game"), "controller"),
    (("audio", "musik", "sound", "music"), "headphones"),
    (("nachhilfe", "studium", "schule", "lernen", "study"), "book"),
    (("kreativ", "design", "creative"), "palette"),
    (("streaming", "stream"), "tower"),
]


def _resolve_profile_symbol(profile: str) -> str | None:
    name = profile.lower()
    for keywords, symbol in _PROFILE_KEYWORDS:
        if any(kw in name for kw in keywords):
            return symbol
    return None


def _draw_profile_symbol(draw: ImageDraw.ImageDraw, symbol: str, cx: int, cy: int, s: int, lw: int, accent: tuple) -> None:
    if symbol == "clock":
        r = int(s * 0.24)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=accent, width=lw)
        draw.line([cx, cy, cx, cy - r * 0.6], fill=accent, width=max(2, lw - 1))
        draw.line([cx, cy, cx + r * 0.45, cy + r * 0.1], fill=accent, width=max(2, lw - 1))
    elif symbol == "pin":
        r = int(s * 0.18)
        top_cy = cy - r * 0.3
        draw.ellipse([cx - r, top_cy - r, cx + r, top_cy + r], outline=accent, width=lw)
        draw.polygon([(cx - r * 0.55, top_cy + r * 0.7), (cx + r * 0.55, top_cy + r * 0.7), (cx, top_cy + r * 2.1)], fill=accent)
    elif symbol == "radar":
        for frac in (0.12, 0.2, 0.28):
            r = int(s * frac)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=accent, width=max(2, lw - 1))
        r = int(s * 0.28)
        draw.line([cx, cy, cx + r * 0.9, cy - r * 0.6], fill=accent, width=lw)
    elif symbol == "cloud":
        r = int(s * 0.16)
        draw.ellipse([cx - r * 1.6, cy - r * 0.2, cx - r * 0.2, cy + r * 1.1], fill=accent)
        draw.ellipse([cx - r * 0.5, cy - r * 0.9, cx + r * 0.9, cy + r * 0.5], fill=accent)
        draw.ellipse([cx + r * 0.1, cy - r * 0.2, cx + r * 1.7, cy + r * 1.1], fill=accent)
        draw.rectangle([cx - r * 1.2, cy + r * 0.3, cx + r * 1.3, cy + r * 1.1], fill=accent)
    elif symbol == "house":
        hw, hh = int(s * 0.26), int(s * 0.2)
        x0, y0 = cx - hw, cy + hh * 0.2
        draw.rectangle([x0, y0, x0 + 2 * hw, y0 + hh], outline=accent, width=lw)
        draw.polygon([(x0 - hw * 0.15, y0), (cx, y0 - hh * 1.3), (x0 + 2 * hw + hw * 0.15, y0)], outline=accent, width=lw)
    elif symbol == "star":
        r_out, r_in = int(s * 0.26), int(s * 0.11)
        pts = []
        for i in range(10):
            r = r_out if i % 2 == 0 else r_in
            ang = math.radians(-90 + i * 36)
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        draw.polygon(pts, fill=accent)
    elif symbol == "gauge":
        r = int(s * 0.26)
        draw.arc([cx - r, cy - r * 0.3, cx + r, cy + r * 1.7], start=180, end=360, fill=accent, width=lw)
        draw.line([cx, cy + r * 0.5, cx + r * 0.7, cy - r * 0.05], fill=accent, width=max(2, lw - 1))
    elif symbol == "chip":
        r = int(s * 0.18)
        draw.rectangle([cx - r, cy - r, cx + r, cy + r], outline=accent, width=lw)
        pin_len = int(s * 0.08)
        for frac in (-0.5, 0.5):
            y = cy + frac * r
            draw.line([cx - r - pin_len, y, cx - r, y], fill=accent, width=max(2, lw - 1))
            draw.line([cx + r, y, cx + r + pin_len, y], fill=accent, width=max(2, lw - 1))
    elif symbol == "chat":
        bw, bh = int(s * 0.5), int(s * 0.32)
        x0, y0 = cx - bw // 2, cy - bh // 2
        draw.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=int(bh * 0.3), outline=accent, width=lw)
        draw.polygon([(x0 + bw * 0.2, y0 + bh), (x0 + bw * 0.35, y0 + bh), (x0 + bw * 0.15, y0 + bh * 1.4)], fill=accent)
    elif symbol == "code":
        r = int(s * 0.2)
        draw.line([cx - r * 1.6, cy - r * 0.7, cx - r * 0.6, cy], fill=accent, width=lw)
        draw.line([cx - r * 0.6, cy, cx - r * 1.6, cy + r * 0.7], fill=accent, width=lw)
        draw.line([cx + r * 1.6, cy - r * 0.7, cx + r * 0.6, cy], fill=accent, width=lw)
        draw.line([cx + r * 0.6, cy, cx + r * 1.6, cy + r * 0.7], fill=accent, width=lw)
    elif symbol == "controller":
        bw, bh = int(s * 0.5), int(s * 0.24)
        x0, y0 = cx - bw // 2, cy - bh // 2
        draw.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=int(bh * 0.5), outline=accent, width=lw)
        dr = max(2, int(s * 0.03))
        for dy in (-bh * 0.15, bh * 0.15):
            bx, by = x0 + bw * 0.78, y0 + bh * 0.5 + dy
            draw.ellipse([bx - dr, by - dr, bx + dr, by + dr], fill=accent)
        px, py = x0 + bw * 0.28, y0 + bh * 0.5
        draw.line([px - bh * 0.2, py, px + bh * 0.2, py], fill=accent, width=max(2, lw - 1))
        draw.line([px, py - bh * 0.2, px, py + bh * 0.2], fill=accent, width=max(2, lw - 1))
    elif symbol == "headphones":
        r = int(s * 0.24)
        draw.arc([cx - r, cy - r * 0.3, cx + r, cy + r * 0.9], start=180, end=360, fill=accent, width=lw)
        cw, ch = int(s * 0.12), int(s * 0.22)
        draw.rounded_rectangle([cx - r - cw * 0.3, cy + r * 0.3, cx - r + cw * 0.7, cy + r * 0.3 + ch], radius=int(cw * 0.4), fill=accent)
        draw.rounded_rectangle([cx + r - cw * 0.7, cy + r * 0.3, cx + r + cw * 0.3, cy + r * 0.3 + ch], radius=int(cw * 0.4), fill=accent)
    elif symbol == "book":
        bw, bh = int(s * 0.46), int(s * 0.32)
        x0, y0 = cx - bw // 2, cy - bh // 2
        draw.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=int(bh * 0.12), outline=accent, width=lw)
        draw.line([cx, y0 + lw, cx, y0 + bh - lw], fill=accent, width=lw)
        rw = int(bw * 0.14)
        rx = x0 + bw * 0.7
        draw.polygon(
            [(rx, y0), (rx + rw, y0), (rx + rw, y0 + bh * 0.42), (rx + rw / 2, y0 + bh * 0.3), (rx, y0 + bh * 0.42)],
            fill=accent,
        )
    elif symbol == "palette":
        r = int(s * 0.24)
        draw.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.9], outline=accent, width=lw)
        dr = max(2, int(s * 0.035))
        for ang in (200, 260, 320, 20):
            rad = math.radians(ang)
            px, py = cx + r * 0.55 * math.cos(rad), cy + r * 0.4 * math.sin(rad)
            draw.ellipse([px - dr, py - dr, px + dr, py + dr], fill=accent)
    elif symbol == "tower":
        r = max(2, int(s * 0.05))
        draw.line([cx, cy - s * 0.22, cx, cy + s * 0.22], fill=accent, width=lw)
        draw.ellipse([cx - r, cy - s * 0.22 - r, cx + r, cy - s * 0.22 + r], fill=accent)
        for rad_frac in (0.12, 0.2):
            rr = int(s * rad_frac)
            box = [cx - rr, cy - s * 0.22 - rr, cx + rr, cy - s * 0.22 + rr]
            draw.arc(box, start=-60, end=60, fill=accent, width=max(2, lw - 1))
            draw.arc(box, start=120, end=240, fill=accent, width=max(2, lw - 1))


def _draw_symbol(draw: ImageDraw.ImageDraw, action_type: str, size: tuple[int, int], accent: tuple, profile: str = "") -> None:
    """Groesseres, klareres Symbol im oberen Bereich der Karte (nimmt ~40%
    der Kartenhoehe ein, statt vorher ~15%)."""
    w, h = size
    cx, cy = w // 2, int(h * 0.36)
    s = min(w, h)
    lw = max(3, s // 18)

    if action_type == "hotkey":
        kw, kh = int(s * 0.5), int(s * 0.32)
        x0, y0 = cx - kw // 2, cy - kh // 2
        draw.rounded_rectangle([x0, y0, x0 + kw, y0 + kh], radius=int(kh * 0.3), outline=accent, width=lw)
        # kleine Tasten-Andeutung innerhalb
        gap = kw // 5
        for i in range(3):
            gx = x0 + gap * (i + 1)
            draw.line([gx, y0 + kh * 0.35, gx, y0 + kh * 0.65], fill=accent, width=max(2, lw // 2))
    elif action_type in ("open", "open_sequence"):
        fw, fh = int(s * 0.56), int(s * 0.36)
        x0, y0 = cx - fw // 2, cy - fh // 2 + fh * 0.12
        draw.polygon(
            [(x0, y0), (x0 + fw * 0.38, y0), (x0 + fw * 0.48, y0 - fh * 0.28),
             (x0 + fw, y0 - fh * 0.28), (x0 + fw, y0 + fh), (x0, y0 + fh)],
            fill=accent,
        )
    elif action_type == "website":
        r = int(s * 0.23)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=accent, width=lw)
        draw.ellipse([cx - r * 0.45, cy - r, cx + r * 0.45, cy + r], outline=accent, width=max(2, lw - 1))
        draw.line([cx - r, cy, cx + r, cy], fill=accent, width=max(2, lw - 1))
    elif action_type == "page_previous":
        r = int(s * 0.24)
        draw.polygon([(cx + r * 0.55, cy - r), (cx - r * 0.7, cy), (cx + r * 0.55, cy + r)], fill=accent)
    elif action_type == "page_next":
        r = int(s * 0.24)
        draw.polygon([(cx - r * 0.55, cy - r), (cx + r * 0.7, cy), (cx - r * 0.55, cy + r)], fill=accent)
    elif action_type == "switch_profile":
        symbol = _resolve_profile_symbol(profile) if profile else None
        if symbol is not None:
            _draw_profile_symbol(draw, symbol, cx, cy, s, lw, accent)
        else:
            r = int(s * 0.22)
            draw.arc([cx - r, cy - r, cx + r, cy + r], start=25, end=305, fill=accent, width=lw)
            draw.polygon(
                [(cx + r * 0.9, cy - r * 0.55), (cx + r * 1.45, cy - r * 0.1), (cx + r * 0.75, cy + r * 0.2)],
                fill=accent,
            )
    elif action_type == "app_volume":
        bw, bh = int(s * 0.16), int(s * 0.26)
        x0, y0 = cx - int(s * 0.28), cy - bh // 2
        draw.rectangle([x0, y0, x0 + bw, y0 + bh], fill=accent)
        draw.polygon(
            [(x0 + bw, y0 - bh * 0.35), (x0 + bw + int(s * 0.14), y0 - bh * 0.75),
             (x0 + bw + int(s * 0.14), y0 + bh * 1.75), (x0 + bw, y0 + bh * 1.35)],
            fill=accent,
        )
        for r in (int(s * 0.15), int(s * 0.24)):
            draw.arc([cx + int(s * 0.02) - r, cy - r, cx + int(s * 0.02) + r, cy + r], start=-35, end=35, fill=accent, width=max(2, lw - 1))
    elif action_type == "open_gui":
        r_outer, r_inner = int(s * 0.24), int(s * 0.1)
        for i in range(8):
            angle = i * (360 / 8)
            rad = math.radians(angle)
            x1, y1 = cx + r_outer * 0.72 * math.cos(rad), cy + r_outer * 0.72 * math.sin(rad)
            x2, y2 = cx + r_outer * 1.15 * math.cos(rad), cy + r_outer * 1.15 * math.sin(rad)
            draw.line([x1, y1, x2, y2], fill=accent, width=lw)
        draw.ellipse([cx - r_outer * 0.72, cy - r_outer * 0.72, cx + r_outer * 0.72, cy + r_outer * 0.72], outline=accent, width=lw)
        draw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner], fill=accent)
    elif action_type == "unmapped":
        r = int(s * 0.26)
        draw.polygon([(cx, cy - r), (cx - r * 0.95, cy + r * 0.8), (cx + r * 0.95, cy + r * 0.8)], outline=accent, width=lw)
        draw.line([cx, cy - r * 0.15, cx, cy + r * 0.35], fill=accent, width=lw)
        dr = max(2, lw // 2 + 1)
        draw.ellipse([cx - dr, cy + r * 0.55 - dr, cx + dr, cy + r * 0.55 + dr], fill=accent)
    elif action_type == "ha_toggle":
        r = int(s * 0.18)
        draw.ellipse([cx - r, cy - r * 1.1, cx + r, cy + r * 1.1], outline=accent, width=lw)
        draw.line([cx - r * 0.4, cy + r * 1.1, cx + r * 0.4, cy + r * 1.1], fill=accent, width=lw)
        draw.line([cx - r * 0.3, cy + r * 1.5, cx + r * 0.3, cy + r * 1.5], fill=accent, width=max(2, lw - 1))
    elif action_type == "ha_cover":
        r = int(s * 0.16)
        draw.polygon([(cx - r, cy - r * 0.2), (cx, cy - r * 0.9), (cx + r, cy - r * 0.2)], outline=accent, width=lw)
        draw.polygon([(cx - r, cy + r * 0.9), (cx, cy + r * 0.2), (cx + r, cy + r * 0.9)], outline=accent, width=lw)
    else:
        r = int(s * 0.18)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=accent, width=lw)


def render_generated_icon(size: tuple[int, int], title: str, action_type: str = "", profile: str = "") -> Image.Image:
    w, h = size
    top, bottom, accent = _TYPE_STYLE.get(action_type, _DEFAULT_STYLE)

    # Karten-Look: dunkler Rand + abgerundete, farbige Innenflaeche mit
    # weichem Schatten, statt eines randlosen Vollflaechen-Verlaufs.
    margin = max(2, int(min(w, h) * 0.035))
    radius = max(6, int(min(w, h) * 0.14))

    img = Image.new("RGB", (w, h), (8, 8, 10))
    card = _gradient_bg((w - 2 * margin, h - 2 * margin), top, bottom)
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, card.size[0] - 1, card.size[1] - 1], radius=radius, fill=255)

    shadow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shadow).rounded_rectangle(
        [margin, margin + max(1, h // 40), w - margin, h - margin + max(1, h // 40)],
        radius=radius, fill=90,
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(1, min(w, h) // 25)))
    img.paste((0, 0, 0), (0, 0), shadow)
    img.paste(card, (margin, margin), mask)

    draw = ImageDraw.Draw(img)
    _draw_symbol(draw, action_type, size, accent, profile)

    text = (title or action_type or "?").strip()
    font_size = max(10, min(w, h) // 9)
    font = _load_font(font_size)

    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words or [text]:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] > w - 2 * margin - 10 and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    lines = lines[:2] or [text]

    line_height = font.size + 4
    total_height = line_height * len(lines)
    y = h - margin - total_height - int(h * 0.06)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        # dezenter dunkler Text-Schatten fuer Lesbarkeit auf hellerem Verlauf
        draw.text(((w - line_w) // 2 + 1, y + 1), line, font=font, fill=(0, 0, 0))
        draw.text(((w - line_w) // 2, y), line, font=font, fill=(245, 245, 250))
        y += line_height

    return img


def render_app_icon_card(size: tuple[int, int], logo_path: Path, title: str) -> Image.Image:
    """Nutzt ein KI-generiertes Icon-Bild (bereits volle Komposition mit
    dunklem Hintergrund, siehe tools/generate_app_icons.py) randfuellend als
    Hintergrund, mit einem halbtransparenten Textbalken unten fuer den
    Titel - statt es klein auf eine zweite Karte zu packen."""
    w, h = size
    img = Image.open(logo_path).convert("RGB")
    # Zentriert zuschneiden statt verzerrt zu strecken (Quellbilder sind
    # quadratisch, Zielgroesse i.d.R. auch, aber schadet nicht als Absicherung).
    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    img = img.resize((max(1, int(src_w * scale)), max(1, int(src_h * scale))), Image.LANCZOS)
    left = (img.width - w) // 2
    top_crop = (img.height - h) // 2
    img = img.crop((left, top_crop, left + w, top_crop + h))

    text = (title or "").strip()
    if text:
        draw = ImageDraw.Draw(img, "RGBA")
        bar_h = max(16, int(h * 0.24))
        draw.rectangle([0, h - bar_h, w, h], fill=(10, 10, 14, 190))

        font_size = max(10, min(w, h) // 9)
        font = _load_font(font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        while bbox[2] - bbox[0] > w - 10 and font_size > 8:
            font_size -= 1
            font = _load_font(font_size)
            bbox = draw.textbbox((0, 0), text, font=font)
        line_w, line_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (w - line_w) // 2
        ty = h - bar_h + (bar_h - line_h) // 2 - bbox[1]
        draw.text((tx, ty), text, font=font, fill=(245, 245, 250, 255))

    return img.convert("RGB")


GENERATED_ICON_DIR = PROJECT_ROOT / "assets" / "generated-icons"


def _stat_color(percent: float | None) -> tuple[int, int, int]:
    if percent is None:
        return (70, 70, 76)
    if percent < 60:
        return (30, 130, 70)
    if percent < 85:
        return (170, 130, 20)
    return (170, 40, 40)


def _draw_sparkline(img: Image.Image, history: list[float], accent: tuple, margin: int, radius: int) -> None:
    """Zeichnet eine gefuellte Verlaufskurve (letzte ROLLING_WINDOW_S Sekunden,
    siehe hw_monitor.get_recent_values()) als halbtransparente Flaeche im
    Kartenhintergrund, VOR Zahl/Label (die werden danach obendrauf gemalt)."""
    if len(history) < 2:
        return
    w, h = img.size
    lo, hi = min(history), max(history)
    if hi - lo < 1e-6:
        lo, hi = lo - 1, hi + 1  # flache Linie vermeiden -> Divide-by-zero
    pad_x = margin + int(w * 0.06)
    top_y = int(h * 0.12)
    bottom_y = h - margin - int(h * 0.02)
    n = len(history)
    step = (w - 2 * pad_x) / (n - 1)

    points = []
    for i, v in enumerate(history):
        x = pad_x + i * step
        t = (v - lo) / (hi - lo)
        y = bottom_y - t * (bottom_y - top_y)
        points.append((x, y))

    # KORRIGIERT 2026-08-21: 'accent' ist dieselbe Farbe wie der Kartenhinter-
    # grund selbst (Ampel-Farbe) - eine halbtransparente Flaeche in genau
    # dieser Farbe verschmilzt fast unsichtbar mit dem Verlauf darunter (nur
    # die duenne Linienkante war minimal erkennbar). Kontrastierendes Weiss
    # statt der Akzentfarbe verwenden, damit der Graph tatsaechlich als Form
    # erkennbar ist, unabhaengig davon ob die Karte gerade gruen/gelb/rot ist.
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    poly = points + [(points[-1][0], bottom_y), (points[0][0], bottom_y)]
    odraw.polygon(poly, fill=(255, 255, 255, 55))
    odraw.line(points, fill=(255, 255, 255, 150), width=max(1, w // 60))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"), (0, 0))


def render_stat_card(
    size: tuple[int, int],
    label: str,
    value: float | None,
    unit: str = "%",
    value_text: str | None = None,
    color_percent: float | None = None,
    history: list[float] | None = None,
) -> Image.Image:
    """Live-Kennzahl-Karte (CPU/RAM/GPU) fuer die DECK-ONE 'system'-Seite:
    grosse Zahl zentriert, Label darunter, Hintergrundfarbe je nach
    Auslastung (gruen/gelb/rot), analog zum bestehenden Karten-Look.
    value_text: falls gesetzt, wird das statt '{value:.0f}{unit}' angezeigt
    (z.B. "12/33" fuer RAM in GB) - Farbe kommt dann von color_percent statt
    von value, falls angegeben (RAM-GB-Anzeige nutzt weiterhin die RAM-%-
    Auslastung fuer die Ampel-Farbe, nicht die absoluten GB-Werte)."""
    w, h = size
    color = _stat_color(color_percent if color_percent is not None else value)
    top = tuple(min(255, c + 25) for c in color)
    bottom = tuple(max(0, c - 15) for c in color)

    margin = max(2, int(min(w, h) * 0.035))
    radius = max(6, int(min(w, h) * 0.14))

    img = Image.new("RGB", (w, h), (8, 8, 10))
    card = _gradient_bg((w - 2 * margin, h - 2 * margin), top, bottom)
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, card.size[0] - 1, card.size[1] - 1], radius=radius, fill=255)
    shadow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shadow).rounded_rectangle(
        [margin, margin + max(1, h // 40), w - margin, h - margin + max(1, h // 40)],
        radius=radius, fill=90,
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(1, min(w, h) // 25)))
    img.paste((0, 0, 0), (0, 0), shadow)
    img.paste(card, (margin, margin), mask)

    if history:
        _draw_sparkline(img, history, color, margin, radius)

    draw = ImageDraw.Draw(img)
    if value_text is None:
        value_text = f"{value:.0f}{unit}" if value is not None else "--"
    value_font_size = max(16, int(min(w, h) * 0.30))
    value_font = _load_font(value_font_size)
    bbox = draw.textbbox((0, 0), value_text, font=value_font)
    # KORRIGIERT 2026-08-21: feste Schriftgroesse lief bei laengeren Texten
    # (z.B. "12/33GB" statt "42%") ueber den Bildrand hinaus - Schrift
    # schrittweise verkleinern bis sie in die Kartenbreite passt, analog zum
    # bereits vorhandenen Schrumpf-Mechanismus beim Label-Text weiter unten.
    while bbox[2] - bbox[0] > w - 2 * margin - 6 and value_font_size > 9:
        value_font_size -= 1
        value_font = _load_font(value_font_size)
        bbox = draw.textbbox((0, 0), value_text, font=value_font)
    vw, vh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    vx, vy = (w - vw) // 2 - bbox[0], int(h * 0.36) - vh // 2 - bbox[1]
    draw.text((vx + 1, vy + 1), value_text, font=value_font, fill=(0, 0, 0))
    draw.text((vx, vy), value_text, font=value_font, fill=(255, 255, 255))

    label_font = _load_font(max(9, int(min(w, h) * 0.11)))
    bbox = draw.textbbox((0, 0), label.upper(), font=label_font)
    lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    lx, ly = (w - lw) // 2 - bbox[0], h - margin - lh - int(h * 0.10)
    draw.text((lx + 1, ly + 1), label.upper(), font=label_font, fill=(0, 0, 0))
    draw.text((lx, ly), label.upper(), font=label_font, fill=(240, 240, 245))

    return img


# -- Wettervorhersage (siehe 'weather_forecast'-Aktionstyp, ha_client.py::get_forecast) --

_WEATHER_COLORS = {
    "sunny": (60, 140, 200), "clear-night": (40, 50, 90),
    "partlycloudy": (70, 110, 140), "cloudy": (75, 80, 90),
    "fog": (90, 90, 95), "windy": (70, 120, 110), "windy-variant": (70, 120, 110),
    "rainy": (30, 90, 150), "pouring": (20, 70, 140),
    "lightning": (90, 60, 140), "lightning-rainy": (80, 50, 140),
    "snowy": (140, 150, 170), "snowy-rainy": (100, 120, 160),
    "hail": (120, 130, 160), "exceptional": (130, 40, 40),
}
_WEATHER_LABELS_DE = {
    "sunny": "Sonnig", "clear-night": "Klar", "partlycloudy": "Wolkig",
    "cloudy": "Bewoelkt", "fog": "Nebel", "windy": "Windig", "windy-variant": "Windig",
    "rainy": "Regen", "pouring": "Starkregen", "lightning": "Gewitter",
    "lightning-rainy": "Gewitter", "snowy": "Schnee", "snowy-rainy": "Schneeregen",
    "hail": "Hagel", "exceptional": "Extrem",
}


def _draw_centered_outlined(draw: ImageDraw.ImageDraw, text: str, font, width: int, y: int) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (width - tw) // 2 - bbox[0]
    ty = y - bbox[1]
    draw.text((x + 1, ty + 1), text, font=font, fill=(0, 0, 0))
    draw.text((x, ty), text, font=font, fill=(240, 240, 245))


def render_weather_forecast_card(
    size: tuple[int, int], day_label: str, condition: str | None,
    temp_high: float | None, temp_low: float | None,
) -> Image.Image:
    """Vorhersage-Kachel fuer den 'weather_forecast'-Aktionstyp: Tag/Zeitpunkt
    oben, Temperatur mittig, Wetterlage unten. Eigene Farblogik statt der
    Ampel-Prozent-Faerbung von render_stat_card (siehe _stat_color) - Regen
    ist nicht 'schlecht' im Auslastungs-Sinn, verdient also keine rote
    Warnfarbe wie eine ueberlastete CPU."""
    w, h = size
    color = _WEATHER_COLORS.get(condition, (70, 70, 76))
    top = tuple(min(255, c + 25) for c in color)
    bottom = tuple(max(0, c - 15) for c in color)

    margin = max(2, int(min(w, h) * 0.035))
    radius = max(6, int(min(w, h) * 0.14))

    img = Image.new("RGB", (w, h), (8, 8, 10))
    card = _gradient_bg((w - 2 * margin, h - 2 * margin), top, bottom)
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, card.size[0] - 1, card.size[1] - 1], radius=radius, fill=255)
    img.paste(card, (margin, margin), mask)
    draw = ImageDraw.Draw(img)

    if temp_high is not None and temp_low is not None:
        value_text = f"{temp_low:.0f}°/{temp_high:.0f}°"
    elif temp_high is not None:
        value_text = f"{temp_high:.0f}°"
    else:
        value_text = "--"
    value_font_size = max(14, int(min(w, h) * 0.22))
    value_font = _load_font(value_font_size)
    bbox = draw.textbbox((0, 0), value_text, font=value_font)
    while bbox[2] - bbox[0] > w - 2 * margin - 6 and value_font_size > 9:
        value_font_size -= 1
        value_font = _load_font(value_font_size)
        bbox = draw.textbbox((0, 0), value_text, font=value_font)
    vw, vh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    vx, vy = (w - vw) // 2 - bbox[0], int(h * 0.42) - vh // 2 - bbox[1]
    draw.text((vx + 1, vy + 1), value_text, font=value_font, fill=(0, 0, 0))
    draw.text((vx, vy), value_text, font=value_font, fill=(255, 255, 255))

    day_font = _load_font(max(9, int(min(w, h) * 0.12)))
    _draw_centered_outlined(draw, day_label.upper(), day_font, w, margin + int(h * 0.06))

    cond_label = _WEATHER_LABELS_DE.get(condition, condition or "")
    cond_font = _load_font(max(8, int(min(w, h) * 0.10)))
    _draw_centered_outlined(draw, cond_label.upper(), cond_font, w, h - margin - int(h * 0.16))

    return img


# -- Timer/Stopwatch (siehe timer_engine.py fuer den Zustandsautomaten) ------

_TIMER_PHASE_COLORS = {
    "ready": ((40, 95, 135), (20, 55, 82)),      # ruhiges Blau - bereit zum Start
    "running": ((30, 135, 90), (16, 78, 56)),     # Gruen - laeuft normal
    "overtime": ((175, 40, 40), (100, 20, 20)),   # Rot - ueber der Zielzeit
}


def _format_hms(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _timer_card_base(size: tuple[int, int], phase: str) -> tuple[Image.Image, tuple, int, int]:
    """Gemeinsamer abgerundeter Karten-Hintergrund (wie render_stat_card),
    Farbe nach Timer-Phase statt nach Auslastungs-Prozent."""
    w, h = size
    top, bottom = _TIMER_PHASE_COLORS.get(phase, _TIMER_PHASE_COLORS["ready"])
    margin = max(2, int(min(w, h) * 0.035))
    radius = max(6, int(min(w, h) * 0.14))

    img = Image.new("RGB", (w, h), (8, 8, 10))
    card = _gradient_bg((w - 2 * margin, h - 2 * margin), top, bottom)
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, card.size[0] - 1, card.size[1] - 1], radius=radius, fill=255)
    shadow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shadow).rounded_rectangle(
        [margin, margin + max(1, h // 40), w - margin, h - margin + max(1, h // 40)],
        radius=radius, fill=90,
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(1, min(w, h) // 25)))
    img.paste((0, 0, 0), (0, 0), shadow)
    img.paste(card, (margin, margin), mask)
    return img, top, margin, radius


def _draw_timer_sublabel(draw: ImageDraw.ImageDraw, size: tuple[int, int], label: str, sublabel: str, margin: int) -> None:
    """Titel+Phase ('POMODORO 25MIN · LÄUFT') passt bei langen Titeln auch
    bei kleinster Schrift nicht immer in die Kachelbreite - dann wird der
    TITEL-Teil mit Ellipse gekuerzt (die Phase, ueber die Kartenfarbe
    ohnehin schon erkennbar, bleibt immer vollstaendig lesbar)."""
    w, h = size
    max_width = w - 2 * margin - 6
    font = _load_font(max(8, int(min(w, h) * 0.095)))
    while font.size > 7:
        text = f"{label.upper()} · {sublabel}" if label else sublabel
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            break
        font = _load_font(font.size - 1)
    else:
        text = f"{label.upper()} · {sublabel}" if label else sublabel

    bbox = draw.textbbox((0, 0), text, font=font)
    if label and bbox[2] - bbox[0] > max_width:
        # Schrift ist am Minimum und passt immer noch nicht - Titel zeichenweise
        # kuerzen (mit '…'), bis Titel+Phase in die Kachelbreite passen.
        short_label = label.upper()
        while short_label and draw.textbbox((0, 0), f"{short_label}… · {sublabel}", font=font)[2] > max_width:
            short_label = short_label[:-1]
        text = f"{short_label}… · {sublabel}" if short_label else sublabel
        bbox = draw.textbbox((0, 0), text, font=font)

    lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    lx, ly = (w - lw) // 2 - bbox[0], h - margin - lh - int(h * 0.08)
    draw.text((lx + 1, ly + 1), text, font=font, fill=(0, 0, 0))
    draw.text((lx, ly), text, font=font, fill=(240, 240, 245))


def _render_timer_digital(size: tuple[int, int], label: str, phase: str, display_seconds: float, sublabel: str) -> Image.Image:
    img, _, margin, _ = _timer_card_base(size, phase)
    w, h = size
    draw = ImageDraw.Draw(img)
    prefix = "+" if phase == "overtime" else ""
    text = prefix + _format_hms(display_seconds)

    font_size = max(14, int(min(w, h) * 0.26))
    font = _load_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    while bbox[2] - bbox[0] > w - 2 * margin - 6 and font_size > 9:
        font_size -= 1
        font = _load_font(font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx, ty = (w - tw) // 2 - bbox[0], int(h * 0.42) - th // 2 - bbox[1]
    draw.text((tx + 1, ty + 1), text, font=font, fill=(0, 0, 0))
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255))

    _draw_timer_sublabel(draw, size, label, sublabel, margin)
    return img


def _render_timer_analog(
    size: tuple[int, int], label: str, phase: str, display_seconds: float, sublabel: str, target_s: float,
) -> Image.Image:
    img, top, margin, _ = _timer_card_base(size, phase)
    w, h = size
    draw = ImageDraw.Draw(img)

    cx, cy = w // 2, int(h * 0.42)
    r = int(min(w, h) * 0.28)
    ring_w = max(3, r // 6)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 60), width=ring_w)

    if phase == "running" and target_s > 0:
        fraction = max(0.0, min(1.0, 1 - display_seconds / target_s))
    elif phase == "overtime":
        fraction = 1.0
    else:
        fraction = 0.0
    if fraction > 0.002:
        draw.arc(
            [cx - r, cy - r, cx + r, cy + r], start=-90, end=-90 + 360 * fraction,
            fill=(255, 255, 255), width=ring_w,
        )

    prefix = "+" if phase == "overtime" else ""
    text = prefix + _format_hms(display_seconds)
    font = _load_font(max(10, int(min(w, h) * 0.15)))
    bbox = draw.textbbox((0, 0), text, font=font)
    while bbox[2] - bbox[0] > 2 * r - 4 and font.size > 8:
        font = _load_font(font.size - 1)
        bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw / 2 - bbox[0] + 1, cy - th / 2 - bbox[1] + 1), text, font=font, fill=(0, 0, 0))
    draw.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), text, font=font, fill=(255, 255, 255))

    _draw_timer_sublabel(draw, size, label, sublabel, margin)
    return img


def render_timer_card(
    size: tuple[int, int],
    label: str,
    phase: str,
    display_seconds: float,
    sublabel: str,
    style: str = "digital",
    target_s: float = 0.0,
) -> Image.Image:
    """phase ist die REN­DER-Phase ('ready'/'running'/'overtime' - fuer die
    Farbe), nicht zwangslaeufig identisch mit dem rohen TimerState.phase
    (siehe timer_engine.describe(), das z.B. ein 'result' je nach Ausgang
    auf 'running' oder 'overtime' abbildet, damit auf einen Blick sichtbar
    ist ob man drunter oder drueber geblieben ist)."""
    if style == "analog":
        return _render_timer_analog(size, label, phase, display_seconds, sublabel, target_s)
    return _render_timer_digital(size, label, phase, display_seconds, sublabel)


# -- Live-Ansicht-Umschalter (siehe live_view.py) -----------------------------

def render_toggle_card(size: tuple[int, int], label: str, enabled: bool) -> Image.Image:
    """Physische An/Aus-Taste fuer den Browser-Live-Spiegel - gruen+AN wenn
    der Server gerade laeuft, sonst gedecktes Blaugrau+AUS, damit der
    Zustand auch ohne Druck auf einen Blick ablesbar ist."""
    top, bottom = ((30, 150, 90), (16, 88, 56)) if enabled else ((50, 56, 68), (26, 30, 38))
    img, _, margin, _ = _timer_card_base(size, "running" if enabled else "ready")
    # _timer_card_base nutzt schon eine Phase->Farbe-Tabelle - fuer AN/AUS
    # reicht deren "running"(gruen)/"ready"(blau) nicht ganz, direkt neu
    # eingefaerbt statt eine dritte Farbtabelle nur dafuer anzulegen.
    w, h = size
    card = _gradient_bg((w - 2 * margin, h - 2 * margin), top, bottom)
    mask = Image.new("L", card.size, 0)
    radius = max(6, int(min(w, h) * 0.14))
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, card.size[0] - 1, card.size[1] - 1], radius=radius, fill=255)
    img.paste(card, (margin, margin), mask)

    draw = ImageDraw.Draw(img)
    r = int(min(w, h) * 0.16)
    cx, cy = w // 2, int(h * 0.4)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255), width=max(2, r // 4))
    draw.ellipse([cx - r * 0.4, cy - r * 0.4, cx + r * 0.4, cy + r * 0.4], fill=(255, 255, 255))

    state_text = "AN" if enabled else "AUS"
    font = _load_font(max(12, int(min(w, h) * 0.16)))
    bbox = draw.textbbox((0, 0), state_text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx, ty = (w - tw) // 2 - bbox[0], int(h * 0.68) - th // 2 - bbox[1]
    draw.text((tx + 1, ty + 1), state_text, font=font, fill=(0, 0, 0))
    draw.text((tx, ty), state_text, font=font, fill=(255, 255, 255))

    _draw_timer_sublabel(draw, size, "", label, margin)
    return img


def render_key_icon(icon_def: dict, size: tuple[int, int], title: str, action_type: str = "", profile: str = "") -> Image.Image:
    if icon_def and icon_def.get("type") == "app_icon":
        asset_path = PROJECT_ROOT / icon_def["path"]
        if asset_path.exists():
            return render_app_icon_card(size, asset_path, title)
    if icon_def and icon_def.get("type") == "asset":
        asset_path = PROJECT_ROOT / icon_def["path"]
        if asset_path.exists():
            img = Image.open(asset_path).convert("RGB")
            return img.resize(size)
    # Generisches KI-generiertes Icon je Aktionstyp (hotkey/website/Seitenwechsel/...)
    # als Fallback, bevor auf das gezeichnete Vektor-Icon zurueckgefallen wird.
    # (profilspezifische Symbole bei switch_profile gibt es nur im gezeichneten
    # Vektor-Icon, nicht ueber diesen Datei-Fallback - waere pro Profil eine
    # eigene PNG, lohnt sich nicht neben der Keyword-Symbolwahl unten.)
    generic_path = GENERATED_ICON_DIR / f"{action_type}.png"
    if action_type and generic_path.exists():
        return render_app_icon_card(size, generic_path, title)
    return render_generated_icon(size, title, action_type, profile)


def blank_icon(size: tuple[int, int]) -> Image.Image:
    return Image.new("RGB", size, (15, 15, 18))


_ERROR_BADGE_COLOR = (211, 47, 47)  # kraeftiges Rot, deutlich abgesetzt von jeder Kartenfarbe


def add_error_badge(img: Image.Image) -> Image.Image:
    """Blendet eine kleine rote Warn-Badge (Kreis + '!') oben rechts auf eine
    fertig gerenderte Kachel ein - fuer HA-abhaengige Kacheln, wenn die
    letzte Anfrage an Home Assistant fehlgeschlagen ist (ha_client.is_healthy()),
    statt dass der Fehler nur im Log landet und die Kachel weiterhin harmlos
    '--' anzeigt."""
    out = img.convert("RGB").copy()
    w, h = out.size
    draw = ImageDraw.Draw(out, "RGBA")
    r = max(10, round(min(w, h) * 0.14))
    margin = max(2, round(min(w, h) * 0.05))
    cx, cy = w - r - margin, r + margin
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=(*_ERROR_BADGE_COLOR, 235), outline=(255, 255, 255, 255), width=max(1, round(r * 0.12)),
    )
    font = _load_font(round(r * 1.3))
    text = "!"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), text, font=font, fill=(255, 255, 255, 255))
    return out


def zoom_icon(img: Image.Image, factor: float = 1.18) -> Image.Image:
    """Kurzer 'Punch'-Zoom fuers Tastendruck-Feedback: croppt die Bildmitte
    enger und skaliert wieder auf die Zielgroesse hoch - wirkt wie ein
    kurzes Heranzoomen, wenn direkt danach auf der Taste angezeigt."""
    w, h = img.size
    crop_w, crop_h = max(1, int(w / factor)), max(1, int(h / factor))
    left, top = (w - crop_w) // 2, (h - crop_h) // 2
    cropped = img.crop((left, top, left + crop_w, top + crop_h))
    return cropped.resize((w, h), Image.LANCZOS)
