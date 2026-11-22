"""Own Pan-Tompkins detector: SciPy supplies filters, never beat decisions.

QRS energy is emphasized by 5–15 Hz filtering, a five-point derivative,
squaring and a 150 ms moving-window integral. Local-max decisions, adaptive
signal/noise levels, refractory / T-wave checks and search-back are written
here. Final R events are refined on the cleaned ECG within ±50 ms; absolute
local excursion accommodates inverted and mixed-polarity complexes.
"""

from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, sosfiltfilt

from . import config as cfg


@dataclass
class PeakDetection:
    indices: np.ndarray
    bandpassed: np.ndarray
    derivative: np.ndarray
    squared: np.ndarray
    integrated: np.ndarray
    candidates: np.ndarray
    thresholds: np.ndarray
    searchback_count: int
    polarity: str


def _local_maxima(values: np.ndarray) -> list[int]:
    """Our turning-point logic; plateau maxima select the last plateau sample."""
    return [index for index in range(1, values.size - 1)
            if values[index] >= values[index - 1] and values[index] > values[index + 1]]


def pan_tompkins(cleaned: np.ndarray, fs: float = cfg.FS_TARGET) -> PeakDetection:
    """Detect beat events with adaptive thresholds and RR-guided search-back.

    This is an offline, zero-phase Pan-Tompkins adaptation. No `find_peaks`,
    WFDB detector, or pretrained model is used. All returned indices refer to
    the supplied cleaned signal's time base.
    """
    values = np.asarray(cleaned, dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)) or values.size < int(fs * cfg.MIN_SIGNAL_SECONDS):
        raise ValueError("Provide a finite cleaned one-lead signal of at least two seconds.")
    if not np.isfinite(fs) or fs <= 2 * cfg.DETECTOR_BAND_HZ[1]:
        raise ValueError("Sampling frequency is too low for the detector band.")
    sos = butter(cfg.DETECTOR_FILTER_ORDER, cfg.DETECTOR_BAND_HZ, btype="bandpass", fs=fs, output="sos")
    bandpassed = sosfiltfilt(sos, values)
    derivative = np.convolve(bandpassed, np.asarray(cfg.DERIVATIVE_COEFFICIENTS) / cfg.DERIVATIVE_DIVISOR, mode="same")
    squared = derivative ** 2
    window = max(1, int(round(cfg.INTEGRATION_SECONDS * fs)))
    integrated = np.convolve(squared, np.ones(window) / window, mode="same")
    candidates = _local_maxima(integrated)
    thresholds = np.zeros_like(integrated)

    initial = integrated[: min(integrated.size, int(cfg.INITIALIZATION_SECONDS * fs))]
    signal_level = cfg.INITIAL_SIGNAL_SCALE * float(np.max(initial))
    noise_level = cfg.INITIAL_NOISE_SCALE * float(np.mean(initial))
    refractory = max(1, int(round(cfg.REFRACTORY_SECONDS * fs)))
    t_wave_window = int(round(cfg.T_WAVE_SECONDS * fs))
    half_window = max(1, window // 2)
    refine_window = max(1, int(round(cfg.REFINE_SECONDS * fs)))
    accepted: list[tuple[int, int, float]] = []  # envelope position, refined R, slope
    rejected: list[tuple[int, int, float, float]] = []
    searchback_count = 0

    def threshold() -> float:
        return max(noise_level + cfg.THRESHOLD_WEIGHT * (signal_level - noise_level), cfg.NUMERICAL_EPSILON)

    def locate(candidate: int) -> tuple[int, float]:
        # Anchor a centered energy window to its strongest bandpassed excursion,
        # then carry out the requested ±50 ms refinement on the cleaned signal.
        left, right = max(0, candidate - half_window), min(values.size, candidate + half_window + 1)
        anchor = left + int(np.argmax(np.abs(bandpassed[left:right])))
        start, stop = max(0, anchor - refine_window), min(values.size, anchor + refine_window + 1)
        local = values[start:stop]
        baseline_left, baseline_right = max(0, anchor - refractory), min(values.size, anchor + refractory + 1)
        baseline = float(np.median(values[baseline_left:baseline_right]))
        location = start + int(np.argmax(np.abs(local - baseline)))
        slope = float(np.max(np.abs(derivative[left:right])))
        return location, slope

    def eligible(location: int, slope: float) -> bool:
        if not accepted:
            return True
        interval = location - accepted[-1][1]
        if interval < refractory:
            return False
        if interval < t_wave_window and slope < cfg.T_WAVE_SLOPE_RATIO * accepted[-1][2]:
            return False
        return True

    for candidate in candidates:
        level = float(integrated[candidate])
        main_threshold = threshold()
        thresholds[candidate] = main_threshold
        location, slope = locate(candidate)
        if accepted:
            intervals = np.diff([beat[1] for beat in accepted[-(cfg.RR_HISTORY_BEATS + 1):]])
            expected_rr = float(np.median(intervals)) if intervals.size else fs
            if location - accepted[-1][1] > cfg.SEARCHBACK_RR_FACTOR * expected_rr:
                options = [beat for beat in rejected
                           if beat[1] > accepted[-1][1] + refractory
                           and beat[1] < location - refractory
                           and beat[2] >= cfg.SECONDARY_THRESHOLD_RATIO * main_threshold
                           and eligible(beat[1], beat[3])]
                if options:
                    recovered = max(options, key=lambda beat: beat[2])
                    accepted.append((recovered[0], recovered[1], recovered[3]))
                    signal_level = (1 - cfg.SEARCHBACK_UPDATE) * signal_level + cfg.SEARCHBACK_UPDATE * recovered[2]
                    searchback_count += 1
                    main_threshold = threshold()
        if level >= main_threshold and eligible(location, slope):
            accepted.append((candidate, location, slope))
            signal_level = (1 - cfg.ADAPTIVE_UPDATE) * signal_level + cfg.ADAPTIVE_UPDATE * level
            rejected = [beat for beat in rejected if beat[1] > location]
        else:
            noise_level = (1 - cfg.ADAPTIVE_UPDATE) * noise_level + cfg.ADAPTIVE_UPDATE * level
            rejected.append((candidate, location, level, slope))

    # A final long gap can contain a low-amplitude beat even with no later QRS.
    if len(accepted) >= 2:
        expected_rr = float(np.median(np.diff([beat[1] for beat in accepted[-(cfg.RR_HISTORY_BEATS + 1):]])))
        if values.size - accepted[-1][1] > cfg.SEARCHBACK_RR_FACTOR * expected_rr:
            options = [beat for beat in rejected if eligible(beat[1], beat[3])
                       and beat[2] >= cfg.SECONDARY_THRESHOLD_RATIO * threshold()]
            if options:
                recovered = max(options, key=lambda beat: beat[2])
                accepted.append((recovered[0], recovered[1], recovered[3]))
                searchback_count += 1
    indices = np.asarray(sorted({beat[1] for beat in accepted}), dtype=int)
    positive = np.count_nonzero(values[indices] >= 0) if indices.size else 0
    polarity = "upright" if positive > indices.size / 2 else "inverted" if positive < indices.size / 2 else "mixed"
    return PeakDetection(indices, bandpassed, derivative, squared, integrated,
                         np.asarray(candidates, dtype=int), thresholds, searchback_count, polarity)


def detect_r_peaks(cleaned: np.ndarray, fs: float = cfg.FS_TARGET) -> np.ndarray:
    """Convenient index-only interface to our detector."""
    return pan_tompkins(cleaned, fs).indices
