import numpy as np
import pytest

from ecg.features import extract_features
from ecg.peaks import detect_r_peaks, pan_tompkins
from ecg.preprocess import preprocess
from ecg.synth import generate_ecg
from scripts.validate import match_beats


@pytest.mark.parametrize("hr", [45, 58, 72, 100, 130])
@pytest.mark.parametrize("invert", [False, True])
def test_synthetic_rate_and_beat_detection_with_interference(hr, invert):
    synthetic = generate_ecg(hr, duration=20, noise=0.025, mains_amplitude=0.15,
                             baseline_wander=0.25, invert=invert)
    processed = preprocess(synthetic.signal)
    detected = detect_r_peaks(processed.filtered, processed.fs)
    metrics = match_beats(synthetic.r_peaks / synthetic.signal.fs, detected / processed.fs)
    features = extract_features(detected, processed.fs)
    assert metrics["sensitivity"] >= 99
    assert metrics["ppv"] >= 99
    assert abs(features["hr_mean_bpm"] - synthetic.true_hr) <= 1


def test_filters_attenuate_mains_and_baseline_without_moving_beats():
    synthetic = generate_ecg(72, duration=20, noise=0, mains_amplitude=0.3, baseline_wander=0.5)
    processed = preprocess(synthetic.signal)
    mains = np.argmin(np.abs(processed.frequencies - 50))
    baseline = np.argmin(np.abs(processed.frequencies - 0.33))
    assert processed.filtered_power[mains] < processed.raw_power[mains] / 1000
    assert processed.filtered_power[baseline] < processed.raw_power[baseline] / 10
    assert processed.raw.shape == processed.filtered.shape


def test_sixty_hz_notch_can_be_selected():
    synthetic = generate_ecg(75, duration=20, noise=0)
    time = np.arange(synthetic.signal.samples.size) / synthetic.signal.fs
    noisy = synthetic.signal.samples + 0.3 * np.sin(2 * np.pi * 60 * time)
    processed = preprocess(noisy, synthetic.signal.fs, notch_hz=60)
    index = np.argmin(np.abs(processed.frequencies - 60))
    assert processed.filtered_power[index] < processed.raw_power[index] / 1000


def test_rr_feature_definitions_and_nulls():
    features = extract_features(np.array([0, 250, 500, 800]), fs=250)
    rr = np.array([1000.0, 1000.0, 1200.0])
    assert features["hr_mean_bpm"] == pytest.approx(60_000 / rr.mean(), abs=0.001)
    assert features["sdnn_ms"] == pytest.approx(np.std(rr, ddof=1), abs=0.001)
    assert features["rmssd_ms"] == pytest.approx(np.sqrt(np.mean(np.diff(rr) ** 2)), abs=0.001)
    assert features["pnn50_percent"] == 50
    assert extract_features(np.array([250]))["hr_mean_bpm"] is None
    assert extract_features(np.array([250, 500]))["sdnn_ms"] is None


def test_matching_never_double_counts_a_reference_or_detection():
    result = match_beats(np.array([1.0, 2.0]), np.array([0.98, 1.04, 2.03]))
    assert (result["tp"], result["fp"], result["fn"]) == (2, 1, 0)
    missed = match_beats(np.array([1.0, 2.0]), np.array([1.0]))
    assert (missed["tp"], missed["fp"], missed["fn"]) == (1, 0, 1)


def test_resampling_preserves_physical_heart_rate():
    synthetic = generate_ecg(83, fs=360, duration=20, noise=0.015)
    processed = preprocess(synthetic.signal)
    peaks = detect_r_peaks(processed.filtered, processed.fs)
    assert processed.fs == 250
    assert processed.raw.size == 5000
    assert abs(extract_features(peaks)["hr_mean_bpm"] - synthetic.true_hr) < 1


@pytest.mark.parametrize("samples,fs", [([1, np.nan] * 300, 250), ([[1, 2]] * 300, 250),
                                        ([1] * 10, 250), ([1] * 500, 1)])
def test_bad_signal_inputs_fail_before_processing(samples, fs):
    with pytest.raises(ValueError):
        preprocess(samples, fs)


def test_flat_signal_produces_no_beats():
    processed = preprocess(np.zeros(2500), 250)
    assert detect_r_peaks(processed.filtered).size == 0


def test_search_back_recovers_a_low_amplitude_beat_without_extra_events():
    generated = generate_ecg(72, duration=30, noise=0)
    weak_peak = int(generated.r_peaks[12])
    generated.signal.samples[weak_peak - 75:weak_peak + 125] *= 0.35
    processed = preprocess(generated.signal)
    detected = pan_tompkins(processed.filtered, processed.fs)
    matched = match_beats(generated.r_peaks / generated.signal.fs, detected.indices / processed.fs)
    assert detected.searchback_count >= 1
    assert (matched["tp"], matched["fp"], matched["fn"]) == (35, 0, 0)
