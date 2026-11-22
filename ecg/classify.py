"""Explainable rate and RR screening rules, never a clinical conclusion.

Confidence is an engineering badge reflecting signal repeatability, not a
validated probability of disease. RR irregularity is nonspecific and cannot
distinguish AFib from ectopy, artifact or other causes.
"""

import numpy as np

from . import config as cfg


def classify(measurements: dict, quality: dict) -> list[dict]:
    """Return possible / suggestive findings only after the quality gate passes."""
    if quality.get("status") != "ok":
        return []
    hr, cv = measurements.get("hr_mean_bpm"), measurements.get("rr_cv")
    rr = np.asarray(measurements.get("rr_intervals_ms", []), dtype=float)
    confidence = cfg.RULE_HIGH_CONFIDENCE if (quality.get("snr_db") or 0) >= cfg.HIGH_CONFIDENCE_SNR_DB else cfg.RULE_BASE_CONFIDENCE
    findings = []
    if hr is not None and hr < cfg.BRADYCARDIA_BPM:
        findings.append({"label": "Possible bradycardia (slow rate)", "confidence": confidence,
                         "evidence": [f"Mean HR {hr:.1f} bpm is below {cfg.BRADYCARDIA_BPM:g} bpm."]})
    if hr is not None and hr > cfg.TACHYCARDIA_BPM:
        findings.append({"label": "Possible tachycardia (fast rate)", "confidence": confidence,
                         "evidence": [f"Mean HR {hr:.1f} bpm exceeds {cfg.TACHYCARDIA_BPM:g} bpm."]})
    if cv is not None and cv > cfg.IRREGULAR_RR_CV:
        findings.append({"label": "Possible irregular rhythm / AFib screening flag", "confidence": confidence,
                         "evidence": [f"RR coefficient of variation {cv:.3f} exceeds {cfg.IRREGULAR_RR_CV:.2f}.",
                                      "RR variability alone cannot establish AFib; ectopy and artifact can also cause irregularity."]})
    if rr.size >= 2:
        median = float(np.median(rr))
        pairs = np.flatnonzero((rr[:-1] < cfg.PREMATURE_RR_RATIO * median)
                               & (rr[1:] > cfg.COMPENSATORY_RR_RATIO * median))
        if pairs.size:
            evidence = [f"{pairs.size} short–long RR pair(s); median RR {median:.1f} ms."]
            for index in pairs[:3]:
                evidence.append(f"RR {index + 1}: {rr[index]:.1f} ms < {cfg.PREMATURE_RR_RATIO:g}×median, "
                                f"followed by {rr[index + 1]:.1f} ms > {cfg.COMPENSATORY_RR_RATIO:g}×median.")
            findings.append({"label": "Possible premature-beat pattern", "confidence": confidence,
                             "evidence": evidence})
    if not findings and hr is not None and cv is not None:
        findings.append({"label": "Suggestive of regular RR timing within the screened rate range",
                         "confidence": cfg.REGULAR_TIMING_CONFIDENCE,
                         "evidence": [f"Mean HR {hr:.1f} bpm; RR coefficient of variation {cv:.3f}.",
                                      "Regular RR timing does not establish a sinus rhythm or exclude a condition."]})
    return findings
