"""One measured pipeline shared by raw signals, demos and digitized images."""

from . import config as cfg
from . import plots, report
from .classify import classify
from .features import extract_features
from .peaks import pan_tompkins
from .preprocess import Signal, preprocess
from .quality import assess_quality


def analyze_signal(signal: Signal, *, explain: bool = True, include_plots: bool = True,
                   notch_hz: float | None = cfg.NOTCH_HZ,
                   allow_provider_default_temperature: bool = False) -> dict:
    """Measure first, quality-gate, apply rules, then optionally explain JSON."""
    processed = preprocess(signal, notch_hz=notch_hz)
    detection = pan_tompkins(processed.filtered, processed.fs)
    measurements = extract_features(detection.indices, processed.fs, processed.raw.size / processed.fs)
    quality = assess_quality(processed, detection.indices, signal.metadata)
    findings = classify(measurements, quality) if quality["status"] == "ok" else []
    warnings = list(processed.warnings)
    warnings.extend(signal.metadata.get("warnings", []))
    warnings.extend(["Single-lead rate and RR screening only; no PR/QT/ST/QRS-width or axis measurement.",
                     "Finding confidence is heuristic, not a validated disease probability.",
                     "Short-strip RR variability includes possible ectopy and detection errors.", cfg.DISCLAIMER])
    if quality["status"] != "ok":
        warnings.extend(quality["reasons"])
    result = {"status": quality["status"], "quality": quality, "measurements": measurements,
              "findings": findings, "explanation": None,
              "plots": plots.render_plots(processed, detection.indices) if include_plots else {},
              "warnings": list(dict.fromkeys(warnings)), "disclaimer": cfg.DISCLAIMER,
              "source": {key: value for key, value in signal.metadata.items() if key != "warnings"},
              "detector": {"method": "Own offline Pan-Tompkins", "polarity": detection.polarity,
                           "searchback_beats": detection.searchback_count}}
    if quality["status"] == "ok" and explain:
        explanation = report.explain_measurements(result, allow_provider_default_temperature=True) if allow_provider_default_temperature else report.explain_measurements(result)
        result["explanation"] = explanation["explanation"]
        result["explanation_error"] = explanation.get("error")
        if explanation.get("error"):
            result["warnings"].append(explanation["error"])
        if explanation.get("model"):
            result["explanation_model"] = explanation["model"]
        if explanation.get("explanation_settings"):
            result["explanation_settings"] = explanation["explanation_settings"]
            if explanation["explanation_settings"].get("used_provider_default"):
                result["warnings"].append("AI compatibility mode used the provider's default temperature after 0.2 was rejected.")
    elif quality["status"] != "ok":
        result["explanation_error"] = "Screening rules and AI explanation skipped: insufficient quality."
    else:
        result["explanation_error"] = "AI explanation not requested; measured results are available."
    return result
