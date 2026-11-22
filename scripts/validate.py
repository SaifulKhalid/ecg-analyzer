"""MIT-BIH lead-0 first-minute validation; expert annotations are reference.

Run from any directory: python scripts/validate.py. Download once separately
with scripts/download_data.py. Missing data are errors, never synthetic MIT-BIH.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecg import config as cfg
from ecg.peaks import detect_r_peaks
from ecg.preprocess import preprocess


def match_beats(reference_seconds: np.ndarray, detected_seconds: np.ndarray,
                tolerance: float = cfg.MATCH_TOLERANCE_SECONDS) -> dict:
    """Sorted one-to-one matching, maximizing matches within the tolerance.

    Two pointers pair the earliest eligible events. Each reference / detection
    is consumed at most once, so duplicate peaks count as false positives.
    """
    reference = np.sort(np.asarray(reference_seconds, dtype=float))
    detected = np.sort(np.asarray(detected_seconds, dtype=float))
    ref_index = det_index = 0
    errors = []
    matched_reference = set()
    matched_detected = set()
    while ref_index < reference.size and det_index < detected.size:
        difference = detected[det_index] - reference[ref_index]
        if abs(difference) <= tolerance:
            errors.append(float(difference * 1000))
            matched_reference.add(ref_index)
            matched_detected.add(det_index)
            ref_index += 1
            det_index += 1
        elif difference < -tolerance:
            det_index += 1
        else:
            ref_index += 1
    tp = len(errors)
    fp, fn = int(detected.size) - tp, int(reference.size) - tp
    return {"tp": tp, "fp": fp, "fn": fn,
            "reference_beats": int(reference.size), "detected_beats": int(detected.size),
            "sensitivity": 100 * tp / (tp + fn) if tp + fn else 0.0,
            "ppv": 100 * tp / (tp + fp) if tp + fp else 0.0,
            "timing_mae_ms": float(np.mean(np.abs(errors))) if errors else None,
            "missed_times_s": [float(t) for i, t in enumerate(reference) if i not in matched_reference],
            "extra_times_s": [float(t) for i, t in enumerate(detected) if i not in matched_detected]}


def validate_record(record_id: str, data_dir: Path = cfg.DATA_DIR) -> dict:
    import wfdb

    record_path = str(data_dir / record_id)
    header = wfdb.rdheader(record_path)
    count = min(int(round(cfg.VALIDATION_SECONDS * header.fs)), header.sig_len)
    record = wfdb.rdrecord(record_path, sampto=count, channels=[0])
    annotations = wfdb.rdann(record_path, "atr", sampto=count)
    reference = np.asarray([sample for sample, symbol in zip(annotations.sample, annotations.symbol)
                            if symbol in cfg.BEAT_ANNOTATIONS and sample < count]) / record.fs
    processed = preprocess(record.p_signal[:, 0], record.fs)
    peaks = detect_r_peaks(processed.filtered, processed.fs)
    result = match_beats(reference, peaks / processed.fs)
    return {"record": record_id, "lead": record.sig_name[0], "source_fs": record.fs,
            "seconds": count / record.fs, "status": "ok", **result}


def run_validation(data_dir: Path = cfg.DATA_DIR, output_dir: Path = cfg.RESULTS_DIR) -> dict:
    rows = []
    for record in cfg.VALIDATION_RECORDS:
        try:
            rows.append(validate_record(record, data_dir))
        except (OSError, ValueError) as error:
            rows.append({"record": record, "status": "unavailable", "error": str(error)})
    available = [row for row in rows if row["status"] == "ok"]
    mean_sensitivity = float(np.mean([row["sensitivity"] for row in available])) if available else 0.0
    mean_ppv = float(np.mean([row["ppv"] for row in available])) if available else 0.0
    row_100 = next((row for row in available if row["record"] == "100"), None)
    passed = (len(available) == len(cfg.VALIDATION_RECORDS) and row_100 is not None
              and row_100["sensitivity"] >= cfg.GATE_RECORD_100_PERCENT
              and row_100["ppv"] >= cfg.GATE_RECORD_100_PERCENT
              and mean_sensitivity >= cfg.GATE_MEAN_PERCENT and mean_ppv >= cfg.GATE_MEAN_PERCENT)
    summary = {"generated_utc": datetime.now(timezone.utc).isoformat(),
               "source": "MIT-BIH Arrhythmia Database 1.0.0, expert atr beat annotations",
               "records": rows, "mean_sensitivity": mean_sensitivity, "mean_ppv": mean_ppv,
               "gate_passed": bool(passed), "match_tolerance_ms": cfg.MATCH_TOLERANCE_SECONDS * 1000,
               "processing_fs": cfg.FS_TARGET, "training": "none"}
    lines = ["# MIT-BIH detector validation", "", cfg.DISCLAIMER, "",
             f"Generated: {summary['generated_utc']}", "",
             "First 60 s, lead 0, original expert beat annotations; processing at 250 Hz.",
             "One-to-one matching within ±150 ms; non-beat annotation symbols excluded.", "",
             "| Record | Lead | Reference | Detected | TP | FP | FN | Sensitivity | PPV | Timing MAE |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in rows:
        if row["status"] != "ok":
            lines.append(f"| {row['record']} | unavailable | — | — | — | — | — | — | — | — |")
            continue
        lines.append(f"| {row['record']} | {row['lead']} | {row['reference_beats']} | {row['detected_beats']} "
                     f"| {row['tp']} | {row['fp']} | {row['fn']} | {row['sensitivity']:.2f}% "
                     f"| {row['ppv']:.2f}% | {row['timing_mae_ms']:.2f} ms |")
    lines.extend([f"| **Macro mean ({len(available)}/5)** | | | | | | | **{mean_sensitivity:.2f}%** "
                  f"| **{mean_ppv:.2f}%** | |", "",
                  f"**Gate: {'PASS' if passed else 'FAIL'}** — record 100 needs ≥99% sensitivity / PPV; "
                  "both macro means need ≥95%, with all five records available.", "",
                  "No dataset training or library peak detector. These five minutes are a small",
                  "engineering validation set, not a held-out clinical study. A passed detector",
                  "gate does not validate image digitization, AFib screening, or clinical use.", "",
                  "See `validation.json` for unmatched event times and reproducible counts.", ""])
    for row in rows:
        if row["status"] != "ok":
            lines.append(f"Unavailable {row['record']}: {row['error']}")
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown = "\n".join(lines)
    (output_dir / "validation.md").write_text(markdown, encoding="utf-8")
    (output_dir / "validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(markdown)
    return summary


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=cfg.DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=cfg.RESULTS_DIR)
    args = parser.parse_args()
    sys.exit(0 if run_validation(args.data_dir, args.output_dir)["gate_passed"] else 1)
