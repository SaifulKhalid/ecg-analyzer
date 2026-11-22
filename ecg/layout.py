"""Trace region proposals; measurement decisions use the frozen pipeline."""

from dataclasses import dataclass

import cv2
import numpy as np

from .digitize import digitize, _spacing
from .features import extract_features
from .pipeline import analyze_signal

MAX_CANDIDATES = 8
LONG_STRIP_FRACTION = 0.85
MIN_REGION_SECONDS = 5.0
PAPER_REGION_HEIGHT_MM = 30.0
NO_GRID_NOTE = "Time scale assumed: strip width = 10 s at 25 mm/s. Amplitude not calibrated."


@dataclass
class Candidate:
    kind: str
    box: list[int]
    band: int


@dataclass
class Selection:
    candidate: Candidate | None
    recovered: object | None
    result: dict
    candidates: list[dict]
    notes: list[str]
    measurement_image: np.ndarray | None
    amplitude_calibrated: bool = True


def unmeasured_result(reason, *, no_trace=False):
    measurements = extract_features(np.array([], dtype=int), 250, None)
    measurements.update(fs_hz=None, beat_count=None)
    status = "no_ecg_detected" if no_trace else "insufficient_quality"
    return {"status": status, "quality": {"status": "insufficient_quality", "reasons": [reason],
            "beat_count": 0, "snr_db": None, "signal_range_mv": None, "rr_plausible_fraction": None},
            "measurements": measurements, "findings": [], "explanation": None, "plots": {},
            "warnings": [reason], "notes": [reason], "source": {}, "detector": {}}


