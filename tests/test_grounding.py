import json

import pytest

from ecg import config as cfg
from ecg.grounding import SECTIONS, check_explanation
from ecg.report import measurement_payload


def payload():
    # Actual saved live response; no new model requests in these tests.
    return measurement_payload(json.loads((cfg.RESULTS_DIR / "llm-compatibility.json").read_text(encoding="utf-8")))


def explanation(summary):
    return {section: summary if section == "Summary" else "Educational screening tool, not a medical device."
            for section in SECTIONS}


def test_actual_saved_five_section_report_is_numerically_grounded():
    saved = json.loads((cfg.RESULTS_DIR / "llm-compatibility.json").read_text(encoding="utf-8"))
    result = check_explanation(saved["explanation"], measurement_payload(saved))
    assert result["status"] == "passed", result
    assert result["checked_numeric_claims"] >= 15


def test_new_live_guarded_reply_still_passes_the_final_guard():
    saved = json.loads((cfg.RESULTS_DIR / "grounded-explanation.json").read_text(encoding="utf-8"))
    result = check_explanation(saved["explanation"], measurement_payload(saved))
    assert result["status"] == "passed", result
    assert result["checked_numeric_claims"] == saved["explanation_grounding"]["checked_numeric_claims"]


@pytest.mark.parametrize("text", [
    "Mean HR 72 bpm; SDNN 1.9 ms; RMSSD 3.27 ms.",
    "Mean HR 72.01 bpm; minimum HR 71.8 bpm; maximum HR 72.1 bpm.",
    "Mean RR 0.833 seconds; SDNN 0.001922 seconds.",
    "RR CV 0.23%; confidence 75%.",
    "Rates from 71.77 to 72.115 bpm.",
    "pNN50 is 0%, using a difference threshold greater than 50 ms.",
    "Mean HR 72.009 bpm is above the 60 bpm bradycardia threshold.",
    "No PR/QT/ST/QRS-width or axis measurements are available. Filtering affects the first and last 0.5 seconds.",
    "This 12-second strip has mean HR 72.009 bpm and SDNN 1.922 ms.",
    "Mean HR 72.009 bpm over 12 seconds; RMSSD 3.266 ms.",
    "The 75% confidence badge is not a disease probability.",
    "RR intervals range from 832 to 836 ms; mean RR interval is 833.231 ms.",
])
def test_rounding_conversions_definitions_and_limits_are_allowed(text):
    result = check_explanation(explanation(text), payload())
    assert result["status"] == "passed", result


@pytest.mark.parametrize("text", [
    "Mean HR 140 bpm.",
    "Mean HR 14 bpm.",               # Beat count cannot become heart rate.
    "Mean HR 60 bpm.",               # A cutoff is not an observed mean.
    "SDNN 3.266 ms.",                # RMSSD cannot become SDNN.
    "SDNN 50 ms.",                   # pNN50 definition cannot become SDNN.
    "pNN50 was 50%.",                # The 50 ms definition is not a percentage.
    "Mean HR 72.2 bpm.",             # Outside this displayed rounding precision.
    "confidence 0.75 bpm.",          # A confidence badge cannot become a rate.
    "QTc is 450 ms.",
    "QRS width was 72 ms.",
    "ST is normal.",
    "The axis is normal.",
    "QT is not prolonged.",           # Negating abnormality still invents QT assessment.
    "There is a 75% chance of AFib.", # A confidence badge is not disease probability.
    "The patient has atrial fibrillation.",
    "RR interval was 50 ms.",         # A definition cannot become an observed RR interval.
    "Mean RR interval was 832 ms.",   # A single interval cannot become the measured mean.
])
def test_invented_mislabeled_or_unimplemented_measurements_are_rejected(text):
    result = check_explanation(explanation(text), payload())
    assert result["status"] == "rejected"


def test_partial_sections_are_rejected():
    assert check_explanation({"Summary": "Possible timing."}, payload())["status"] == "rejected"


def test_definitions_are_report_only_and_do_not_mutate_input_measurements():
    original = {"measurements": {"hr_mean_bpm": 72}, "quality": {"status": "ok"},
                "findings": [], "warnings": [], "image": "not-sent", "samples": [1, 2]}
    measured = measurement_payload(original)
    assert original["measurements"] == {"hr_mean_bpm": 72}
    assert set(measured) == {"measurements", "quality", "findings", "warnings"}
    assert "image" not in measured and "samples" not in measured
