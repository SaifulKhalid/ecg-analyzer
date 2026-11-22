import numpy as np
import pytest

from ecg.imageprep import prepare_image
from ecg.layout import detect_candidates, select_region, NO_GRID_NOTE
from tests.report_synth import render_report, variants


@pytest.mark.parametrize("options", [
    {}, {"ppm":4}, {"grid":"red"}, {"grid":"green"}, {"grid":"blue"},
    {"grayscale":True}, {"grid":None,"grayscale":True}, {"rotation":90},
    {"rotation":180}, {"rotation":270}, {"skew":3}, {"jpeg_quality":60}, {"photo":True},
])
def test_full_report_proposes_bottom_single_lead_strip(options):
    fixture = render_report(**options)
    prepared = prepare_image(fixture.image)
    candidates = detect_candidates(prepared.image)
    assert candidates and candidates[0].kind == "long strip"
    box = candidates[0].box
    assert (box[2]-box[0]) >= prepared.image.shape[1]*0.85
    assert box[1] > prepared.image.shape[0]*0.65
    assert (box[3]-box[1]) < prepared.image.shape[0]*0.2


def test_cells_are_not_stitched_when_rhythm_strip_is_absent():
    prepared = prepare_image(render_report(rhythm=False).image)
    candidates = detect_candidates(prepared.image)
    assert len(candidates) >= 8
    assert all(candidate.kind == "segment" for candidate in candidates)
    assert all(candidate.box[2]-candidate.box[0] < prepared.image.shape[1]*0.3 for candidate in candidates)


def test_blank_and_random_pixels_have_no_trace_candidates():
    assert detect_candidates(np.full((300, 500, 3), 255, np.uint8)) == []
    assert detect_candidates(np.random.default_rng(90).integers(0, 256, (300, 500, 3), dtype=np.uint8)) == []


def test_report_manifest_has_at_least_thirty_distinct_variants():
    cases = variants()
    assert len(cases) >= 30
    assert len({tuple(sorted(case.items())) for case in cases}) == len(cases)


@pytest.mark.parametrize("options", [{}, {"grid":"green"}, {"grid":"blue"}, {"grayscale":True}, {"grid":None,"grayscale":True}])
def test_selection_measures_correct_rhythm_strip_and_caps_evaluation(options):
    fixture = render_report(**options)
    prepared = prepare_image(fixture.image)
    selection = select_region(prepared.image)
    assert selection.result["status"] == "ok", selection.result["quality"]
    assert selection.candidate.kind == "long strip"
    assert selection.candidate.box[1] > prepared.image.shape[0]*0.7
    assert abs(selection.result["measurements"]["hr_mean_bpm"]-fixture.hr) <= 3
    assert 1 <= len(selection.candidates) <= 8
    assert [item["rank"] for item in selection.candidates] == list(range(1, len(selection.candidates)+1))
    if options.get("grid", "pink") is None:
        assert NO_GRID_NOTE in selection.notes
        assert selection.result["quality"]["signal_range_mv"] is None
        assert selection.recovered.calibration["gain"] is None


def test_manual_region_wins_without_running_detection(monkeypatch):
    from ecg import layout
    fixture = render_report()
    prepared = prepare_image(fixture.image, automatic_orientation=False)
    monkeypatch.setattr(layout, "detect_candidates", lambda image: pytest.fail("Automatic selection ran with a manual crop."))
    selection = select_region(prepared.image, crop_box=fixture.target_box)
    assert selection.candidate.box == fixture.target_box
    assert selection.result["status"] == "ok"


def test_short_cells_and_uncalibrated_cells_have_clear_quality_notes():
    selection = select_region(prepare_image(render_report(rhythm=False, hr=120).image).image)
    assert selection.result["status"] == "insufficient_quality"
    assert selection.result["findings"] == []
    assert any("too short" in reason for reason in selection.result["quality"]["reasons"])
    unknown = select_region(prepare_image(render_report(rhythm=False, grid=None).image).image)
    assert unknown.result["status"] == "insufficient_quality"
    assert unknown.result["measurements"]["hr_mean_bpm"] is None
    assert "Time scale could not be determined." in unknown.result["notes"]
