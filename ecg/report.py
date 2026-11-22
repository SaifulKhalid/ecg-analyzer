"""Explain measured JSON via the existing AgentRouter JavaScript client.

The subprocess sends JSON on stdin, never on a command line or in a public
file. The shared client owns credentials, headers, fallback and redaction.
"""

import json
import os
import subprocess

from . import config as cfg
from .grounding import check_explanation


def measurement_payload(payload: dict) -> dict:
    """Copy the measured whitelist and attach authoritative report definitions.

    Definitions come from existing config; they are not new measurements and
    never modify the API's measured values or the frozen DSP modules.
    """
    measured = {key: payload[key] for key in ("measurements", "findings", "quality", "warnings") if key in payload}
    measured["measurements"] = {**measured.get("measurements", {}), "definitions": {
        "pnn50_difference_threshold_ms": cfg.PNN50_MS,
        "bradycardia_bpm": cfg.BRADYCARDIA_BPM, "tachycardia_bpm": cfg.TACHYCARDIA_BPM,
        "irregular_rr_cv": cfg.IRREGULAR_RR_CV,
        "premature_rr_ratio": cfg.PREMATURE_RR_RATIO,
        "compensatory_rr_ratio": cfg.COMPENSATORY_RR_RATIO,
        "minimum_quality_beats": cfg.MIN_QUALITY_BEATS, "minimum_snr_db": cfg.MIN_SNR_DB,
        "plausible_rr_min_s": cfg.MIN_RR_SECONDS, "plausible_rr_max_s": cfg.MAX_RR_SECONDS,
        "note": "Definitions and screening thresholds are not observed measurements or validated disease probabilities.",
    }}
    return measured


def call_bridge(request: dict, timeout_seconds: float = cfg.LLM_TOTAL_TIMEOUT_SECONDS) -> dict:
    """Bounded private Node transport; provider failure never loses measurements."""
    request = {**request, "timeout_seconds": timeout_seconds,
               "attempt_timeout_seconds": cfg.LLM_TIMEOUT_SECONDS,
               "temperature": cfg.LLM_TEMPERATURE}
    try:
        completed = subprocess.run(
            ["node", str(cfg.ROOT / "scripts" / "agentrouter_bridge.mjs")],
            input=json.dumps(request, allow_nan=False), capture_output=True, text=True,
            encoding="utf-8", timeout=timeout_seconds + cfg.LLM_PROCESS_GRACE_SECONDS,
            cwd=cfg.ROOT,
        )
        if completed.returncode:
            return {"error": "AgentRouter bridge could not be started.", "status_code": 502}
        result = json.loads(completed.stdout)
        if not isinstance(result, dict):
            raise ValueError("Invalid bridge response")
        return result
    except subprocess.TimeoutExpired:
        return {"error": "AgentRouter explanation timed out; measured results are preserved.", "status_code": 504}
    except (OSError, ValueError, TypeError):
        return {"error": "AgentRouter is unavailable; measured results are preserved.", "status_code": 502}


def explain_measurements(payload: dict, *, allow_provider_default_temperature: bool = False) -> dict:
    """Production entry: whitelist measured JSON only; quality failures skip LLM."""
    if payload.get("quality", {}).get("status") != "ok":
        return {"explanation": None, "error": "Explanation skipped because signal quality is insufficient."}
    if os.environ.get("ECG_LLM_ENABLED", "1").lower() in ("0", "false", "off"):
        return {"explanation": None, "error": "AI explanation disabled; measured results are available."}
    measured = measurement_payload(payload)
    result = call_bridge({"kind": "explain", "payload": measured,
                          "allow_provider_default_temperature": allow_provider_default_temperature})
    if result.get("status_code") != 200:
        return {"explanation": None, "error": result.get("error", "AgentRouter explanation failed.")}
    provider_report = result.get("report")
    explanation = provider_report.get("explanation") if isinstance(provider_report, dict) else None
    if not isinstance(explanation, dict):
        return {"explanation": None, "error": "AgentRouter returned an invalid explanation."}
    grounding = check_explanation(explanation, measured)
    if grounding["status"] != "passed":
        return {"explanation": None,
                "error": "AI explanation rejected: unsupported numbers or unavailable measurements. Measured results are preserved.",
                "explanation_grounding": grounding, "model": result.get("model"),
                "explanation_settings": result.get("explanation_settings")}
    return {"explanation": explanation, "error": None, "explanation_grounding": grounding, "model": result.get("model"),
            "explanation_settings": result.get("explanation_settings"),
            "attempts": result.get("attempts"), "duration_ms": result.get("durationMs")}
