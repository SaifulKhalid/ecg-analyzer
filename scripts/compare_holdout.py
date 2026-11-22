"""Fresh synthetic validation with predeclared cases and frozen measurement code.

Prepare and commit the manifest before live calls: --prepare. Every result is
reported, including failed predictions; no threshold / algorithm changes are
permitted during this study. This validates synthetic parameter generalization,
not clinical accuracy.
"""

import argparse
import hashlib
import json
import subprocess
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
from ecg.synth import generate_ecg
from scripts.compare_gpt import estimate_gpt, gpt_protocol_fingerprint, write_report

MEASUREMENT_FILES = ("config", "preprocess", "peaks", "features", "classify", "quality", "digitize", "plots", "synth")
HOLDOUT_SEED = 20261123
DEFAULT_OUTPUT = cfg.RESULTS_DIR / "holdout"


def measurement_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in MEASUREMENT_FILES:
        digest.update(name.encode())
        digest.update((cfg.ROOT / "ecg" / f"{name}.py").read_bytes())
    return digest.hexdigest()


def prepare(output_dir: Path) -> dict:
    path = output_dir / "manifest.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    rng = np.random.default_rng(HOLDOUT_SEED)
    rates = np.round(rng.uniform(45, 130, 10), 2)
    cases = []
    for index, rate in enumerate(rates):
        cases.append({"case_id": f"holdout_{index + 1:02d}", "parameters": {
            "hr": float(rate), "noise": round(float(rng.uniform(0.01, 0.10)), 4),
            "mains_amplitude": round(float(rng.uniform(0.02, 0.20)), 4),
            "baseline_wander": round(float(rng.uniform(0.03, 0.25)), 4),
            "irregular": index in (3, 8), "invert": index in (4, 9),
            "duration": cfg.COMPARISON_DURATION_SECONDS, "seed": HOLDOUT_SEED + index}})
    manifest = {"prepared_utc": datetime.now(timezone.utc).isoformat(), "seed": HOLDOUT_SEED,
                "prepared_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cfg.ROOT, text=True).strip(),
                "measurement_fingerprint": measurement_fingerprint(), "measurement_files": list(MEASUREMENT_FILES),
                "sampling": "HR uniformly drawn from 45–130 bpm; all cases / noise / timing / polarity fixed before GPT requests.",
                "cases": cases, "training": "none"}
    output_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def run(output_dir: Path, *, offline: bool = False, max_seconds: float = 750) -> dict:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("Prepare and commit the manifest with --prepare before live validation.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest["measurement_fingerprint"]
    if measurement_fingerprint() != expected:
        raise ValueError("Frozen measurement modules changed; do not silently reuse this study.")
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    cache = {}
    cached_protocol = None
    checkpoint = output_dir / "comparison.json"
    if checkpoint.exists():
        previous = json.loads(checkpoint.read_text(encoding="utf-8"))
        if previous.get("manifest_sha256") == manifest_hash:
            cache = {row["case_id"]: row for row in previous["cases"]}
            cached_protocol = previous.get("gpt_protocol_fingerprint")
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    started = time.monotonic()
    failures = 0
    for number, case in enumerate(manifest["cases"]):
        generated = generate_ecg(**case["parameters"])
        image = render_ecg_image(generated.signal)
        image_hash = hashlib.sha256(image).hexdigest()
        (image_dir / f"{case['case_id']}.png").write_bytes(image)
        recovered = digitize(image)
        measured = analyze_signal(recovered.signal, explain=False, include_plots=False)
        valid = measured["status"] == "ok"
        cv = measured["measurements"]["rr_cv"]
        pipeline = {"status": measured["status"], "heart_rate_bpm": measured["measurements"]["hr_mean_bpm"] if valid else None,
                    "rhythm": ("irregular" if cv > cfg.IRREGULAR_RR_CV else "regular") if valid and cv is not None else "unknown",
                    "quality": measured["quality"], "calibration": recovered.calibration}
        cached = cache.get(case["case_id"])
        if cached and cached["image_sha256"] == image_hash and cached["gpt"]["status"] in ("ok", "no_estimate"):
            gpt = {**cached["gpt"], "cached": True,
                   "source_protocol_fingerprint": cached["gpt"].get("source_protocol_fingerprint") or cached_protocol or "unknown_legacy"}
        elif offline or failures >= 3 or time.monotonic() - started > max_seconds - cfg.COMPARISON_TIMEOUT_SECONDS:
            gpt = {"status": "not_run", "heart_rate_bpm": None, "rhythm": "unknown",
                   "error": "Not run: offline, consecutive provider failures or study time budget."}
        else:
            print(f"[{number + 1}/10] {case['case_id']}: image-only GPT request", flush=True)
            gpt = estimate_gpt(image)
            failures = failures + 1 if gpt["status"] == "failed" else 0
            time.sleep(cfg.COMPARISON_PAUSE_SECONDS)
        truth = {"heart_rate_bpm": generated.true_hr, "rhythm": generated.rhythm,
                 "beat_count": int(generated.r_peaks.size)}
        row = {**case, "truth": truth, "pipeline": pipeline, "gpt": gpt, "image_sha256": image_hash,
               "pipeline_absolute_hr_error": abs(pipeline["heart_rate_bpm"] - truth["heart_rate_bpm"]) if valid else None,
               "gpt_absolute_hr_error": abs(gpt["heart_rate_bpm"] - truth["heart_rate_bpm"]) if gpt.get("heart_rate_bpm") is not None else None}
        rows.append(row)
        summary = write_report(rows, output_dir, expected)
        summary.update(seed=manifest["seed"], manifest_sha256=manifest_hash,
                       manifest=manifest, measurement_code_unchanged=measurement_fingerprint() == expected,
                       study="Fresh synthetic validation; cases declared and measurement code frozen before GPT predictions.")
        checkpoint.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        markdown_path = output_dir / "comparison.md"
        markdown = markdown_path.read_text(encoding="utf-8").replace(
            "# GPT-only versus measured ECG pipeline", "# Fresh synthetic validation: GPT-only versus frozen DSP")
        markdown += (f"\nStudy protocol: [manifest.json](manifest.json), declared {manifest['prepared_utc']}.\n"
                     f"Measurement modules frozen at SHA-256 `{expected}`; unchanged throughout this run.\n"
                     "HR / noise parameters and new simulator seeds were fixed before model predictions; all ten cases are included.\n"
                     "No post-result DSP changes are permitted. These remain Gaussian-sum synthetic strips, not clinical validation.\n")
        markdown_path.write_text(markdown, encoding="utf-8")
        print(f"  True {truth['heart_rate_bpm']:.2f}; GPT {gpt.get('heart_rate_bpm')}; pipeline {pipeline['heart_rate_bpm']}", flush=True)
    if measurement_fingerprint() != expected:
        raise ValueError("Measurement code changed during the study; invalidate these results.")
    return summary


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-seconds", type=float, default=750)
    args = parser.parse_args()
    result = prepare(args.output_dir) if args.prepare else run(args.output_dir, offline=args.offline, max_seconds=args.max_seconds)
    print(json.dumps(result.get("metrics", result), indent=2))
