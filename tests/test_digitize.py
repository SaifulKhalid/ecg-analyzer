import base64

import cv2
import numpy as np
import pytest

from ecg.digitize import digitize
from ecg.pipeline import analyze_signal
from ecg.plots import render_ecg_image
from ecg.synth import generate_ecg
from ecg import config as cfg
from ecg.preprocess import Signal


@pytest.mark.parametrize("hr", [45, 72, 130])
@pytest.mark.parametrize("pixels_per_mm", [6, 8, 12])
def test_calibrated_grid_round_trip_has_at_most_three_bpm_error(hr, pixels_per_mm):
    generated = generate_ecg(hr, noise=0.015, mains_amplitude=0.08, baseline_wander=0.15)
    image = render_ecg_image(generated.signal, pixels_per_mm=pixels_per_mm)
    recovered = digitize(image)
    result = analyze_signal(recovered.signal, explain=False, include_plots=False)
    assert recovered.signal.fs == 250
    assert not recovered.signal.metadata["calibration_uncertain"]
    assert recovered.calibration["pixels_per_mm"] == pytest.approx(pixels_per_mm, abs=0.25)
    assert result["status"] == "ok", result["quality"]
    assert abs(result["measurements"]["hr_mean_bpm"] - generated.true_hr) <= 3
    assert recovered.debug_overlay.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("options", [{"irregular": True}, {"invert": True}])
def test_image_round_trip_handles_irregular_and_inverted_strips(options):
    generated = generate_ecg(75, noise=0.01, **options)
    recovered = digitize(render_ecg_image(generated.signal))
    result = analyze_signal(recovered.signal, explain=False, include_plots=False)
    assert result["status"] == "ok", result["quality"]
    assert abs(result["measurements"]["hr_mean_bpm"] - generated.true_hr) <= 3
    if options.get("irregular"):
        assert any("irregular" in finding["label"] for finding in result["findings"])


def test_fractional_pixel_spacing_is_calibrated():
    generated = generate_ecg(83, noise=0.01)
    recovered = digitize(render_ecg_image(generated.signal, pixels_per_mm=7.5))
    result = analyze_signal(recovered.signal, explain=False, include_plots=False)
    assert recovered.calibration["pixels_per_mm"] == pytest.approx(7.5, abs=0.2)
    assert abs(result["measurements"]["hr_mean_bpm"] - generated.true_hr) <= 3


def test_missing_grid_requires_manual_scale_before_screening():
    generated = generate_ecg(72, noise=0.01)
    image = render_ecg_image(generated.signal, grid=False)
    assumed = digitize(image)
    result = analyze_signal(assumed.signal, explain=False, include_plots=False)
    assert result["status"] == "insufficient_quality"
    assert result["findings"] == [] and result["explanation"] is None
    assert any("grid" in warning.lower() for warning in assumed.warnings)
    # Crop off the printed header when no color grid can define the strip bounds.
    pixels = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
    recovered = digitize(image, pixels_per_mm=8, crop_box=[0, 28, pixels.shape[1], pixels.shape[0]])
    result = analyze_signal(recovered.signal, explain=False, include_plots=False)
    assert result["status"] == "ok"
    assert abs(result["measurements"]["hr_mean_bpm"] - generated.true_hr) <= 3


def test_paper_speed_gain_and_crop_overrides_preserve_timing():
    generated = generate_ecg(92, noise=0.01)
    image = render_ecg_image(generated.signal, pixels_per_mm=8, paper_speed=50, gain=5)
    pixels = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
    recovered = digitize(image, pixels_per_mm=8, paper_speed=50, gain=5,
                         crop_box=[0, 28, pixels.shape[1], pixels.shape[0]])
    result = analyze_signal(recovered.signal, explain=False, include_plots=False)
    assert result["status"] == "ok"
    assert abs(result["measurements"]["hr_mean_bpm"] - generated.true_hr) <= 3


def multipart_image(image, **fields):
    boundary = "ecg-roundtrip-boundary"
    chunks = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"strip.png\"\r\nContent-Type: image/png\r\n\r\n".encode())
    chunks.extend([image, f"\r\n--{boundary}--\r\n".encode()])
    return b"".join(chunks), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def test_analyze_image_multipart_uses_shared_pipeline_and_mocked_explanation(api_client):
    request, calls = api_client
    generated = generate_ecg(72, noise=0.01)
    data, headers = multipart_image(render_ecg_image(generated.signal), notch_hz=50)
    code, result = request("/analyze", data=data, headers=headers)
    assert code == 200 and result["status"] == "ok", result
    assert abs(result["measurements"]["hr_mean_bpm"] - generated.true_hr) <= 3
    assert base64.b64decode(result["plots"]["digitization"]).startswith(b"\x89PNG")
    assert len(calls) == 1 and result["explanation"]["Summary"]


def test_bad_image_and_bad_crop_do_not_call_llm(api_client):
    request, calls = api_client
    data, headers = multipart_image(b"not an image")
    assert request("/analyze", data=data, headers=headers)[0] == 422
    generated = generate_ecg()
    data, headers = multipart_image(render_ecg_image(generated.signal), crop_box="[-1,0,3,4]")
    assert request("/analyze", data=data, headers=headers)[0] == 422
    assert calls == []


def test_multilead_image_is_rejected_instead_of_blending_leads():
    generated = generate_ecg()
    image = render_ecg_image(generated.signal)
    pixels = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)[28:]
    stacked = np.vstack([pixels, pixels, pixels])
    ok, encoded = cv2.imencode(".png", stacked)
    assert ok
    with pytest.raises(ValueError, match="Multiple trace bands"):
        digitize(encoded.tobytes())


@pytest.mark.skipif(not (cfg.DATA_DIR / "100.dat").exists(), reason="MIT-BIH not cached; synthetic tests cover offline use.")
def test_mit_bih_image_hr_agrees_with_original_annotated_beat_times():
    import wfdb

    path = str(cfg.DATA_DIR / "100")
    header = wfdb.rdheader(path)
    count = int(12 * header.fs)
    record = wfdb.rdrecord(path, sampto=count, channels=[0])
    annotations = wfdb.rdann(path, "atr", sampto=count)
    reference = np.asarray([sample for sample, symbol in zip(annotations.sample, annotations.symbol)
                            if symbol in cfg.BEAT_ANNOTATIONS and sample < count]) / record.fs
    true_hr = 60 / np.mean(np.diff(reference))
    source = Signal(record.p_signal[:, 0], record.fs)
    recovered = digitize(render_ecg_image(source))
    result = analyze_signal(recovered.signal, explain=False, include_plots=False)
    assert result["status"] == "ok", result["quality"]
    assert abs(result["measurements"]["hr_mean_bpm"] - true_hr) <= 3
