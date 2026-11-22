"""Zero-phase baseline-wander, mains-hum, and muscle-noise suppression.

The 0.5 Hz high-pass suppresses slow baseline drift from respiration / motion.
The 40 Hz low-pass attenuates high-frequency muscle (EMG) artifact. A narrow
50 Hz notch targets mains hum; 60 Hz is selectable. Filtering cannot repair
clipping or missing information, and edges of a short strip are less reliable.
"""

from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
from scipy.signal import butter, iirnotch, resample_poly, sosfiltfilt, tf2sos

from . import config as cfg


@dataclass
class Signal:
    """One lead in mV, sampled uniformly at fs Hz; metadata contain provenance."""

    samples: np.ndarray
    fs: float = cfg.FS_TARGET
    metadata: dict = field(default_factory=dict)


@dataclass
class Preprocessed:
    raw: np.ndarray
    filtered: np.ndarray
    fs: float
    original_fs: float
    frequencies: np.ndarray
    raw_power: np.ndarray
    filtered_power: np.ndarray
    warnings: list[str] = field(default_factory=list)
    notch_hz: float | None = cfg.NOTCH_HZ

    @property
    def time(self) -> np.ndarray:
        return np.arange(self.raw.size) / self.fs


def power_spectrum(samples: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """One-sided Hann-window periodogram in mV²/Hz, calculated with NumPy FFT."""
    values = np.asarray(samples, dtype=float)
    window = np.hanning(values.size)
    centered = (values - values.mean()) * window
    power = np.abs(np.fft.rfft(centered)) ** 2 / max(fs * np.sum(window ** 2), cfg.NUMERICAL_EPSILON)
    if values.size % 2:
        power[1:] *= 2
    else:
        power[1:-1] *= 2
    return np.fft.rfftfreq(values.size, 1 / fs), power


def resample_signal(samples: np.ndarray, fs: float, target_fs: float = cfg.FS_TARGET) -> np.ndarray:
    """Anti-aliased rational resampling, preserving time in seconds."""
    values = np.asarray(samples, dtype=float)
    if np.isclose(fs, target_fs):
        return values.copy()
    ratio = Fraction(float(target_fs) / float(fs)).limit_denominator(10000)
    return resample_poly(values, ratio.numerator, ratio.denominator)


def preprocess(samples: np.ndarray | Signal, fs: float | None = None,
               notch_hz: float | None = cfg.NOTCH_HZ) -> Preprocessed:
    """Return raw / cleaned signals and spectra on a common 250 Hz time base.

    SOS forward-backward Butterworth filtering avoids a phase delay that would
    otherwise move R peaks. The notch removes mains interference before the
    broad band-pass. `notch_hz=None` disables it for controlled comparisons.
    Input must be a finite, uniformly sampled, single-lead mV signal.
    """
    if isinstance(samples, Signal):
        fs = samples.fs
        samples = samples.samples
    if fs is None or not np.isfinite(fs) or not cfg.MIN_INPUT_FS <= fs <= cfg.MAX_INPUT_FS:
        raise ValueError(f"fs must be between {cfg.MIN_INPUT_FS:g} and {cfg.MAX_INPUT_FS:g} Hz.")
    values = np.asarray(samples, dtype=float)
    if values.ndim != 1 or not values.size or not np.all(np.isfinite(values)):
        raise ValueError("samples must be a finite, one-dimensional mV array.")
    duration = values.size / fs
    if not cfg.MIN_SIGNAL_SECONDS <= duration <= cfg.MAX_SIGNAL_SECONDS:
        raise ValueError(f"Provide {cfg.MIN_SIGNAL_SECONDS:g}–{cfg.MAX_SIGNAL_SECONDS:g} seconds of one lead.")
    if notch_hz is not None and (not np.isfinite(notch_hz) or notch_hz not in (50, 60)):
        raise ValueError("notch_hz must be 50, 60, or null to disable the notch.")

    raw = resample_signal(values, fs)
    cleaned = raw.copy()
    warnings = ["Filtering may distort the first and last 0.5 seconds of a short strip."]
    if notch_hz is not None:
        b, a = iirnotch(notch_hz, cfg.NOTCH_Q, fs=cfg.FS_TARGET)
        cleaned = sosfiltfilt(tf2sos(b, a), cleaned)
    sos = butter(cfg.FILTER_ORDER, cfg.BANDPASS_HZ, btype="bandpass", fs=cfg.FS_TARGET, output="sos")
    cleaned = sosfiltfilt(sos, cleaned)
    frequencies, raw_power = power_spectrum(raw, cfg.FS_TARGET)
    _, filtered_power = power_spectrum(cleaned, cfg.FS_TARGET)
    return Preprocessed(raw, cleaned, cfg.FS_TARGET, float(fs), frequencies,
                        raw_power, filtered_power, warnings, notch_hz)
