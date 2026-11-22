import numpy as np
import pytest

from ecg.synth import generate_ecg
from scripts.validate import match_beats
from scripts.validate_long import detect_windowed, signal_windows


def test_windows_cover_all_samples_once_and_respect_processing_limit():
    count, fs = 650000, 360
    windows = signal_windows(count, fs, 290, 5)
    assert windows[0]["central_start"] == 0
    assert windows[-1]["central_stop"] == count
    assert sum(item["central_stop"] - item["central_start"] for item in windows) == count
    assert all(first["central_stop"] == second["central_start"] for first, second in zip(windows, windows[1:]))
    assert all(2 <= (item["stop"] - item["start"]) / fs <= 300 for item in windows)
    assert windows[1]["start"] < windows[1]["central_start"] < windows[1]["central_stop"] < windows[1]["stop"]


def test_short_tail_has_enough_filter_context_and_seam_beats_are_not_duplicated():
    # Several true R events land exactly at central seams; the final core is 0.5 s.
    generated = generate_ecg(120, fs=360, duration=32, noise=0,
                             mains_amplitude=0.08, baseline_wander=0.1)
    detected, details = detect_windowed(generated.signal.samples, 360, 10.5, 3)
    truth = generated.r_peaks / 360
    matched = match_beats(truth, detected)
    assert (matched["tp"], matched["fp"], matched["fn"]) == (len(truth), 0, 0)
    assert np.all(np.diff(detected) > 0.2)
    assert sum(item["retained_beats"] for item in details) == len(detected)
    assert details[-1]["central_stop_s"] - details[-1]["central_start_s"] == 0.5
    assert details[-1]["processing_stop_s"] - details[-1]["processing_start_s"] >= 2


@pytest.mark.parametrize("central,context", [(300, 5), (0, 5), (290, -1), (float("nan"), 5)])
def test_invalid_window_protocol_fails_early(central, context):
    with pytest.raises(ValueError):
        signal_windows(650000, 360, central, context)
