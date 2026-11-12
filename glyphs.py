"""Read the game's pixel fonts by matching glyph templates cut from real captures.

A text region is turned into a black/white mask (one colour rule per kind of
text), split into glyphs at empty columns, and every glyph is compared with the
labelled bitmaps stored in templates/glyphs.json. Unknown glyphs come back as
"?" so the caller can stop instead of guessing.

All bitmaps are in canonical picture pixels (the 16:9 game picture scaled to
2560 x 1440, see window.CANON_W / CANON_H).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

TEMPLATE_FILE = Path(__file__).resolve().parent / "templates" / "glyphs.json"

UNKNOWN = "?"          # returned for a glyph that matches no template
MATCH_MIN = 0.92       # minimum overlap score to accept a template (8 vs 0 scores about 0.85)
SIZE_TOL = 3           # a glyph may differ from its template by this many pixels


@dataclass
class Glyph:
    x0: int            # column range inside the region
    x1: int
    y0: int            # row range inside the region
    y1: int
    bitmap: np.ndarray  # bool, trimmed to the glyph

    @property
    def width(self) -> int:
        return self.x1 - self.x0


def segment(mask: np.ndarray, min_pixels: int = 6, join_gap: int = 0) -> list[Glyph]:
    """Split a text mask into glyphs at runs of empty columns.

    join_gap: empty-column runs up to this wide stay inside one glyph (used for
    fonts whose glyphs have internal gaps).
    """
    cols = mask.any(axis=0)
    runs: list[list[int]] = []
    x = 0
    w = mask.shape[1]
    while x < w:
        if cols[x]:
            start = x
            while x < w and cols[x]:
                x += 1
            if runs and start - runs[-1][1] <= join_gap:
                runs[-1][1] = x
            else:
                runs.append([start, x])
        else:
            x += 1
    out = []
    for x0, x1 in runs:
        part = mask[:, x0:x1]
        rows = np.nonzero(part.any(axis=1))[0]
        y0, y1 = int(rows[0]), int(rows[-1]) + 1
        bm = part[y0:y1]
        if bm.sum() >= min_pixels:
            out.append(Glyph(x0, x1, y0, y1, bm.copy()))
    return out


def segment_blobs(mask: np.ndarray, min_pixels: int = 6) -> list[Glyph]:
    """Split a text mask into connected blobs, left to right.

    For fonts whose glyphs are one piece each but can overlap column-wise
    (in a stat badge the foot of a "1" reaches under the next digit).
    """
    import cv2
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    out = []
    for k in range(1, n):
        x, y, w, h, area = stats[k]
        if area >= min_pixels:
            out.append(Glyph(int(x), int(x + w), int(y), int(y + h), (labels[y:y + h, x:x + w] == k)))
    out.sort(key=lambda g: g.x0)
    return out


def _resize(bm: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    if bm.shape == shape:
        return bm
    ys = (np.arange(shape[0]) * bm.shape[0] / shape[0]).astype(int)
    xs = (np.arange(shape[1]) * bm.shape[1] / shape[1]).astype(int)
    return bm[ys][:, xs]


def _score(a: np.ndarray, b: np.ndarray) -> float:
    """Overlap (intersection over union) of two bitmaps, after resizing a to b."""
    if abs(a.shape[0] - b.shape[0]) > SIZE_TOL or abs(a.shape[1] - b.shape[1]) > SIZE_TOL:
        return 0.0
    a = _resize(a, b.shape)
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 0.0


def _encode(bm: np.ndarray) -> list[str]:
    return ["".join("#" if v else "." for v in row) for row in bm]


def _decode(rows: list[str]) -> np.ndarray:
    return np.array([[c == "#" for c in row] for row in rows], dtype=bool)


class GlyphStore:
    """Labelled glyph bitmaps, grouped by font, kept in a readable JSON file."""

    def __init__(self, path: Path = TEMPLATE_FILE):
        self.path = path
        self.fonts: dict[str, list[tuple[str, np.ndarray]]] = {}
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            for font, entries in raw.items():
                self.fonts[font] = [(e["label"], _decode(e["rows"])) for e in entries]

    def save(self) -> None:
        self.path.parent.mkdir(exist_ok=True)
        raw = {
            font: [{"label": lab, "rows": _encode(bm)} for lab, bm in sorted(entries, key=lambda e: e[0])]
            for font, entries in sorted(self.fonts.items())
        }
        self.path.write_text(json.dumps(raw, indent=1), encoding="utf-8")

    def classify(self, font: str, bm: np.ndarray) -> tuple[str, float]:
        best, best_score = UNKNOWN, 0.0
        for label, tpl in self.fonts.get(font, []):
            s = _score(bm, tpl)
            if s > best_score:
                best, best_score = label, s
        if best_score < MATCH_MIN:
            return UNKNOWN, best_score
        return best, best_score

    def add(self, font: str, label: str, bm: np.ndarray) -> bool:
        """Store a labelled glyph unless an equal one is already known."""
        known, score = self.classify(font, bm)
        if known == label and score >= 0.97:
            return False
        self.fonts.setdefault(font, []).append((label, bm.copy()))
        return True

    def read(self, font: str, mask: np.ndarray, space_gap: int | None = None,
             join_gap: int = 0) -> str:
        """Read a text mask. Gaps of space_gap or more columns become a space."""
        text = ""
        prev = None
        for g in segment(mask, join_gap=join_gap):
            if prev is not None and space_gap is not None and g.x0 - prev.x1 >= space_gap:
                text += " "
            text += self.classify(font, g.bitmap)[0]
            prev = g
        return text

    def teach(self, font: str, mask: np.ndarray, text: str, join_gap: int = 0) -> int:
        """Label the glyphs of a mask with a known text. Returns glyphs added.

        The text (without spaces) must have exactly one character per glyph.
        """
        glyphs = segment(mask, join_gap=join_gap)
        chars = text.replace(" ", "")
        if len(glyphs) != len(chars):
            raise ValueError(
                f"{font}: '{text}' has {len(chars)} characters but the image has {len(glyphs)} glyphs"
            )
        return sum(self.add(font, c, g.bitmap) for c, g in zip(chars, glyphs))


# ---- colour rules that turn an RGB region (H x W x 3 array) into a text mask ----

def white(rgb: np.ndarray, level: int = 215) -> np.ndarray:
    """White text."""
    return rgb.min(axis=2) >= level


def dark(rgb: np.ndarray, level: int = 110) -> np.ndarray:
    """Dark text on a light background."""
    return rgb.max(axis=2) <= level


def inked(rgb: np.ndarray) -> np.ndarray:
    """Dark or strongly coloured text on a white background (pale shadows excluded)."""
    rgb = rgb.astype(int)
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    return (mx <= 130) | ((mx - mn >= 90) & (mn <= 170))


def dump(mask: np.ndarray, step: int = 1) -> str:
    """ASCII picture of a mask, for debugging."""
    return "\n".join("".join("#" if v else "." for v in row[::step]) for row in mask[::step])
