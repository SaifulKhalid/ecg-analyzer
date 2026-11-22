import pytest

from scripts import compare_holdout


def test_manifest_is_predeclared_deterministic_and_not_overwritten(tmp_path):
    manifest = compare_holdout.prepare(tmp_path)
    original = (tmp_path / "manifest.json").read_bytes()
    assert len(manifest["cases"]) == 10
    assert all(45 <= case["parameters"]["hr"] <= 130 for case in manifest["cases"])
    assert len({case["parameters"]["seed"] for case in manifest["cases"]}) == 10
    assert sum(case["parameters"]["irregular"] for case in manifest["cases"]) == 2
    assert sum(case["parameters"]["invert"] for case in manifest["cases"]) == 2
    assert compare_holdout.prepare(tmp_path) == manifest
    assert (tmp_path / "manifest.json").read_bytes() == original


def test_changed_measurement_code_blocks_holdout_run(tmp_path, monkeypatch):
    compare_holdout.prepare(tmp_path)
    monkeypatch.setattr(compare_holdout, "measurement_fingerprint", lambda: "changed")
    monkeypatch.setattr(compare_holdout, "estimate_gpt", lambda image: pytest.fail("Invalid study must not call GPT."))
    with pytest.raises(ValueError, match="Frozen measurement modules changed"):
        compare_holdout.run(tmp_path)
