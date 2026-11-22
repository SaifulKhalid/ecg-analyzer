import json
import subprocess

from ecg import report


def measured_payload():
    return {"measurements": {"hr_mean_bpm": 72, "sdnn_ms": 8}, "findings": [],
            "quality": {"status": "ok", "beat_count": 14}, "warnings": [],
            "plots": {"r_peaks": "data:image/png;base64,secret-image"}, "image": "must not be sent"}


def test_report_bridge_sends_only_measured_json_and_temperature(monkeypatch):
    seen = []

    def fake_run(command, **options):
        seen.append(json.loads(options["input"]))
        assert command[0] == "node"
        return subprocess.CompletedProcess(command, 0, json.dumps({"status_code": 200,
            "report": {"explanation": {"Summary": "Possible regular timing."}}, "model": "test-model"}), "")

    monkeypatch.delenv("ECG_LLM_ENABLED", raising=False)
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = report.explain_measurements(measured_payload())
    assert result["explanation"]["Summary"]
    assert seen[0]["temperature"] == 0.2
    assert set(seen[0]["payload"]) == {"measurements", "findings", "quality", "warnings"}
    assert "data:image" not in json.dumps(seen)


def test_bridge_failure_keeps_null_explanation_and_error(monkeypatch):
    monkeypatch.delenv("ECG_LLM_ENABLED", raising=False)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], 0, json.dumps({"status_code": 429, "error": "API rate limit reached."}), ""))
    result = report.explain_measurements(measured_payload())
    assert result["explanation"] is None and "limit" in result["error"]


def test_insufficient_quality_never_starts_bridge(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM called")))
    payload = measured_payload()
    payload["quality"]["status"] = "insufficient_quality"
    assert report.explain_measurements(payload)["explanation"] is None
