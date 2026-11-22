"""Fixed, matched-image GPT-only versus measured-pipeline comparison.

Default: make bounded AgentRouter calls, checkpoint after every case, and reuse
successful predictions for unchanged images / code. --offline renders and
measures all cases with cached GPT replies or explicit 'not run'. No training.
"""

import argparse
import base64
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecg import config as cfg
from ecg.digitize import digitize
from ecg.pipeline import analyze_signal
from ecg.plots import render_ecg_image
from ecg.report import call_bridge
from ecg.synth import generate_ecg


def code_fingerprint() -> str:
    names = ["ecg/config.py", "ecg/preprocess.py", "ecg/peaks.py", "ecg/features.py",
             "ecg/classify.py", "ecg/quality.py", "ecg/digitize.py", "ecg/plots.py",
             "lib/analyze.js", "scripts/agentrouter_bridge.mjs"]
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode())
        digest.update((cfg.ROOT / name).read_bytes())
    return digest.hexdigest()


def gpt_protocol_fingerprint() -> str:
    """Cache GPT by its unchanged protocol and image, separately from DSP code."""
    digest = hashlib.sha256()
    for name in ("lib/analyze.js", "lib/agentrouter-config.js", "scripts/agentrouter_bridge.mjs"):
        digest.update((cfg.ROOT / name).read_bytes())
    return digest.hexdigest()


def estimate_gpt(image_bytes: bytes) -> dict:
    """The only GPT input is the exact image. No truth / DSP values cross over."""
    image = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    result = call_bridge({"kind": "baseline", "image": image}, cfg.COMPARISON_TIMEOUT_SECONDS)
    if result.get("status_code") != 200:
        return {"status": "failed", "heart_rate_bpm": None, "rhythm": "unknown",
                "error": result.get("error", "AgentRouter request failed."),
                "status_code": result.get("status_code")}
    report = result.get("report", {})
    value = report.get("heart_rate_bpm")
    if value is not None and (not isinstance(value, (float, int)) or not np.isfinite(value)):
        return {"status": "failed", "heart_rate_bpm": None, "rhythm": "unknown", "error": "Invalid GPT HR value."}
    return {"status": "ok" if value is not None else "no_estimate", "heart_rate_bpm": value,
            "rhythm": report.get("rhythm", "unknown"), "model": result.get("model"),
            "attempts": result.get("attempts"), "duration_ms": result.get("durationMs")}


def comparison_metrics(rows: list[dict]) -> dict:
    """Use identical successful pairs for the head-to-head HR comparison.

    Report all-case pipeline errors and prediction coverage separately. Unknown
    rhythm / missing replies count as misses in overall timing-label accuracy.
    """
    pipeline = [row for row in rows if row["pipeline"]["status"] == "ok"
                and row["pipeline"]["heart_rate_bpm"] is not None]
    gpt = [row for row in rows if row["gpt"]["status"] == "ok" and row["gpt"]["heart_rate_bpm"] is not None]
    pairs = [row for row in pipeline if row in gpt]

    def mae(selected, method):
        return float(np.mean([abs(row[method]["heart_rate_bpm"] - row["truth"]["heart_rate_bpm"])
                              for row in selected])) if selected else None

    def accurate(selected, method):
        return sum(abs(row[method]["heart_rate_bpm"] - row["truth"]["heart_rate_bpm"])
                   <= cfg.IMAGE_MAX_HR_ERROR_BPM for row in selected)

    total = len(rows)
    paired_gpt_mae, paired_pipeline_mae = mae(pairs, "gpt"), mae(pairs, "pipeline")
    return {"case_count": total, "gpt_hr_coverage": len(gpt), "pipeline_hr_coverage": len(pipeline),
            "paired_count": len(pairs), "gpt_paired_hr_mae_bpm": paired_gpt_mae,
            "pipeline_paired_hr_mae_bpm": paired_pipeline_mae,
            "pipeline_all_hr_mae_bpm": mae(pipeline, "pipeline"),
            "gpt_all_hr_mae_bpm": mae(gpt, "gpt"),
            "gpt_hr_within_3_bpm_count": accurate(gpt, "gpt"),
            "pipeline_hr_within_3_bpm_count": accurate(pipeline, "pipeline"),
            "gpt_rhythm_correct_count": sum(row["gpt"].get("rhythm") == row["truth"]["rhythm"] for row in rows),
            "pipeline_rhythm_correct_count": sum(row["pipeline"].get("rhythm") == row["truth"]["rhythm"] for row in rows),
            "gpt_rhythm_accuracy_percent": 100 * sum(row["gpt"].get("rhythm") == row["truth"]["rhythm"] for row in rows) / total if total else None,
            "pipeline_rhythm_accuracy_percent": 100 * sum(row["pipeline"].get("rhythm") == row["truth"]["rhythm"] for row in rows) / total if total else None,
            "pipeline_beats_gpt_hr_mae": bool(pairs and paired_pipeline_mae < paired_gpt_mae)}


