import base64

import pytest

from scripts import compare_gpt


def row(truth, gpt, pipeline, *, gpt_status="ok", true_rhythm="regular", gpt_rhythm="regular"):
    return {"truth": {"heart_rate_bpm": truth, "rhythm": true_rhythm},
            "gpt": {"status": gpt_status, "heart_rate_bpm": gpt, "rhythm": gpt_rhythm},
            "pipeline": {"status": "ok", "heart_rate_bpm": pipeline, "rhythm": true_rhythm}}


def test_paired_error_comparison_uses_same_cases_and_reports_missing_coverage():
    metrics = compare_gpt.comparison_metrics([row(60, 70, 60.2), row(100, None, 100.2, gpt_status="failed", gpt_rhythm="unknown")])
    assert metrics["paired_count"] == 1
    assert metrics["gpt_hr_coverage"] == 1 and metrics["pipeline_hr_coverage"] == 2
    assert metrics["gpt_paired_hr_mae_bpm"] == 10
    assert metrics["pipeline_paired_hr_mae_bpm"] == pytest.approx(0.2)
    assert metrics["gpt_rhythm_accuracy_percent"] == 50
    assert metrics["pipeline_beats_gpt_hr_mae"]


def test_missing_gpt_predictions_never_produce_a_superiority_claim():
    metrics = compare_gpt.comparison_metrics([row(72, None, 72, gpt_status="not_run", gpt_rhythm="unknown")])
    assert metrics["gpt_paired_hr_mae_bpm"] is None
    assert not metrics["pipeline_beats_gpt_hr_mae"]


def test_gpt_baseline_bridge_receives_image_only(monkeypatch):
    seen = []

    def fake_bridge(request, timeout):
        seen.append(request)
        return {"status_code": 200, "report": {"heart_rate_bpm": 72, "rhythm": "regular"}, "model": "mock"}

    monkeypatch.setattr(compare_gpt, "call_bridge", fake_bridge)
    result = compare_gpt.estimate_gpt(b"test image")
    assert set(seen[0]) == {"kind", "image"}
    assert seen[0]["image"] == "data:image/png;base64," + base64.b64encode(b"test image").decode()
    assert result["heart_rate_bpm"] == 72


def test_offline_comparison_runs_all_fixed_images_without_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(compare_gpt, "call_bridge", lambda *args: pytest.fail("Offline run must not call GPT."))
    result = compare_gpt.run_comparison(tmp_path, offline=True)
    assert len(result["cases"]) == 10
    assert result["metrics"]["pipeline_hr_coverage"] == 10
    assert result["metrics"]["pipeline_all_hr_mae_bpm"] < 1
    assert result["metrics"]["gpt_hr_coverage"] == 0
    assert all(row["gpt"]["status"] == "not_run" for row in result["cases"])
    assert (tmp_path / "comparison.md").exists()


def test_same_gpt_prediction_is_reused_after_dsp_revision(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(compare_gpt.cfg, "COMPARISON_CASES", compare_gpt.cfg.COMPARISON_CASES[:1])
    monkeypatch.setattr(compare_gpt.cfg, "COMPARISON_PAUSE_SECONDS", 0)
    calls = []

    def fake_gpt(image):
        calls.append(image)
        return {"status": "ok", "heart_rate_bpm": 45, "rhythm": "regular", "model": "mock"}

    compare_gpt.run_comparison(tmp_path, gpt_requester=fake_gpt)
    path = tmp_path / "comparison.json"
    cached = json.loads(path.read_text())
    cached["code_fingerprint"] = "older DSP version"
    path.write_text(json.dumps(cached))
    revised = compare_gpt.run_comparison(tmp_path, gpt_requester=lambda image: pytest.fail("Same GPT image must not be rerun."))
    assert len(calls) == 1
    assert revised["cases"][0]["gpt"]["cached"]
    assert revised["cases"][0]["gpt"]["heart_rate_bpm"] == 45


def test_offline_history_preserves_predictions_after_client_change(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(compare_gpt.cfg, "COMPARISON_CASES", compare_gpt.cfg.COMPARISON_CASES[:1])
    monkeypatch.setattr(compare_gpt.cfg, "COMPARISON_PAUSE_SECONDS", 0)
    compare_gpt.run_comparison(tmp_path, gpt_requester=lambda image: {
        "status": "ok", "heart_rate_bpm": 45, "rhythm": "regular", "model": "original"})
    path = tmp_path / "comparison.json"
    original = json.loads(path.read_text())
    original["code_fingerprint"] = "older code"
    original["gpt_protocol_fingerprint"] = "original client protocol"
    path.write_text(json.dumps(original))
    result = compare_gpt.run_comparison(tmp_path, offline=True,
        gpt_requester=lambda image: pytest.fail("Offline history must not call GPT."))
    assert result["metrics"]["gpt_hr_coverage"] == 1
    assert result["cases"][0]["gpt"]["heart_rate_bpm"] == 45
    assert result["cases"][0]["gpt"]["source_protocol_fingerprint"] == "original client protocol"


def test_mixed_legacy_protocol_metadata_has_explicit_unknown_value(tmp_path):
    legacy = {"case_id": "legacy", **row(60, 60, 60)}
    recent = {"case_id": "recent", **row(70, 70, 70)}
    legacy["gpt"]["source_protocol_fingerprint"] = None
    recent["gpt"]["source_protocol_fingerprint"] = "recent"
    result = compare_gpt.write_report([legacy, recent], tmp_path, "measurement")
    assert result["gpt_prediction_protocol_fingerprints"] == ["recent", "unknown_legacy"]
    assert result["metrics"]["paired_count"] == 2


def test_unavailable_initial_gpt_score_is_not_imputed_or_declared_better(tmp_path):
    import json

    missing = compare_gpt.comparison_metrics([row(60, None, 60, gpt_status="not_run", gpt_rhythm="unknown")])
    (tmp_path / "comparison-initial.json").write_text(json.dumps({"metrics": missing}))
    current = {"case_id": "measured", **row(60, 65, 60)}
    result = compare_gpt.write_report([current], tmp_path, "measurement")
    text = (tmp_path / "comparison.md").read_text(encoding="utf-8")
    assert result["initial_run_metrics"]["gpt_paired_hr_mae_bpm"] is None
    assert "not available" in text
    assert "GPT had lower error" not in text
    assert "no initial advantage" in result["revision_note"]
