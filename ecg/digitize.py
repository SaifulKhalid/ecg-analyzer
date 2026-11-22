"""Single-lead image calibration and own column-wise trace extraction.

Pink/red grid pixels supply physical spacing via projection autocorrelation.
Dark ink is thresholded independently of the color mask, then one median y is
recovered per image column. Missing columns are interpolated and recorded as
quality warnings. Paper speed and gain are explicit assumptions / overrides,
not OCR measurements. The result is always a 250 Hz, median-baseline mV signal.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from . import config as cfg
from .preprocess import Signal, resample_signal


@dataclass
class Digitized:
    signal: Signal
    debug_overlay: bytes
    calibration: dict
    warnings: list[str]


def _grid_mask(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    red_hue = (hue <= cfg.GRID_HUE_HIGH) | (hue >= cfg.GRID_HUE_LOW)
    return red_hue & (saturation >= cfg.GRID_MIN_SATURATION) & (value >= cfg.GRID_MIN_VALUE)


def _spacing(profile: np.ndarray) -> float | None:
    """Own local-max decisions on FFT autocorrelation; interpolate subpixel lag."""
    values = np.asarray(profile, dtype=float)
    values -= values.mean()
    if values.size < 2 * cfg.GRID_MIN_SPACING_PX or np.dot(values, values) < cfg.NUMERICAL_EPSILON:
        return None
    fft_size = 1 << (2 * values.size - 1).bit_length()
    transform = np.fft.rfft(values, fft_size)
    correlation = np.fft.irfft(transform * np.conj(transform), fft_size)[:values.size]
    correlation /= max(correlation[0], cfg.NUMERICAL_EPSILON)
    limit = min(cfg.GRID_MAX_SPACING_PX, values.size // 3)
    candidates = [lag for lag in range(cfg.GRID_MIN_SPACING_PX, limit)
                  if correlation[lag] >= correlation[lag - 1] and correlation[lag] > correlation[lag + 1]
                  and correlation[lag] >= cfg.GRID_MIN_CORRELATION]
    if not candidates:
        return None
    lag = candidates[0]  # First repeat is the 1 mm minor grid, not a later harmonic.
    left, center, right = correlation[lag - 1:lag + 2]
    denominator = left - 2 * center + right
    shift = 0.5 * (left - right) / denominator if abs(denominator) > cfg.NUMERICAL_EPSILON else 0.0
    return float(lag + np.clip(shift, -0.5, 0.5))


def _longest_gap(valid: np.ndarray) -> int:
    longest = current = 0
    for present in valid:
        current = 0 if present else current + 1
        longest = max(longest, current)
    return longest


def _keep_trace_components(binary: np.ndarray) -> np.ndarray:
    """Remove short text / specks, retaining all long traces to detect multi-lead input."""
    count, labels, statistics, _ = cv2.connectedComponentsWithStats(binary.astype(np.uint8), connectivity=8)
    minimum_width = max(2, int(binary.shape[1] * cfg.MIN_TRACE_COMPONENT_WIDTH_FRACTION))
    keep = [label for label in range(1, count) if statistics[label, cv2.CC_STAT_WIDTH] >= minimum_width]
    return np.isin(labels, keep) if keep else binary


def _looks_multilead(trace: np.ndarray) -> bool:
    active = np.flatnonzero(np.mean(trace, axis=1) >= cfg.MULTILEAD_ROW_ACTIVITY_FRACTION)
    if not active.size:
        return False
    minimum_separation = max(1, int(trace.shape[0] * cfg.MULTILEAD_ROW_SEPARATION_FRACTION))
    bands = [int(active[0])]
    for row in active[1:]:
        if row - bands[-1] >= minimum_separation:
            bands.append(int(row))
    return len(bands) >= cfg.MULTILEAD_MIN_BANDS


def digitize(image_bytes: bytes, *, pixels_per_mm: float | None = None,
             paper_speed: float = cfg.PAPER_SPEED_MM_S, gain: float = cfg.GAIN_MM_MV,
             crop_box: tuple[int, int, int, int] | list[int] | None = None) -> Digitized:
    """Recover one lead; crop box is (left, top, right, bottom), in input pixels.

    With no detected grid and no manual pixel scale, the default scale is used
    only for a debug preview. `calibration_uncertain` makes the shared quality
    gate skip screening / GPT until pixels_per_mm is supplied.
    """
    if not image_bytes or len(image_bytes) > cfg.MAX_IMAGE_BYTES:
        raise ValueError("Choose a non-empty image under 10 MB.")
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The image could not be decoded as PNG, JPG, or WebP.")
    height, width = image.shape[:2]
    if height * width > cfg.MAX_IMAGE_PIXELS:
        raise ValueError("Image dimensions are too large; crop to one lead first.")
    calibration_values = [paper_speed, gain] + ([] if pixels_per_mm is None else [pixels_per_mm])
    if any(not np.isfinite(value) or value <= 0 for value in calibration_values):
        raise ValueError("pixels_per_mm, paper_speed, and gain must be positive finite numbers.")
    if crop_box is not None:
        if len(crop_box) != 4 or any(not isinstance(value, (int, np.integer)) for value in crop_box):
            raise ValueError("crop_box must contain four integer pixel bounds.")
        x0, y0, x1, y1 = map(int, crop_box)
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise ValueError("crop_box must stay inside the image and have positive width / height.")
    else:
        x0, y0, x1, y1 = 0, 0, width, height
    selected = image[y0:y1, x0:x1]
    mask = _grid_mask(selected)
    has_color_grid = float(np.mean(mask)) >= cfg.GRID_MIN_MASK_FRACTION
    # Exclude the renderer's calibration header / plain margins using grid bounds.
    if crop_box is None and has_color_grid:
        rows, columns = np.nonzero(mask)
        x0, x1 = int(columns.min()), int(columns.max()) + 1
        y0, y1 = int(rows.min()), int(rows.max()) + 1
        selected = image[y0:y1, x0:x1]
        mask = _grid_mask(selected)
    spacing_x = _spacing(mask.mean(axis=0)) if has_color_grid else None
    spacing_y = _spacing(mask.mean(axis=1)) if has_color_grid else None
    detected = spacing_x or spacing_y
    warnings = []
    uncertain = False
    if pixels_per_mm is not None:
        scale, method = float(pixels_per_mm), "manual pixels_per_mm"
        if detected is not None and abs(detected - scale) / scale > cfg.GRID_AXIS_DISAGREEMENT_FRACTION:
            warnings.append("Manual pixels/mm differs from the automatic grid estimate; the supplied scale is used.")
    elif detected is not None:
        scale, method = float(detected), "automatic pink/red grid autocorrelation"
        if spacing_x is not None and spacing_y is not None:
            if abs(spacing_x - spacing_y) / scale > cfg.GRID_AXIS_DISAGREEMENT_FRACTION:
                uncertain = True
                warnings.append("Grid spacing disagrees between axes; provide pixels_per_mm.")
            else:
                scale = float((spacing_x + spacing_y) / 2)
        else:
            warnings.append("Only one grid direction was recovered; square paper geometry is assumed.")
        warnings.append("Automatic calibration assumes the first detected grid repeat is 1 mm; confirm the scale.")
    else:
        scale, method, uncertain = cfg.DEFAULT_PIXELS_PER_MM, "assumed default; needs confirmation", True
    if detected is None:
        warnings.append("Pink/red grid spacing was not found. Provide pixels_per_mm for reliable time calibration.")
    native_fs = scale * paper_speed
    if native_fs < cfg.MIN_IMAGE_COLUMNS_PER_SECOND:
        raise ValueError("Image has too few columns per second; use a higher-resolution single-lead strip.")
    if native_fs < cfg.MIN_INPUT_FS:
        warnings.append(f"Image has only {native_fs:.1f} columns/s; resampling cannot restore lost waveform detail.")

    grayscale = cv2.cvtColor(selected, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(grayscale, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    # Dark ink wins over a pink tint at anti-aliased grid crossings. Removing
    # every colored pixel would erase parts of a thin true trace.
    removable_grid = mask & (grayscale >= cfg.GRID_REMOVAL_MIN_GRAY)
    trace = (ink > 0) & ~removable_grid
    components = _keep_trace_components(trace)
    if _looks_multilead(components):
        raise ValueError("Multiple trace bands detected. Crop to one horizontal lead / rhythm strip.")
    original_coverage = float(np.mean(np.any(trace, axis=0)))
    component_coverage = float(np.mean(np.any(components, axis=0)))
    # Suppress short text only when doing so preserves almost all trace columns.
    if component_coverage >= (1 - cfg.MAX_COMPONENT_COLUMN_LOSS) * original_coverage:
        trace = components
    positions = np.full(trace.shape[1], np.nan, dtype=float)
    for column in range(trace.shape[1]):
        ys = np.flatnonzero(trace[:, column])
        if ys.size:
            positions[column] = float(np.median(ys))
    valid = np.isfinite(positions)
    if np.count_nonzero(valid) < 2:
        raise ValueError("No recoverable single-lead trace was found; use a clearer crop.")
    gap_fraction = float(np.mean(~valid))
    longest_gap_seconds = _longest_gap(valid) / native_fs
    if gap_fraction:
        warnings.append(f"Interpolated {gap_fraction:.1%} of columns with missing trace; longest gap {longest_gap_seconds:.3f} s.")
    columns = np.arange(positions.size)
    positions = np.interp(columns, columns[valid], positions[valid])
    millivolts = -(positions - np.median(positions)) / (scale * gain)
    samples = resample_signal(millivolts, native_fs, cfg.FS_TARGET)
    calibration = {"pixels_per_mm": round(scale, 4), "paper_speed": float(paper_speed), "gain": float(gain),
                   "method": method, "grid_spacing_x_px": spacing_x, "grid_spacing_y_px": spacing_y,
                   "native_columns_per_second": round(native_fs, 3), "crop_box": [x0, y0, x1, y1]}
    warnings.append(f"Image conversion assumes paper speed {paper_speed:g} mm/s and gain {gain:g} mm/mV; confirm calibration.")
    metadata = {"source": "digitized single-lead image", "calibration": calibration,
                "calibration_uncertain": uncertain, "gap_fraction": round(gap_fraction, 4),
                "longest_gap_s": round(longest_gap_seconds, 4), "warnings": warnings}
    recovered = Signal(samples, cfg.FS_TARGET, metadata)
    overlay = image.copy()
    points = np.column_stack((columns + x0, np.rint(positions).astype(int) + y0)).astype(np.int32)
    cv2.polylines(overlay, [points.reshape(-1, 1, 2)], False, (40, 180, 30), 1, lineType=cv2.LINE_AA)
    cv2.rectangle(overlay, (x0, y0), (x1 - 1, y1 - 1), (200, 100, 20), 1)
    ok, encoded = cv2.imencode(".png", overlay)
    if not ok:
        raise ValueError("Could not generate the digitization overlay.")
    return Digitized(recovered, encoded.tobytes(), calibration, warnings)
