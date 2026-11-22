"""Heart-rate and descriptive RR variability; no PR / QT / ST / QRS width.

All detected RR intervals, including possible ectopy, are retained. Therefore
SDNN here means the sample standard deviation of detected RR, not adjudicated
normal-to-normal autonomic HRV. Short strips do not support long-term HRV claims.
"""

import numpy as np

from . import config as cfg


def extract_features(r_peaks: np.ndarray, fs: float = cfg.FS_TARGET,
                     duration: float | None = None) -> dict:
    """Measure HR as 60 / mean RR, with min/max from individual RR intervals.

    SDNN uses sample standard deviation (ddof=1). RMSSD and pNN50 use consecutive
    RR differences; pNN50 uses strictly >50 ms. No interval trimming is applied.
    Values unavailable from too few peaks are null, not fabricated zeroes.
    """
    peaks = np.asarray(r_peaks, dtype=int)
    if peaks.ndim != 1 or np.any(peaks < 0) or np.any(np.diff(peaks) <= 0):
        raise ValueError("R-peak indices must be nonnegative and strictly increasing.")
    if not np.isfinite(fs) or fs <= 0:
        raise ValueError("fs must be positive.")
    rr = np.diff(peaks) / fs
    rr_ms = rr * 1000
    changes = np.diff(rr_ms)
    result = {
        "fs_hz": float(fs), "duration_s": duration, "beat_count": int(peaks.size),
        "hr_mean_bpm": None, "hr_min_bpm": None, "hr_max_bpm": None,
        "mean_rr_ms": None, "sdnn_ms": None, "rmssd_ms": None,
        "pnn50_percent": None, "rr_cv": None,
        "rr_intervals_ms": np.round(rr_ms, 3).tolist(),
        "r_peak_times_s": np.round(peaks / fs, 4).tolist(),
        "variability_note": "Descriptive RR variability includes all detected beats; not adjudicated NN HRV.",
    }
    if rr.size:
        instant_hr = 60 / rr
        result.update(hr_mean_bpm=float(60 / rr.mean()), hr_min_bpm=float(instant_hr.min()),
                      hr_max_bpm=float(instant_hr.max()), mean_rr_ms=float(rr_ms.mean()))
    if rr.size >= 2:
        result.update(sdnn_ms=float(np.std(rr_ms, ddof=1)),
                      rr_cv=float(np.std(rr, ddof=1) / rr.mean()))
    if changes.size:
        result.update(rmssd_ms=float(np.sqrt(np.mean(changes ** 2))),
                      pnn50_percent=float(np.mean(np.abs(changes) > cfg.PNN50_MS) * 100))
    for key, value in result.items():
        if isinstance(value, float):
            result[key] = round(value, 4 if key == "rr_cv" else 3)
    return result
