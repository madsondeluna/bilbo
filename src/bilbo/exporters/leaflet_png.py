"""Top-view PNG scatter plot of leaflet lipid and protein distributions.

Uses only numpy (already a project dependency) and Python stdlib (struct, zlib).
No matplotlib or other graphics libraries required.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Optional

import numpy as np

from bilbo.builders.leaflet_layout import LeafletLayout

# ── Colour palette (10 distinct colours) ────────────────────────────────────
_PALETTE: list[tuple[int, int, int]] = [
    (31, 119, 180),
    (255, 127, 14),
    (44, 160, 44),
    (214, 39, 40),
    (148, 103, 189),
    (140, 86, 75),
    (227, 119, 194),
    (127, 127, 127),
    (188, 189, 34),
    (23, 190, 207),
]
_PROTEIN_COLOR: tuple[int, int, int] = (20, 20, 20)
_BG: tuple[int, int, int] = (255, 255, 255)
_PANEL_BG: tuple[int, int, int] = (240, 243, 252)
_BORDER: tuple[int, int, int] = (90, 100, 130)
_TEXT_COLOR: tuple[int, int, int] = (30, 30, 60)
_LEGEND_TEXT: tuple[int, int, int] = (50, 50, 70)

# ── 5×7 bitmap font ─────────────────────────────────────────────────────────
# Row-major: each entry is 7 rows of 5 pixels.
# Each row is a 5-bit int: bit 4 = leftmost pixel, bit 0 = rightmost pixel.
_FONT7: dict[str, list[int]] = {
    " ": [0] * 7,
    "-": [0, 0, 0, 0b11111, 0, 0, 0],
    "A": [0b01110, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0],
    "B": [0b11110, 0b10001, 0b11110, 0b10001, 0b10001, 0b11110, 0],
    "C": [0b01110, 0b10001, 0b10000, 0b10000, 0b10001, 0b01110, 0],
    "D": [0b11100, 0b10010, 0b10001, 0b10001, 0b10010, 0b11100, 0],
    "E": [0b11111, 0b10000, 0b11110, 0b10000, 0b10000, 0b11111, 0],
    "F": [0b11111, 0b10000, 0b11110, 0b10000, 0b10000, 0b10000, 0],
    "G": [0b01110, 0b10001, 0b10000, 0b10011, 0b10001, 0b01110, 0],
    "H": [0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001, 0],
    "I": [0b01110, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110, 0],
    "J": [0b00111, 0b00001, 0b00001, 0b00001, 0b10001, 0b01110, 0],
    "K": [0b10001, 0b10010, 0b10100, 0b11000, 0b10100, 0b10001, 0],
    "L": [0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b11111, 0],
    "M": [0b10001, 0b11011, 0b10101, 0b10001, 0b10001, 0b10001, 0],
    "N": [0b10001, 0b11001, 0b10101, 0b10011, 0b10001, 0b10001, 0],
    "O": [0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110, 0],
    "P": [0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0],
    "Q": [0b01110, 0b10001, 0b10001, 0b10101, 0b10010, 0b01101, 0],
    "R": [0b11110, 0b10001, 0b10001, 0b11110, 0b10010, 0b10001, 0],
    "S": [0b01111, 0b10000, 0b01110, 0b00001, 0b00001, 0b11110, 0],
    "T": [0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0],
    "U": [0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110, 0],
    "V": [0b10001, 0b10001, 0b10001, 0b10001, 0b01010, 0b00100, 0],
    "W": [0b10001, 0b10001, 0b10101, 0b10101, 0b11011, 0b10001, 0],
    "X": [0b10001, 0b01010, 0b00100, 0b00100, 0b01010, 0b10001, 0],
    "Y": [0b10001, 0b01010, 0b00100, 0b00100, 0b00100, 0b00100, 0],
    "Z": [0b11111, 0b00010, 0b00100, 0b01000, 0b10000, 0b11111, 0],
    "0": [0b01110, 0b10011, 0b10101, 0b11001, 0b10001, 0b01110, 0],
    "1": [0b00100, 0b01100, 0b00100, 0b00100, 0b00100, 0b01110, 0],
    "2": [0b01110, 0b10001, 0b00001, 0b00110, 0b01000, 0b11111, 0],
    "3": [0b01110, 0b10001, 0b00110, 0b00001, 0b10001, 0b01110, 0],
    "4": [0b00010, 0b00110, 0b01010, 0b11111, 0b00010, 0b00010, 0],
    "5": [0b11111, 0b10000, 0b11110, 0b00001, 0b10001, 0b01110, 0],
    "6": [0b01110, 0b10000, 0b11110, 0b10001, 0b10001, 0b01110, 0],
    "7": [0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b01000, 0],
    "8": [0b01110, 0b10001, 0b01110, 0b10001, 0b10001, 0b01110, 0],
    "9": [0b01110, 0b10001, 0b10001, 0b01111, 0b00001, 0b01110, 0],
}

_FS = 2  # font pixel scale: each bitmap pixel becomes _FS×_FS screen pixels
_CW = (5 + 1) * _FS  # character width in screen pixels (5 cols + 1 gap)
_CH = 7 * _FS  # character height in screen pixels


def _draw_text(
    img: np.ndarray,
    text: str,
    x0: int,
    y0: int,
    color: tuple[int, int, int],
) -> None:
    h, w = img.shape[:2]
    cx = x0
    for ch in text.upper():
        glyph = _FONT7.get(ch, _FONT7[" "])
        for row_idx, row_bits in enumerate(glyph):
            for col_idx in range(5):
                if row_bits & (1 << (4 - col_idx)):
                    px = cx + col_idx * _FS
                    py = y0 + row_idx * _FS
                    py2 = min(py + _FS, h)
                    px2 = min(px + _FS, w)
                    if py < h and px < w:
                        img[py:py2, px:px2] = color
        cx += _CW


def _text_width(text: str) -> int:
    return len(text) * _CW


def _draw_circle(
    img: np.ndarray,
    cx: int,
    cy: int,
    r: int,
    color: tuple[int, int, int],
) -> None:
    h, w = img.shape[:2]
    y0, y1 = max(0, cy - r), min(h, cy + r + 1)
    x0, x1 = max(0, cx - r), min(w, cx + r + 1)
    ys, xs = np.ogrid[y0:y1, x0:x1]
    mask = (xs - cx) ** 2 + (ys - cy) ** 2 <= r * r
    img[y0:y1, x0:x1][mask] = color


def _draw_plus_marker(
    img: np.ndarray,
    cx: int,
    cy: int,
    r: int,
    color: tuple[int, int, int],
) -> None:
    h, w = img.shape[:2]
    y0, y1 = max(0, cy - r), min(h, cy + r + 1)
    x0, x1 = max(0, cx - r), min(w, cx + r + 1)
    ys, xs = np.mgrid[y0:y1, x0:x1]
    dy = np.abs(ys - cy)
    dx = np.abs(xs - cx)
    thick = max(1, r // 3)
    mask = (dy <= thick) | (dx <= thick)
    img[y0:y1, x0:x1][mask] = color


def _write_png(path: Path, img: np.ndarray) -> None:
    h, w = img.shape[:2]

    def _chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + row.astype(np.uint8).tobytes() for row in img)
    idat = zlib.compress(raw, level=6)

    with path.open("wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(_chunk(b"IHDR", ihdr))
        fh.write(_chunk(b"IDAT", idat))
        fh.write(_chunk(b"IEND", b""))


def write_leaflet_png(
    layouts: dict[str, LeafletLayout],
    output_path: Path,
    peptide_placements: Optional[list[dict]] = None,
) -> None:
    """Write a top-view PNG scatter plot of lipid and protein distributions.

    peptide_placements: list of dicts with keys 'peptide_id', 'leaflet',
    and 'translation_vector' ([tx, ty, tz] in Angstroms).
    """
    if not layouts:
        return

    species: list[str] = sorted(
        {pos.lipid_id for layout in layouts.values() for pos in layout.positions}
    )
    species_color: dict[str, tuple[int, int, int]] = {
        sp: _PALETTE[i % len(_PALETTE)] for i, sp in enumerate(species)
    }

    pep_ids: list[str] = []
    if peptide_placements:
        seen: set[str] = set()
        for pp in peptide_placements:
            pid = pp.get("peptide_id", "")
            if pid and pid not in seen:
                pep_ids.append(pid)
                seen.add(pid)

    MARGIN = 30
    PAD = 20
    PANEL_SEP = 24
    TITLE_H = _CH + 16

    legend_labels = species + pep_ids
    legend_label_w = max((_text_width(lb) for lb in legend_labels), default=0)
    LEGEND_W = 18 + legend_label_w + MARGIN

    box_x = max(lay.box_x() for lay in layouts.values())
    box_y = max(lay.box_y() for lay in layouts.values())

    scale = min(580.0 / max(box_x, 0.01), 520.0 / max(box_y, 0.01))

    mean_spacing = sum(lay.spacing for lay in layouts.values()) / len(layouts)
    dot_r = min(6, max(1, int(mean_spacing * scale / 2) - 1))

    panel_w = int(box_x * scale) + 2 * PAD
    panel_h = int(box_y * scale) + 2 * PAD

    leaflet_order = [k for k in ("upper", "lower") if k in layouts]
    n_panels = len(leaflet_order)

    total_w = MARGIN * 2 + n_panels * panel_w + (n_panels - 1) * PANEL_SEP + LEGEND_W
    total_h = MARGIN * 2 + TITLE_H + panel_h

    img = np.full((total_h, total_w, 3), _BG, dtype=np.uint8)

    for panel_idx, leaflet_name in enumerate(leaflet_order):
        layout = layouts[leaflet_name]
        px0 = MARGIN + panel_idx * (panel_w + PANEL_SEP)
        py0 = MARGIN + TITLE_H

        img[py0: py0 + panel_h, px0: px0 + panel_w] = _PANEL_BG
        img[py0, px0: px0 + panel_w] = _BORDER
        img[py0 + panel_h - 1, px0: px0 + panel_w] = _BORDER
        img[py0: py0 + panel_h, px0] = _BORDER
        img[py0: py0 + panel_h, px0 + panel_w - 1] = _BORDER

        label = leaflet_name.upper() + " LEAFLET"
        tx = px0 + (panel_w - _text_width(label)) // 2
        ty = MARGIN + (TITLE_H - _CH) // 2
        _draw_text(img, label, tx, ty, _TEXT_COLOR)

        for pos in layout.positions:
            color = species_color[pos.lipid_id]
            lx = px0 + PAD + int(pos.x * scale)
            ly = py0 + PAD + int(pos.y * scale)
            _draw_circle(img, lx, ly, dot_r, color)

        if peptide_placements:
            for pp in peptide_placements:
                if pp.get("leaflet") != leaflet_name:
                    continue
                tv = pp.get("translation_vector", [0.0, 0.0, 0.0])
                # translation_vector is in Angstroms; convert to nm
                lx = px0 + PAD + int(tv[0] / 10.0 * scale)
                ly = py0 + PAD + int(tv[1] / 10.0 * scale)
                if px0 < lx < px0 + panel_w and py0 < ly < py0 + panel_h:
                    _draw_plus_marker(img, lx, ly, dot_r * 3 + 2, _PROTEIN_COLOR)

    # Legend
    lx = MARGIN * 2 + n_panels * panel_w + (n_panels - 1) * PANEL_SEP
    ly = MARGIN + TITLE_H + PAD

    _draw_text(img, "LIPIDS", lx, ly, _TEXT_COLOR)
    ly += _CH + 10

    for sp, color in species_color.items():
        _draw_circle(img, lx + 6, ly + _CH // 2, 6, color)
        _draw_text(img, sp, lx + 18, ly, _LEGEND_TEXT)
        ly += _CH + 8

    if pep_ids:
        ly += 8
        _draw_text(img, "PROTEINS", lx, ly, _TEXT_COLOR)
        ly += _CH + 10
        for pid in pep_ids:
            _draw_plus_marker(img, lx + 6, ly + _CH // 2, 7, _PROTEIN_COLOR)
            _draw_text(img, pid, lx + 18, ly, _LEGEND_TEXT)
            ly += _CH + 8

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_png(output_path, img)