def _grid_info(rgb, box):
    left, top, right, bottom = box
    strip = rgb[top:bottom, left:right]
    hsv = cv2.cvtColor(strip, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(strip, cv2.COLOR_RGB2GRAY)
    masks = [((hsv[:, :, 1] >= 10) & (hsv[:, :, 2] > 100) & (gray > 155)),
             ((gray > 160) & (gray < 245))]
    for mask in masks:
        if not 0.01 <= mask.mean() <= 0.65:
            continue
        x_spacing = _spacing(mask.mean(axis=0))
        y_spacing = _spacing(mask.mean(axis=1))
        if x_spacing is not None and y_spacing is not None and abs(x_spacing-y_spacing)/x_spacing < 0.2:
            return x_spacing, mask
    return None, None


def _quality_reason(result, reason):
    result["status"] = result["quality"]["status"] = "insufficient_quality"
    result["quality"]["reasons"] = list(dict.fromkeys([*result["quality"]["reasons"], reason]))
    result["warnings"] = list(dict.fromkeys([*result["warnings"], reason]))
    result["findings"] = []


def _remove_small_ink(rgb, box):
    left, top, right, bottom = box
    crop = rgb[top:bottom, left:right]
    original = ink_mask(crop)
    connected = cv2.morphologyEx(original, cv2.MORPH_CLOSE, np.ones((1, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(connected)
    keep = [label for label in range(1, count) if stats[label, cv2.CC_STAT_WIDTH] >= max(25, (right-left)*0.12)
            and stats[label, cv2.CC_STAT_HEIGHT] >= 4]
    if keep:
        # Remove small text only; no interpolated values or trace samples are
        # invented here. The digitizer records any remaining missing columns.
        crop[(original > 0) & ~np.isin(labels, keep)] = (255, 255, 255)


def select_region(rgb: np.ndarray, *, pixels_per_mm=None, paper_speed=25, gain=10,
                  crop_box=None, notch_hz=50) -> Selection:
    """Evaluate at most eight independent strips/cells with the frozen pipeline."""
    all_proposals = [Candidate("manual", list(crop_box), -1)] if crop_box is not None else detect_candidates(rgb)
    neighbors = [(proposal, proposal.box.copy()) for proposal in all_proposals]
    proposals = all_proposals[:MAX_CANDIDATES]
    if not proposals:
        return Selection(None, None, unmeasured_result("No ECG trace detected in the image.", no_trace=True), [], [], None)
    evaluated = []
    for candidate in proposals:
        spacing, grid_mask = _grid_info(rgb, candidate.box)
        scale = pixels_per_mm if pixels_per_mm is not None else spacing
        amplitude_calibrated = scale is not None
        notes = []
        full_width = candidate.box[2]-candidate.box[0] >= rgb.shape[1]*LONG_STRIP_FRACTION
        if scale is None:
            if not full_width or paper_speed != 25:
                result = unmeasured_result("Time scale could not be determined.")
                evaluated.append((candidate, None, result, [], None, False))
                continue
            scale = (candidate.box[2]-candidate.box[0])/(10*25)
            notes.append(NO_GRID_NOTE)
        if crop_box is None:
            # A tightly clipped waveform can look like several bands to the
            # frozen digitizer. Keep physical paper context around ONE lead,
            # bounded by valleys to neighboring rows; never change its gate.
            left, top, right, bottom = candidate.box
            rows = np.nonzero(ink_mask(rgb[top:bottom, left:right]))[0]
            center = top + (float(np.median(rows)) if rows.size else (bottom-top)/2)
            new_top = max(0, round(center-PAPER_REGION_HEIGHT_MM*float(scale)/2))
            new_bottom = min(rgb.shape[0], round(center+PAPER_REGION_HEIGHT_MM*float(scale)/2))
            for other, other_box in neighbors:
                if other is candidate or other_box[0] >= right or other_box[2] <= left:
                    continue
                if other_box[3] <= top:
                    new_top = max(new_top, (other_box[3]+top)//2)
                elif other_box[1] >= bottom:
                    new_bottom = min(new_bottom, (bottom+other_box[1])//2)
            candidate.box = [left, min(top, new_top), right, max(bottom, new_bottom)]
            updated_spacing, grid_mask = _grid_info(rgb, candidate.box)
            if pixels_per_mm is None and updated_spacing is not None:
                spacing = scale = updated_spacing
                amplitude_calibrated = True
                notes = []
        measurement_image = rgb.copy()
        if grid_mask is not None:
            left, top, right, bottom = candidate.box
            crop = measurement_image[top:bottom, left:right]
            # The frozen digitizer knows pink/red grids. Normalize only light
            # grid pixels; dark trace pixels and the original preview are kept.
            crop[grid_mask] = (245, 175, 190)
        _remove_small_ink(measurement_image, candidate.box)
        try:
            ok, png = cv2.imencode(".png", cv2.cvtColor(measurement_image, cv2.COLOR_RGB2BGR))
            if not ok:
                raise ValueError("Could not prepare the measurement region.")
            recovered = digitize(png.tobytes(), pixels_per_mm=float(scale), paper_speed=paper_speed,
                                 gain=gain, crop_box=candidate.box)
            result = analyze_signal(recovered.signal, explain=False, include_plots=False, notch_hz=notch_hz)
            if pixels_per_mm is None and spacing is not None:
                recovered.calibration["method"] = "automatic grid autocorrelation"
            if not amplitude_calibrated:
                recovered.calibration.update(gain=None, method="assumed 10 s time scale; amplitude uncalibrated")
                result["quality"]["signal_range_mv"] = None
                result["warnings"] = [warning for warning in result["warnings"]
                                      if not warning.startswith(("Image conversion assumes", "Pink/red grid", "Automatic calibration"))]
            recovered.calibration["amplitude_calibrated"] = amplitude_calibrated
            if candidate.kind != "manual" and result["measurements"]["duration_s"] < MIN_REGION_SECONDS:
                _quality_reason(result, "Selected region is too short for reliable measurement (less than 5 s).")
                for key in ("hr_mean_bpm", "hr_min_bpm", "hr_max_bpm", "mean_rr_ms", "sdnn_ms", "rmssd_ms", "pnn50_percent", "rr_cv"):
                    result["measurements"][key] = None
            evaluated.append((candidate, recovered, result, notes, measurement_image, amplitude_calibrated))
        except (ValueError, TypeError, OSError, cv2.error) as error:
            # The digitizer's multiple-band check remains a safety net. A failed
            # proposal never triggers blending or stitching of different leads.
            message = "Selected region could not be measured."
            if "too few columns" in str(error):
                message = "Image resolution is too low for reliable measurement."
            elif "seconds" in str(error):
                message = "Selected region is too short for reliable measurement (less than 2 s)."
            elif "Multiple trace bands" in str(error):
                message = "Selected region contains overlapping trace bands."
            evaluated.append((candidate, None, unmeasured_result(message), notes, measurement_image, amplitude_calibrated))

    passing = any(item[2]["status"] == "ok" for item in evaluated)
    def rank(item):
        candidate, recovered, result, notes, image, calibrated = item
        good = result["status"] == "ok"
        beats = result["quality"].get("beat_count") or 0
        snr = result["quality"].get("snr_db")
        preference = {"manual": 3, "long strip": 2, "row": 1, "segment": 0}[candidate.kind]
        if passing:
            return (good, preference, snr if snr is not None else -100, beats, candidate.box[3])
        # Favor an available long strip/row over short cells; then the most beats.
        return (preference > 0, beats, preference, candidate.box[3])
    evaluated.sort(key=rank, reverse=True)
    records = [{"kind": item[0].kind, "box": item[0].box, "beats": item[2]["quality"].get("beat_count") or 0,
                "snr_db": item[2]["quality"].get("snr_db"), "quality": item[2]["quality"], "rank": index+1}
               for index, item in enumerate(evaluated)]
    candidate, recovered, result, notes, image, calibrated = evaluated[0]
    return Selection(candidate, recovered, result, records, notes, image, calibrated)


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


def _lead_cell_cuts(statistics, box, page_width):
    """Detect repeated label positions even when divider ticks join the ink."""
    left, top, right, bottom = box
    labels = []
    for x, y, w, h, area in statistics[1:]:
        if (1 <= w <= max(30, page_width*0.025) and 5 <= h <= 35 and area >= 4
                and left <= x < right and top-page_width*0.03 <= y < bottom):
            labels.append(float(x+w/2))
    clusters = []
    for x in sorted(labels):
        if not clusters or x-clusters[-1][-1] > max(8, page_width*0.015):
            clusters.append([x])
        else:
            clusters[-1].append(x)
    centers = [float(np.mean(cluster)) for cluster in clusters]
    if len(centers) < 3 or centers[-1]-centers[0] < (right-left)*0.45:
        return []
    spacing = float(np.median(np.diff(centers)))
    columns = round((right-left)/spacing)
    if columns not in (3, 4, 6) or np.max(np.abs(np.diff(centers)-spacing)) > spacing*0.25:
        return []
    return [left+round((right-left)*index/columns) for index in range(1, columns)]


def detect_candidates(rgb: np.ndarray) -> list[Candidate]:
    height, width = rgb.shape[:2]
    if min(height, width) < 60:
        return []
    mask = cv2.morphologyEx(ink_mask(rgb), cv2.MORPH_CLOSE, np.ones((1, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    components = []
    for label in range(1, count):
        x, y, w, h, area = map(int, stats[label])
        if (w >= max(25, width*0.035) and 4 <= h <= height*0.9 and w >= 1.8*h
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
            cuts = _lead_cell_cuts(stats, [left, y0, right, y1], width) if right-left >= width*0.5 else []
            for start, end in zip([left, *cuts], [*cuts, right]):
                start += margin if cuts and start != left else 0
                end -= margin if cuts and end != right else 0
                fraction = (end-start)/width
                kind = "long strip" if fraction >= LONG_STRIP_FRACTION else "row" if fraction >= 0.5 else "segment"
                box = [max(0, start-margin if not cuts else start), max(0, y0-margin),
                       min(width, end+margin if not cuts else end), min(height, y1+margin)]
                candidates.append(Candidate(kind, _trim_leading_pulse(mask, box), band_index))
    candidates.sort(key=lambda item: ({"long strip":2,"row":1,"segment":0}[item.kind], item.box[2]-item.box[0], item.box[3]), reverse=True)
    # Keep a range of rows/cells, with deterministic bottom-most ties.
    return candidates
