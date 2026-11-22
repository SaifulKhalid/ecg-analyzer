"""Signal-quality gate before screening rules or language-model calls.

SNR is a beat-repeatability estimate, not calibrated instrumentation SNR. A
median aligned QRS template is compared with residual beat-to-beat variation;
different beat morphologies can lower the estimate even in a readable signal.
"""

import numpy as np

from . import config as cfg
from .preprocess import Preprocessed


def assess_quality(processed: Preprocessed, r_peaks: np.ndarray,
                   metadata: dict | None = None) -> dict:
    """Gate on beat count, estimated SNR, amplitude and RR plausibility."""
    samples, fs = processed.filtered, processed.fs
    peaks = np.asarray(r_peaks, dtype=int)
    rr = np.diff(peaks) / fs
    radius = max(1, int(round(cfg.SNR_BEAT_WINDOW_SECONDS * fs)))
    windows = []
    for peak in peaks:
        if radius <= peak < samples.size - radius:
            segment = samples[peak - radius:peak + radius + 1].copy()
            edge_count = max(1, radius // 4)
            segment -= np.median(np.concatenate((segment[:edge_count], segment[-edge_count:])))
            windows.append(segment)
    snr_db = None
    if len(windows) >= cfg.MIN_QUALITY_BEATS:
        beats = np.asarray(windows)
        template = np.median(beats, axis=0)
        signal_power = float(np.mean(template ** 2))
        noise_power = float(np.median(np.mean((beats - template) ** 2, axis=1)))
        snr_db = float(np.clip(10 * np.log10((signal_power + cfg.NUMERICAL_EPSILON)
                                           / (noise_power + cfg.NUMERICAL_EPSILON)),
                               -cfg.MAX_REPORTED_SNR_DB, cfg.MAX_REPORTED_SNR_DB))
    implausible = (rr < cfg.MIN_RR_SECONDS) | (rr > cfg.MAX_RR_SECONDS)
    fraction = float(np.mean(implausible)) if rr.size else 1.0
    dynamic_range = float(np.percentile(samples, 99) - np.percentile(samples, 1))
    reasons = []
    if peaks.size < cfg.MIN_QUALITY_BEATS:
        reasons.append(f"Only {peaks.size} beats detected; at least {cfg.MIN_QUALITY_BEATS} are required.")
    if snr_db is None:
        reasons.append("Too few complete beat windows to estimate signal repeatability.")
    elif snr_db < cfg.MIN_SNR_DB:
        reasons.append(f"Estimated SNR {snr_db:.1f} dB is below the {cfg.MIN_SNR_DB:g} dB quality threshold.")
    if dynamic_range < cfg.MIN_SIGNAL_RANGE_MV:
        reasons.append("The filtered signal has too little voltage variation for reliable screening.")
    if fraction > cfg.MAX_IMPLAUSIBLE_RR_FRACTION:
        reasons.append(f"{fraction:.0%} of RR intervals fall outside {cfg.MIN_RR_SECONDS:g}–{cfg.MAX_RR_SECONDS:g} s.")
    metadata = metadata or {}
    if metadata.get("calibration_uncertain"):
        reasons.append("Image time calibration is uncertain; provide pixels_per_mm before screening.")
    if metadata.get("gap_fraction", 0) > cfg.TRACE_MAX_GAP_FRACTION:
        reasons.append("Too many image columns have no recoverable trace.")
    if metadata.get("longest_gap_s", 0) > cfg.TRACE_MAX_GAP_SECONDS:
        reasons.append("An image trace gap is too long for reliable beat timing.")
    return {"status": "insufficient_quality" if reasons else "ok", "reasons": reasons,
            "beat_count": int(peaks.size), "snr_db": round(snr_db, 2) if snr_db is not None else None,
            "snr_method": "Median aligned QRS template / beat-to-template residual (heuristic).",
            "rr_plausible_fraction": round(1 - fraction, 4),
            "signal_range_mv": round(dynamic_range, 4)}
