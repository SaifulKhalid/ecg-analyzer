"""Whole-record MIT-BIH validation of frozen DSP, with context at window seams.

Prepare and commit the protocol before evaluating: --prepare. Results are
separate from the required first-minute gate; no detector tuning is permitted.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecg import config as cfg
from ecg.peaks import detect_r_peaks
from ecg.preprocess import preprocess
from scripts.compare_holdout import MEASUREMENT_FILES, measurement_fingerprint
from scripts.validate import match_beats


def signal_windows(count: int, fs: float, central_seconds: float,
                   context_seconds: float) -> list[dict]:
    """Partition every source sample once; context is processed but not counted.

    Central intervals are half-open. A beat exactly at a seam belongs to the
    next window. Context avoids artificial filter edges at internal seams;
    physical recording endpoints still have the existing filter limitations.
    """
    if not np.isfinite(fs) or fs <= 0 or count / fs < cfg.MIN_SIGNAL_SECONDS:
        raise ValueError("A finite sampling rate and at least two seconds are required.")
    if (not np.isfinite(central_seconds) or not np.isfinite(context_seconds)
            or central_seconds < cfg.MIN_SIGNAL_SECONDS or context_seconds < 0
            or central_seconds + 2 * context_seconds > cfg.MAX_SIGNAL_SECONDS):
        raise ValueError("Central interval plus both contexts must fit the signal duration limit.")
    central_count = int(round(central_seconds * fs))
    context_count = int(round(context_seconds * fs))
    minimum_count = int(np.ceil(cfg.MIN_SIGNAL_SECONDS * fs))
    windows = []
    for central_start in range(0, count, central_count):
        central_stop = min(count, central_start + central_count)
        start = max(0, central_start - context_count)
        stop = min(count, central_stop + context_count)
        if stop - start < minimum_count:
            start = max(0, stop - minimum_count)
        if (stop - start) / fs > cfg.MAX_SIGNAL_SECONDS:
            raise ValueError("Rounded window exceeds the configured duration limit.")
        windows.append({"start": start, "stop": stop,
                        "central_start": central_start, "central_stop": central_stop})
    return windows


def detect_windowed(samples: np.ndarray, fs: float, central_seconds: float,
                    context_seconds: float) -> tuple[np.ndarray, list[dict]]:
    """Run the unchanged filters/detector and map kept events to recording time."""
    windows = signal_windows(len(samples), fs, central_seconds, context_seconds)
    events = []
    details = []
    for window in windows:
        processed = preprocess(samples[window["start"]:window["stop"]], fs)
        peaks = detect_r_peaks(processed.filtered, processed.fs)
        # Compare in source-sample coordinates to preserve ownership at seams.
        positions = window["start"] + peaks.astype(float) * fs / processed.fs
        kept = positions[(positions >= window["central_start"])
                         & (positions < window["central_stop"])] / fs
        events.extend(kept.tolist())
        details.append({"processing_start_s": window["start"] / fs,
                        "processing_stop_s": window["stop"] / fs,
                        "central_start_s": window["central_start"] / fs,
                        "central_stop_s": window["central_stop"] / fs,
                        "retained_beats": int(kept.size)})
    return np.asarray(events), details


def prepare(data_dir: Path, output_dir: Path) -> dict:
    """Record the complete protocol and local input hashes without reading beats."""
    import wfdb

    path = output_dir / "long-validation-protocol.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    records = []
    for record_id in cfg.VALIDATION_RECORDS:
        header = wfdb.rdheader(str(data_dir / record_id))
        hashes = {extension: hashlib.sha256((data_dir / f"{record_id}.{extension}").read_bytes()).hexdigest()
                  for extension in ("hea", "dat", "atr")}
        records.append({"record": record_id, "source_fs": header.fs,
                        "samples": header.sig_len, "seconds": header.sig_len / header.fs,
                        "file_sha256": hashes})
    context_seconds = 5.0
    protocol = {"prepared_utc": datetime.now(timezone.utc).isoformat(),
                "prepared_git_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=cfg.ROOT, text=True).strip(),
                "measurement_fingerprint": measurement_fingerprint(),
                "measurement_files": list(MEASUREMENT_FILES), "lead_index": 0,
                "scope": "Complete cached recordings; no selected intervals or excluded beats.",
                "central_seconds": cfg.MAX_SIGNAL_SECONDS - 2 * context_seconds,
                "context_seconds": context_seconds,
                "match_tolerance_seconds": cfg.MATCH_TOLERANCE_SECONDS,
                "beat_symbols": sorted(cfg.BEAT_ANNOTATIONS),
                "records": records, "training": "none", "post_result_tuning": "none"}
    output_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    return protocol


def run(data_dir: Path, output_dir: Path) -> dict:
    import wfdb

    path = output_dir / "long-validation-protocol.json"
    if not path.exists():
        raise ValueError("Prepare and commit the protocol with --prepare before evaluating.")
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if measurement_fingerprint() != protocol["measurement_fingerprint"]:
        raise ValueError("Frozen measurement modules changed; this protocol cannot be silently reused.")
    rows = []
    for source in protocol["records"]:
        record_id = source["record"]
        print(f"Validating complete record {record_id}...", flush=True)
        try:
            for extension, expected in source["file_sha256"].items():
                if hashlib.sha256((data_dir / f"{record_id}.{extension}").read_bytes()).hexdigest() != expected:
                    raise ValueError(f"Record {record_id}.{extension} changed from the declared input.")
            record_path = str(data_dir / record_id)
            record = wfdb.rdrecord(record_path, channels=[protocol["lead_index"]])
            if record.fs != source["source_fs"] or len(record.p_signal) != source["samples"]:
                raise ValueError("Record shape changed from the declared protocol.")
            annotations = wfdb.rdann(record_path, "atr")
            reference = np.asarray([sample for sample, symbol in zip(annotations.sample, annotations.symbol)
                                    if symbol in protocol["beat_symbols"] and sample < source["samples"]]) / record.fs
            detected, windows = detect_windowed(record.p_signal[:, 0], record.fs,
                                                protocol["central_seconds"], protocol["context_seconds"])
            rows.append({"record": record_id, "lead": record.sig_name[0],
                         "source_fs": record.fs, "seconds": source["seconds"], "status": "ok",
                         "windows": windows, **match_beats(reference, detected, protocol["match_tolerance_seconds"])})
        except (OSError, ValueError) as error:
            rows.append({"record": record_id, "status": "unavailable", "error": str(error)})
    if measurement_fingerprint() != protocol["measurement_fingerprint"]:
        raise ValueError("Measurement code changed during evaluation; results are invalid.")
    available = [row for row in rows if row["status"] == "ok"]
    totals = {key: sum(row[key] for row in available) for key in ("tp", "fp", "fn", "reference_beats", "detected_beats")}
    summary = {"generated_utc": datetime.now(timezone.utc).isoformat(),
               "source": "MIT-BIH Arrhythmia Database 1.0.0, complete lead-0 recordings",
               "protocol_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "protocol": protocol,
               "records": rows, "coverage": f"{len(available)}/{len(rows)}",
               "duration_minutes": sum(row["seconds"] for row in available) / 60,
               "macro_sensitivity": float(np.mean([row["sensitivity"] for row in available])) if available else None,
               "macro_ppv": float(np.mean([row["ppv"] for row in available])) if available else None,
               "pooled_sensitivity": 100 * totals["tp"] / totals["reference_beats"] if totals["reference_beats"] else None,
               "pooled_ppv": 100 * totals["tp"] / totals["detected_beats"] if totals["detected_beats"] else None,
               "totals": totals, "measurement_code_unchanged": True, "training": "none"}
    lines = ["# Whole-record MIT-BIH detector validation", "", cfg.DISCLAIMER, "",
             f"Generated: {summary['generated_utc']}", "",
             "Command: `python scripts/validate_long.py` after preparing and committing `--prepare`.",
             "Complete cached recordings, lead 0; one-to-one matching to expert beat annotations within ±150 ms.",
             "290 s central windows with 5 s context on each side (at most 300 s per DSP input).",
             "Only detections inside each half-open central interval count; no seam deduplication or beat exclusions.", "",
             "| Record | Minutes | Reference | Detected | TP | FP | FN | Sensitivity | PPV | Timing MAE |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in rows:
        if row["status"] == "ok":
            timing = f"{row['timing_mae_ms']:.2f} ms" if row["timing_mae_ms"] is not None else "unavailable"
            lines.append(f"| {row['record']} | {row['seconds'] / 60:.2f} | {row['reference_beats']} | {row['detected_beats']} "
                         f"| {row['tp']} | {row['fp']} | {row['fn']} | {row['sensitivity']:.2f}% | {row['ppv']:.2f}% | {timing} |")
        else:
            lines.append(f"| {row['record']} | unavailable | — | — | — | — | — | — | — | — |")
    if available:
        lines.extend(["", f"Coverage: **{summary['coverage']} recordings / {summary['duration_minutes']:.2f} minutes**.",
                      f"Macro sensitivity **{summary['macro_sensitivity']:.2f}%**, PPV **{summary['macro_ppv']:.2f}%**.",
                      f"Pooled sensitivity **{summary['pooled_sensitivity']:.2f}%**, PPV **{summary['pooled_ppv']:.2f}%**.",
                      f"Pooled counts: {totals['tp']} TP, {totals['fp']} FP, {totals['fn']} FN."])
    lines.extend(["", "The protocol and measurement code were frozen before this extended run. No post-result tuning.",
                  "The requested first-minute gate remains separate in [validation.md](validation.md).",
                  "This wider check uses the same five previously selected records, not an independent patient holdout.",
                  "It validates R-event detection from raw lead-0 signals, not image extraction or disease screening.",
                  "Physical recording edges and detector reinitialization may still affect event timing.",
                  "Unmatched event times, per-window counts, file hashes and protocol are in [long-validation.json](long-validation.json).",
                  "Protocol: [long-validation-protocol.json](long-validation-protocol.json).", ""])
    for row in rows:
        if row["status"] != "ok":
            lines.append(f"Unavailable {row['record']}: {row['error']}")
    markdown = "\n".join(lines)
    (output_dir / "long-validation.md").write_text(markdown, encoding="utf-8")
    (output_dir / "long-validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(markdown)
    return summary


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=cfg.DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=cfg.RESULTS_DIR)
    args = parser.parse_args()
    result = prepare(args.data_dir, args.output_dir) if args.prepare else run(args.data_dir, args.output_dir)
    if args.prepare:
        print(json.dumps(result, indent=2))
    elif len([row for row in result["records"] if row["status"] == "ok"]) != len(result["records"]):
        sys.exit(1)
