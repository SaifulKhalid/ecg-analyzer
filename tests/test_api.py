import numpy as np
import pytest
import base64

from ecg.synth import generate_ecg


def test_health_catalog_and_demo_flow(api_client):
    request, calls = api_client
    code, health = request("/health")
    assert code == 200 and health["target_fs_hz"] == 250
    code, catalog = request("/samples")
    assert code == 200 and any(item["sample_id"] == "synth-regular" for item in catalog)
    code, result = request("/analyze-signal", {"sample_id": "synth-regular"})
    assert code == 200 and result["status"] == "ok"
    assert abs(result["measurements"]["hr_mean_bpm"] - 72) < 1
    assert len(calls) == 1 and result["explanation"]["Summary"]
    assert set(result["plots"]) == {"raw_filtered", "spectrum", "r_peaks", "rr_tachogram"}
    assert all(base64.b64decode(png).startswith(b"\x89PNG\r\n\x1a\n") for png in result["plots"].values())
    assert "warnings" in result
    assert result["disclaimer"] == "Educational screening tool, not a medical device."


def test_raw_millivolt_samples_use_same_measured_pipeline(api_client):
    request, calls = api_client
    generated = generate_ecg(83, fs=360, duration=12)
    code, result = request("/analyze-signal", {"fs": 360, "samples": generated.signal.samples.tolist()})
    assert code == 200 and result["status"] == "ok"
    assert abs(result["measurements"]["hr_mean_bpm"] - generated.true_hr) < 1
    assert result["measurements"]["fs_hz"] == 250
    assert len(calls) == 1


def test_quality_failure_and_opt_out_never_call_llm(api_client):
    request, calls = api_client
    code, result = request("/analyze-signal", {"fs": 250, "samples": np.zeros(2500).tolist()})
    assert code == 200 and result["status"] == "insufficient_quality"
    assert result["findings"] == [] and result["explanation"] is None
    assert result["quality"]["reasons"] and calls == []
    code, result = request("/analyze-signal", {"sample_id": "synth-regular", "explain": False})
    assert code == 200 and result["status"] == "ok" and result["explanation"] is None
    assert calls == []


def test_temperature_policy_is_opt_in_and_visible_in_response(api_client, monkeypatch):
    from ecg import report

    request, _ = api_client
    modes = []

    def fake(payload, *, allow_provider_default_temperature=False):
        modes.append(allow_provider_default_temperature)
        return {"explanation": {"Summary": "Possible measured timing."}, "error": None,
                "explanation_settings": {"requested_temperature": 0.2,
                    "effective_temperature": "provider_default" if allow_provider_default_temperature else 0.2,
                    "used_provider_default": allow_provider_default_temperature}}

    monkeypatch.setattr(report, "explain_measurements", fake)
    assert request("/analyze-signal", {"sample_id": "synth-regular"})[0] == 200
    code, result = request("/analyze-signal", {"sample_id": "synth-regular", "allow_provider_default_temperature": True})
    assert code == 200 and modes == [False, True]
    assert result["explanation_settings"]["used_provider_default"]
    assert any("provider's default temperature" in warning for warning in result["warnings"])


@pytest.mark.parametrize("body", [{}, {"sample_id": "../../config.local.js"},
                                  {"samples": [1, 2, 3], "fs": 250},
                                  {"samples": [1] * 500, "fs": 1},
                                  {"sample_id": "synth-regular", "fs": 250},
                                  {"samples": [1, float("nan")] * 250, "fs": 250}])
def test_invalid_signals_are_rejected_without_llm(api_client, body):
    request, calls = api_client
    code, _ = request("/analyze-signal", body)
    assert code == 422 and calls == []
