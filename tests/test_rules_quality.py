import numpy as np
import pytest

from ecg.classify import classify
from ecg.features import extract_features
from ecg.peaks import detect_r_peaks
from ecg.preprocess import preprocess
from ecg.quality import assess_quality
from ecg.synth import generate_ecg


@pytest.mark.parametrize("hr,flag", [(45, "bradycardia"), (72, "regular RR"), (130, "tachycardia")])
def test_screening_rules_follow_measured_rates(hr, flag):
    generated = generate_ecg(hr)
    processed = preprocess(generated.signal)
    peaks = detect_r_peaks(processed.filtered)
    quality = assess_quality(processed, peaks)
    assert quality["status"] == "ok", quality
    findings = classify(extract_features(peaks), quality)
    assert any(flag in finding["label"] for finding in findings)
    assert all("Possible" in f["label"] or "Suggestive" in f["label"] for f in findings)


def test_irregular_and_short_long_rr_patterns_have_numerical_evidence():
    rr = np.array([1000, 1000, 600, 1500, 1000, 1000])
    peaks = np.rint(np.concatenate(([0], np.cumsum(rr))) / 4).astype(int)
    findings = classify(extract_features(peaks), {"status": "ok", "snr_db": 20})
    assert any("irregular" in f["label"] for f in findings)
    assert any("premature" in f["label"] for f in findings)
    assert all(f["evidence"] and 0 <= f["confidence"] <= 1 for f in findings)


def test_flat_short_and_noise_recordings_are_not_screened():
    for signal in [np.zeros(2500), np.random.default_rng(33).normal(0, 0.5, 5000)]:
        processed = preprocess(signal, 250)
        peaks = detect_r_peaks(processed.filtered)
        quality = assess_quality(processed, peaks)
        assert quality["status"] == "insufficient_quality", quality
        assert classify(extract_features(peaks), quality) == []
    generated = generate_ecg(45, duration=3)
    processed = preprocess(generated.signal)
    peaks = detect_r_peaks(processed.filtered)
    assert assess_quality(processed, peaks)["status"] == "insufficient_quality"


def test_uncertain_image_calibration_blocks_screening():
    generated = generate_ecg(72)
    processed = preprocess(generated.signal)
    peaks = detect_r_peaks(processed.filtered)
    quality = assess_quality(processed, peaks, {"calibration_uncertain": True})
    assert quality["status"] == "insufficient_quality"
    assert any("calibration" in reason for reason in quality["reasons"])
