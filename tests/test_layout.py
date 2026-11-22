import numpy as np
import pytest
import io
import base64
import cv2
from PIL import Image, ImageDraw
from fastapi import UploadFile

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
    assert selection.result["measurements"]["hr_mean_bpm"] is None
    assert any("too short" in reason for reason in selection.result["quality"]["reasons"])
    unknown = select_region(prepare_image(render_report(rhythm=False, grid=None).image).image)
    assert unknown.result["status"] == "insufficient_quality"
    assert unknown.result["measurements"]["hr_mean_bpm"] is None
    assert "Time scale could not be determined." in unknown.result["notes"]


def _image_bytes(picture, format="PNG", **options):
    buffer = io.BytesIO()
    picture.save(buffer, format=format, **options)
    return buffer.getvalue()


def _call_image_api(data, *, crop=None, pixels=None):
    import json
    from ecg.api import analyze_image_endpoint
    return analyze_image_endpoint(UploadFile(file=io.BytesIO(data), filename="fixture.png"),
        pixels_per_mm=pixels, paper_speed=25, gain=10, crop_box=json.dumps(crop) if crop is not None else None,
        explain=False, allow_provider_default_temperature=False, notch_hz=50)


@pytest.mark.parametrize("case", ["blank", "noise", "photo", "tiny", "large", "rgba", "gray-jpeg", "cmyk-jpeg", "webp", "rotated", "skewed", "jpeg60", "low-resolution"])
def test_image_robustness_always_has_structured_response_and_plain_note(case):
    base = Image.open(io.BytesIO(render_report().image)).convert("RGB")
    if case == "blank":
        data = _image_bytes(Image.new("RGB", (500, 300), "white"))
    elif case == "noise":
        data = _image_bytes(Image.fromarray(np.random.default_rng(91).integers(0, 256, (300, 500, 3), dtype=np.uint8)))
    elif case == "photo":
        photo = Image.new("RGB", (500, 300), (133, 185, 226))
        painter = ImageDraw.Draw(photo)
        painter.ellipse((350, 20, 410, 80), fill=(250, 224, 130))
        painter.polygon([(0, 230), (110, 100), (280, 235), (400, 160), (500, 240), (500, 300), (0, 300)], fill=(54, 102, 65))
        data = _image_bytes(photo, "JPEG", quality=90)
    elif case == "tiny":
        data = _image_bytes(Image.new("RGB", (50, 50), "white"))
    elif case == "large":
        data = _image_bytes(Image.new("RGB", (6000, 4000), "white"))
    elif case == "rgba":
        picture = base.convert("RGBA")
        picture.putpixel((0, 0), (0, 0, 0, 0))
        data = _image_bytes(picture)
    elif case == "gray-jpeg":
        data = _image_bytes(base.convert("L"), "JPEG", quality=90)
    elif case == "cmyk-jpeg":
        data = _image_bytes(base.convert("CMYK"), "JPEG", quality=90)
    elif case == "webp":
        data = _image_bytes(base, "WEBP", quality=90)
    else:
        data = render_report(**{"rotated":{"rotation":90}, "skewed":{"skew":3}, "jpeg60":{"jpeg_quality":60}, "low-resolution":{"ppm":4}}[case]).image
    result = _call_image_api(data)
    assert result["status"] in ("ok", "insufficient_quality", "no_ecg_detected")
    assert isinstance(result["notes"], list) and result["notes"]
    assert all(isinstance(note, str) for note in result["notes"])
    assert "region_selection" in result and "prepared_image" in result["plots"]
    assert "measurements" in result and "quality" in result and result["explanation"] is None
    if case in ("blank", "noise", "tiny", "large"):
        assert result["status"] == "no_ecg_detected"
    if case == "large":
        assert max(result["region_selection"]["image_size"]) == 3000
    if case in ("rgba", "gray-jpeg", "cmyk-jpeg", "webp", "rotated", "skewed", "jpeg60", "low-resolution"):
        assert result["status"] == "ok", result["notes"]
        assert abs(result["measurements"]["hr_mean_bpm"]-72) <= 3


def test_exif_orientation_and_alpha_are_applied_before_layout():
    fixture = render_report()
    upright = Image.open(io.BytesIO(fixture.image)).convert("RGB")
    sideways = upright.rotate(90, expand=True)
    exif = sideways.getexif(); exif[274] = 6
    prepared = prepare_image(_image_bytes(sideways, "JPEG", quality=95, exif=exif))
    assert prepared.image.shape[1] > prepared.image.shape[0]
    assert any(operation.get("source") == "EXIF" for operation in prepared.operations)
    transparent = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    normalized = prepare_image(_image_bytes(transparent))
    assert np.all(normalized.image == 255)


def test_frozen_fingerprint_is_the_original_value():
    from scripts.compare_holdout import measurement_fingerprint
    assert measurement_fingerprint() == "df4b1c6ac4feb0db7dbb91fa6a4f32ef779da9f2f91aba53fab7a0f7b75b5925"


@pytest.mark.parametrize("rhythm", [False, True])
def test_touching_leads_are_split_at_repeated_label_positions(rhythm):
    prepared = prepare_image(render_report(rhythm=rhythm, join_cells=True).image)
    candidates = detect_candidates(prepared.image)
    long = [candidate for candidate in candidates if candidate.kind == "long strip"]
    assert len(long) == int(rhythm)
    assert all(candidate.box[2]-candidate.box[0] < prepared.image.shape[1]*0.3 for candidate in candidates if candidate.kind == "segment")
    selection = select_region(prepared.image)
    assert selection.result["status"] == ("ok" if rhythm else "insufficient_quality")


def test_leading_calibration_pulse_is_trimmed_without_changing_hr():
    fixture = render_report()
    image = np.array(Image.open(io.BytesIO(fixture.image)).convert("RGB"))
    baseline = 22*6+3*32*6+20*6
    cv2.line(image, (8*6, baseline), (10*6, baseline), (12, 12, 12), 1)
    selection = select_region(image)
    assert selection.candidate.box[0] >= 8*6
    assert selection.result["status"] == "ok"
    assert abs(selection.result["measurements"]["hr_mean_bpm"]-72) <= 3


def test_full_prepared_image_overlay_changes_only_selected_region():
    result = _call_image_api(render_report().image)
    original = np.array(Image.open(io.BytesIO(base64.b64decode(result["plots"]["prepared_image"]))).convert("RGB"))
    overlay = np.array(Image.open(io.BytesIO(base64.b64decode(result["plots"]["digitization"]))).convert("RGB"))
    assert original.shape == overlay.shape
    left, top, right, bottom = result["region_selection"]["box"]
    difference = np.any(original != overlay, axis=2)
    assert difference[top:bottom, left:right].sum() > 500
    difference[top:bottom, left:right] = False
    assert not difference.any()