def write_report(rows: list[dict], output_dir: Path, fingerprint: str) -> dict:
    metrics = comparison_metrics(rows)
    summary = {"generated_utc": datetime.now(timezone.utc).isoformat(), "code_fingerprint": fingerprint,
               "gpt_protocol_fingerprint": gpt_protocol_fingerprint(),
               "seed": cfg.COMPARISON_SEED, "duration_seconds": cfg.COMPARISON_DURATION_SECONDS,
               "gpt_input": "same image only; printed calibration; model default temperature",
               "pipeline_input": "same image -> auto digitization -> own DSP; LLM explanation disabled",
               "truth_definition": "60 / mean RR between simulator R events; rhythm is regular/irregular timing only",
               "metrics": metrics, "cases": rows}
    lines = ["# GPT-only versus measured ECG pipeline", "", cfg.DISCLAIMER, "",
             f"Generated: {summary['generated_utc']}", "",
             "Ten fixed 12-second synthetic single-lead images, nominal HR 45–130 bpm,",
             "including two irregular RR patterns and noisy / 50 Hz / baseline-wander cases.",
             "Each method sees the **identical PNG**. Ground-truth HR is **60 / mean simulator RR**;",
             "finite-strip irregular HR can differ from nominal HR. No dataset training.", "",
             "| Case | True HR | True RR timing | GPT-only HR | GPT RR timing | Pipeline HR | Pipeline RR timing |",
             "| --- | ---: | --- | ---: | --- | ---: | --- |"]
    for row in rows:
        gpt, pipeline = row["gpt"], row["pipeline"]
        gpt_rate = f"{gpt['heart_rate_bpm']:.2f}" if gpt.get("heart_rate_bpm") is not None else f"{gpt['status'].replace('_', ' ')}"
        pipeline_rate = f"{pipeline['heart_rate_bpm']:.2f}" if pipeline.get("heart_rate_bpm") is not None else pipeline["status"]
        lines.append(f"| {row['case_id']} | {row['truth']['heart_rate_bpm']:.2f} | {row['truth']['rhythm']} "
                     f"| {gpt_rate} | {gpt.get('rhythm', 'unknown')} | {pipeline_rate} | {pipeline.get('rhythm', 'unknown')} |")
    total, paired = metrics["case_count"], metrics["paired_count"]
    lines.extend(["", f"HR prediction coverage: GPT **{metrics['gpt_hr_coverage']}/{total}**; "
                  f"pipeline **{metrics['pipeline_hr_coverage']}/{total}**.", "",
                  "| Metric | GPT-only | Measured pipeline |",
                  "| --- | ---: | ---: |"])
    if paired:
        lines.append(f"| HR mean absolute error, identical {paired} paired cases | {metrics['gpt_paired_hr_mae_bpm']:.3f} bpm "
                     f"| {metrics['pipeline_paired_hr_mae_bpm']:.3f} bpm |")
    else:
        lines.append("| Paired HR mean absolute error | not available | not available |")
    pipeline_mae = metrics["pipeline_all_hr_mae_bpm"]
    lines.append(f"| Pipeline HR MAE, all available cases | — | {pipeline_mae:.3f} bpm |" if pipeline_mae is not None
                 else "| Pipeline HR MAE, all available cases | — | unavailable |")
    lines.extend([f"| HR estimates within ±3 bpm, out of all {total} cases | {metrics['gpt_hr_within_3_bpm_count']}/{total} "
                  f"| {metrics['pipeline_hr_within_3_bpm_count']}/{total} |",
                  f"| Regular/irregular RR timing accuracy (unknowns count as misses) | {metrics['gpt_rhythm_correct_count']}/{total} "
                  f"({metrics['gpt_rhythm_accuracy_percent']:.1f}%) | {metrics['pipeline_rhythm_correct_count']}/{total} "
                  f"({metrics['pipeline_rhythm_accuracy_percent']:.1f}%) |", ""])
    if metrics["pipeline_beats_gpt_hr_mae"]:
        improvement = 100 * (1 - metrics["pipeline_paired_hr_mae_bpm"] / metrics["gpt_paired_hr_mae_bpm"])
        lines.append(f"**Measured result:** pipeline HR MAE is **{improvement:.1f}% lower** on these {paired} identical paired images.")
    elif paired:
        lines.append("**Measured result:** this run does not demonstrate lower pipeline HR MAE than GPT-only.")
    else:
        lines.append("**Measured result:** GPT comparison was not completed; no claim of superiority can be made.")
    models = sorted({row["gpt"].get("model") for row in rows if row["gpt"].get("model")})
    lines.extend(["", "Reproducibility and limits:", "",
                  f"- Model(s) actually returned: {', '.join(models) if models else 'not run / no valid estimate'}.",
                  "- The original AgentRouter Responses client, headers, key fallback and models are reused.",
                  "  Baseline temperature is omitted because the available models reject temperature overrides.",
                  "  Production JSON explanations retain the requested temperature 0.2 and return null on failure.",
                  "- Successful GPT predictions are checkpointed and reused only for the same image SHA-256 and GPT protocol fingerprint.",
                  "  DSP code has its own fingerprint, so an analytic DSP correction can be measured against unchanged GPT replies.",
                  "  Every case and failure is shown; no selection by error and no rerunning valid predictions to find a better score.",
                  "- Timing labels describe simulator RR variability only, not AFib or any clinical condition.",
                  "  These ten clean rendered strips are a small engineering benchmark; photo accuracy and clinical accuracy are unproven.",
                  "- `comparison.json` includes exact errors / calibration / status, case parameters and image hashes.",
                  "  Test PNGs live in ignored `results/images/` and can be regenerated.",
                  "- Run `python scripts/compare_gpt.py` to use live API calls / checkpoints, or `--offline` for offline pipeline results.",
                  "  No network / LLM is needed by the measured pipeline.", ""])
    initial_path = output_dir / "comparison-initial.json"
    if initial_path.exists():
        initial = json.loads(initial_path.read_text(encoding="utf-8"))
        initial_metrics = initial["metrics"]
        summary["initial_run_metrics"] = initial_metrics
        summary["revision_note"] = "After the first run, corrected finite-overlap autocorrelation bias and used the horizontal grid for time calibration; same cached GPT replies, no new cases or training."
        lines.extend(["Initial run and analytic correction:", "",
                      f"- First run: GPT HR MAE **{initial_metrics['gpt_paired_hr_mae_bpm']:.3f} bpm**, "
                      f"pipeline **{initial_metrics['pipeline_paired_hr_mae_bpm']:.3f} bpm**; GPT had lower error.",
                      "- The initial result is preserved in [comparison-initial.md](comparison-initial.md) and its JSON.",
                      "- A consistent calibration bias led to an analytic correction: normalize autocorrelation by",
                      "  overlapping sample count and derive time calibration from the horizontal grid rather than",
                      "  averaging it with the shorter vertical projection. No learned parameters or patient training.",
                      "- Revised pipeline results reuse the original GPT predictions for byte-identical PNGs.",
                      "  This is post-correction engineering validation on the same cases, not a held-out clinical study.", ""])
    failed = [row for row in rows if row["gpt"].get("error")]
    if failed:
        lines.extend(["Provider / skip notes:", ""])
        for row in failed:
            lines.append(f"- {row['case_id']}: {row['gpt']['error']}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    (output_dir / "comparison.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def run_comparison(output_dir: Path = cfg.RESULTS_DIR, *, offline: bool = False,
                   max_seconds: float = cfg.COMPARISON_MAX_SECONDS, gpt_requester=None) -> dict:
    requester = estimate_gpt if gpt_requester is None else gpt_requester
    fingerprint = code_fingerprint()
    cache = {}
    cache_file = output_dir / "comparison.json"
    if cache_file.exists():
        try:
            previous = json.loads(cache_file.read_text(encoding="utf-8"))
            if (previous.get("code_fingerprint") == fingerprint
                    or previous.get("gpt_protocol_fingerprint") == gpt_protocol_fingerprint()):
                cache = {row["case_id"]: row for row in previous.get("cases", [])}
        except (OSError, ValueError):
            pass
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    started = time.monotonic()
    failures = 0
    for number, specification in enumerate(cfg.COMPARISON_CASES):
        parameters = {key: value for key, value in specification.items() if key != "id"}
        seed = cfg.COMPARISON_SEED + number
        generated = generate_ecg(**parameters, duration=cfg.COMPARISON_DURATION_SECONDS, seed=seed)
        image = render_ecg_image(generated.signal)
        image_hash = hashlib.sha256(image).hexdigest()
        (image_dir / f"{specification['id']}.png").write_bytes(image)
        try:
            recovered = digitize(image)
            measured = analyze_signal(recovered.signal, explain=False, include_plots=False)
            valid = measured["status"] == "ok"
            cv = measured["measurements"].get("rr_cv")
            pipeline = {"status": measured["status"],
                        "heart_rate_bpm": measured["measurements"]["hr_mean_bpm"] if valid else None,
                        "rhythm": ("irregular" if cv > cfg.IRREGULAR_RR_CV else "regular") if valid and cv is not None else "unknown",
                        "rr_cv": cv, "quality": measured["quality"], "calibration": recovered.calibration}
        except ValueError as error:
            pipeline = {"status": "failed", "heart_rate_bpm": None, "rhythm": "unknown", "error": str(error)}
        cached = cache.get(specification["id"])
        if cached and cached.get("image_sha256") == image_hash and cached["gpt"]["status"] in ("ok", "no_estimate"):
            gpt = {**cached["gpt"], "cached": True}
        elif offline or failures >= cfg.COMPARISON_MAX_CONSECUTIVE_FAILURES or time.monotonic() - started > max_seconds - cfg.COMPARISON_TIMEOUT_SECONDS:
            reason = "API not run (--offline)." if offline else "API calls stopped after consecutive failures or time budget; no result fabricated."
            gpt = {"status": "not_run", "heart_rate_bpm": None, "rhythm": "unknown", "error": reason}
        else:
            print(f"[{number + 1}/{len(cfg.COMPARISON_CASES)}] Requesting GPT image-only estimate for {specification['id']}...", flush=True)
            gpt = requester(image)
            failures = failures + 1 if gpt["status"] == "failed" else 0
            time.sleep(cfg.COMPARISON_PAUSE_SECONDS)
        truth = {"heart_rate_bpm": generated.true_hr, "rhythm": generated.rhythm,
                 "beat_count": int(generated.r_peaks.size)}
        row = {"case_id": specification["id"], "parameters": {**parameters, "seed": seed},
               "image_sha256": image_hash, "truth": truth, "gpt": gpt, "pipeline": pipeline}
        row["pipeline_absolute_hr_error"] = abs(pipeline["heart_rate_bpm"] - truth["heart_rate_bpm"]) if pipeline["heart_rate_bpm"] is not None else None
        row["gpt_absolute_hr_error"] = abs(gpt["heart_rate_bpm"] - truth["heart_rate_bpm"]) if gpt.get("heart_rate_bpm") is not None else None
        rows.append(row)
        summary = write_report(rows, output_dir, fingerprint)
        print(f"  truth {truth['heart_rate_bpm']:.2f} | GPT {gpt.get('heart_rate_bpm')} ({gpt['status']}) "
              f"| pipeline {pipeline.get('heart_rate_bpm')} ({pipeline['status']})", flush=True)
    return summary


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", "--skip-gpt", action="store_true", help="Use cached GPT results or mark not run; pipeline still runs.")
    parser.add_argument("--output-dir", type=Path, default=cfg.RESULTS_DIR)
    parser.add_argument("--max-seconds", type=float, default=cfg.COMPARISON_MAX_SECONDS)
    args = parser.parse_args()
    summary = run_comparison(args.output_dir, offline=args.offline, max_seconds=args.max_seconds)
    print("\n" + json.dumps(summary["metrics"], indent=2))
