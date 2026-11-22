"""Trace region proposals; measurement decisions use the frozen pipeline."""

from dataclasses import dataclass

import cv2
import numpy as np


MAX_CANDIDATES = 8
LONG_STRIP_FRACTION = 0.85
MIN_REGION_SECONDS = 5.0


@dataclass
class Candidate:
    kind: str
    box: list[int]
    band: int


def ink_mask(rgb: np.ndarray) -> np.ndarray:
    """Dark, mostly neutral trace ink; colored grids and faint gray grids drop."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # Very dark trace/grid crossings can inherit grid saturation after JPEG
    # compression. Their low luminance distinguishes them from colored paper.
    return ((gray < 160) & ((hsv[:, :, 1] < 105) | (gray < 110))).astype(np.uint8)


def _trim_leading_pulse(mask, box):
    left, top, right, bottom = box
    strip = mask[top:bottom, left:right]
    positions = np.full(strip.shape[1], np.nan)
    for column in range(strip.shape[1]):
        rows = np.flatnonzero(strip[:, column])
        if rows.size:
            positions[column] = np.median(rows)
    valid = np.isfinite(positions)
    if valid.sum() < 20:
        return box
    baseline = np.nanmedian(positions)
    level = np.abs(positions-baseline) > max(8, strip.shape[0]*0.3)
    flat = np.r_[False, np.abs(np.diff(positions)) <= 1] & level
    edges = np.diff(np.pad(flat.astype(int), (1, 1)))
    for start, end in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
        if start < strip.shape[1]*0.12 and max(8, strip.shape[1]*0.008) <= end-start <= strip.shape[1]*0.08:
            # A sustained square plateau differs from a narrow R apex. Trim
            # the plateau, falling edge and a small baseline margin.
            return [min(right-1, left+end+max(3, round(strip.shape[1]*0.012))), top, right, bottom]
    return box


def detect_candidates(rgb: np.ndarray) -> list[Candidate]:
    height, width = rgb.shape[:2]
    if min(height, width) < 60:
        return []
    mask = cv2.morphologyEx(ink_mask(rgb), cv2.MORPH_CLOSE, np.ones((1, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    components = []
    for label in range(1, count):
        x, y, w, h, area = map(int, stats[label])
        if (w >= max(25, width*0.035) and 4 <= h <= height*0.35 and w >= 1.8*h
                and area >= w*0.6 and area < w*h*0.6):
            components.append((x, y, x+w, y+h, label))
    if not components:
        return []
    # Projection valleys give row extents after small text components are gone.
    retained = np.isin(labels, [item[4] for item in components])
    active = np.any(retained, axis=1).astype(np.uint8)
    gap = max(3, round(height*0.006))
    active = cv2.morphologyEx(active[:, None], cv2.MORPH_CLOSE, np.ones((gap, 1), np.uint8))[:, 0]
    edges = np.diff(np.pad(active.astype(int), (1, 1)))
    bands = list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))
    candidates = []
    margin = max(3, round(width*0.003))
    for band_index, (top, bottom) in enumerate(bands):
        row = [item for item in components if item[1] < bottom and item[3] > top]
        row.sort(key=lambda item: item[0])
        # Each connected cell is kept separate. Disjoint cells are never joined
        # merely because they occupy the same row.
        for left, y0, right, y1, label in row:
            if right-left < width*0.12:
                continue
            kind = "long strip" if right-left >= LONG_STRIP_FRACTION*width else "segment"
            box = [max(0, left-margin), max(0, y0-margin), min(width, right+margin), min(height, y1+margin)]
            candidates.append(Candidate(kind, _trim_leading_pulse(mask, box), band_index))
    candidates.sort(key=lambda item: (item.kind == "long strip", item.box[2]-item.box[0], item.box[3]), reverse=True)
    # Keep a range of rows/cells, with deterministic bottom-most ties.
    return candidates
