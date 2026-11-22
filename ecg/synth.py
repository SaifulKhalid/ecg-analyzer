"""Seeded Gaussian-sum P-QRS-T signals; synthetic timing is ground truth.

This is a simulator, not a model fitted to MIT-BIH. It does not reproduce all
clinical waveforms. Irregularity means varying RR timing, not simulated AFib.
"""

from dataclasses import dataclass

import numpy as np

from . import config as cfg
from .preprocess import Signal


@dataclass
class SyntheticECG:
    signal: Signal
    r_peaks: np.ndarray
    nominal_hr: float
    rhythm: str

    @property
    def true_hr(self) -> float:
        return float(60 / np.mean(np.diff(self.r_peaks) / self.signal.fs))


def generate_ecg(hr: float = cfg.SYNTH_DEFAULT_HR, *, fs: float = cfg.FS_TARGET,
                 duration: float = cfg.SYNTH_DEFAULT_DURATION,
                 noise: float = cfg.SYNTH_DEFAULT_NOISE,
                 mains_amplitude: float = 0.0, baseline_wander: float = 0.0,
                 irregular: bool = False, invert: bool = False,
                 seed: int = cfg.SYNTH_DEFAULT_SEED) -> SyntheticECG:
    """Generate mV samples with HR, white noise, 50 Hz hum and baseline drift.

    HR is nominal bpm; the actual finite-strip HR is `true_hr`, calculated from
    the simulator's quantized R times. Noise and interference amplitudes are mV.
    """
    if not 20 <= hr <= 250 or fs < cfg.MIN_INPUT_FS or duration < cfg.MIN_SIGNAL_SECONDS:
        raise ValueError("Use HR 20–250 bpm, adequate fs, and at least two seconds.")
    if min(noise, mains_amplitude, baseline_wander) < 0:
        raise ValueError("Noise amplitudes must be nonnegative.")
    rng = np.random.default_rng(seed)
    time = np.arange(int(round(fs * duration))) / fs
    beat_times = []
    next_beat = cfg.SYNTH_START_SECONDS
    beat_number = 0
    while next_beat < duration - cfg.SYNTH_END_MARGIN_SECONDS:
        beat_times.append(next_beat)
        factor = cfg.SYNTH_IRREGULAR_RR_FACTORS[beat_number % len(cfg.SYNTH_IRREGULAR_RR_FACTORS)] if irregular else 1.0
        next_beat += 60 / hr * factor
        beat_number += 1
    r_peaks = np.unique(np.rint(np.asarray(beat_times) * fs).astype(int))
    waveform = np.zeros_like(time)
    for r_time in r_peaks / fs:
        for amplitude, offset, sigma in cfg.SYNTH_WAVES:
            waveform += amplitude * np.exp(-0.5 * ((time - r_time - offset) / sigma) ** 2)
    if invert:
        waveform *= -1
    waveform += noise * rng.standard_normal(time.size)
    waveform += mains_amplitude * np.sin(2 * np.pi * cfg.NOTCH_HZ * time)
    waveform += baseline_wander * np.sin(2 * np.pi * cfg.SYNTH_BASELINE_HZ * time)
    rhythm = "irregular" if irregular else "regular"
    signal = Signal(waveform, fs, {"source": "synthetic", "rhythm": rhythm, "seed": seed})
    return SyntheticECG(signal, r_peaks, float(hr), rhythm)
