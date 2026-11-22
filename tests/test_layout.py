import numpy as np
import pytest

from ecg.imageprep import prepare_image
from ecg.layout import detect_candidates
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
