"""Validate all declared report variants and any supplied local report images."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecg.imageprep import prepare_image
from ecg.layout import select_region
from scripts.compare_holdout import measurement_fingerprint
from tests.report_synth import render_report, variants

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = "df4b1c6ac4feb0db7dbb91fa6a4f32ef779da9f2f91aba53fab7a0f7b75b5925"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def measure(image, *, name, truth=None, expect_long=False, expect_bottom=False, visual_dir=None):
    started = time.monotonic()
    prepared = prepare_image(image)
    chosen = select_region(prepared.image)
    result = chosen.result
    heart_rate = result["measurements"]["hr_mean_bpm"]
    box = chosen.candidate.box if chosen.candidate else None
    kind = chosen.candidate.kind if chosen.candidate else None
    region_ok = bool(box and kind == "long strip")
    if expect_bottom and box:
        region_ok &= box[1] > prepared.image.shape[0]*0.65
    error = abs(heart_rate-truth) if heart_rate is not None and truth is not None else None
    notes = list(dict.fromkeys([*result.get("notes", []), *chosen.notes, *result["quality"]["reasons"]]))
    if chosen.candidate:
        notes.insert(0, f"Region selected automatically: {kind}.")
    if expect_long:
        accepted = result["status"] == "ok" and region_ok and error is not None and error <= 3
    elif truth is not None:
        accepted = result["status"] in ("insufficient_quality", "no_ecg_detected") and any(
            phrase in note for note in notes for phrase in ("too short", "Time scale could not", "No ECG", "resolution"))
    else:
        accepted = result["status"] in ("ok", "insufficient_quality", "no_ecg_detected")
    if visual_dir is not None:
        preview = prepared.image.copy()
        if box:
            cv2.rectangle(preview, (box[0], box[1]), (box[2]-1, box[3]-1), (31, 58, 95), 2)
        visual_dir.mkdir(parents=True, exist_ok=True)
        suffix = hashlib.sha256(image).hexdigest()[:8]
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", Path(name).stem)
        cv2.imwrite(str(visual_dir/f"{safe}-{suffix}.png"), cv2.cvtColor(preview, cv2.COLOR_RGB2BGR))
    return {"name": name, "status": result["status"], "kind": kind, "box": box,
            "image_size": [prepared.image.shape[1], prepared.image.shape[0]],
            "beats": result["quality"]["beat_count"], "snr_db": result["quality"]["snr_db"],
            "hr_bpm": heart_rate, "truth_bpm": truth, "error_bpm": error,
            "expect_long": expect_long, "region_correct": region_ok, "accepted": bool(accepted),
            "notes": notes, "operations": prepared.operations, "candidates": chosen.candidates,
            "elapsed_seconds": round(time.monotonic()-started, 2)}


def run(output=ROOT/"results", limit=None):
    assert measurement_fingerprint() == EXPECTED, "Frozen measurement fingerprint differs."
    rows = []
    cases = variants()
    if limit:
        cases = cases[:limit]
    for index, parameters in enumerate(cases):
        fixture = render_report(**parameters)
        long = parameters.get("rhythm", True) or parameters.get("layout", "3x4") != "3x4"
        row = measure(fixture.image, name=f"report_{index+1:02d}", truth=fixture.hr,
                      expect_long=long, expect_bottom=parameters.get("rhythm", True))
        row["parameters"] = fixture.parameters
        rows.append(row)
        print(f"[{index+1}/{len(cases)}] {row['name']} {row['status']} {row['kind']} HR={row['hr_bpm']} error={row['error_bpm']} accepted={row['accepted']}", flush=True)
    local = []
    directory = ROOT/"samples"/"reports"
    paths = sorted(path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES) if directory.exists() else []
    missing = []
    for name in ("sample_ECG_image.png", "ECG .png"):
        path = ROOT/name
        if path.exists():
            paths.append(path)
        else:
            missing.append(name)
    for path in paths:
        try:
            row = measure(path.read_bytes(), name=str(path.relative_to(ROOT)), visual_dir=output/"layout-visual")
        except (ValueError, OSError, cv2.error) as error:
            row = {"name": str(path.relative_to(ROOT)), "status": "unsupported_image", "accepted": True,
                   "notes": ["Image could not be decoded for measurement."], "kind": None, "hr_bpm": None, "box": None}
        local.append(row)
        print(f"Local {row['name']}: {row['status']} {row['kind']} HR={row['hr_bpm']}", flush=True)
    long_rows = [row for row in rows if row["expect_long"]]
    long_pass = sum(row["accepted"] for row in long_rows)
    short_rows = [row for row in rows if not row["expect_long"]]
    short_pass = sum(row["accepted"] for row in short_rows)
    unchanged = measurement_fingerprint() == EXPECTED
    summary = {"generated_utc": datetime.now(timezone.utc).isoformat(), "fingerprint": EXPECTED,
               "fingerprint_unchanged": unchanged, "variant_count": len(rows), "long_pass": long_pass,
               "long_total": len(long_rows), "long_pass_fraction": long_pass/max(1,len(long_rows)),
               "short_pass": short_pass, "short_total": len(short_rows), "cases": rows, "local": local,
               "missing_inputs": missing, "samples_reports_exists": directory.exists()}
    output.mkdir(parents=True, exist_ok=True)
    (output/"layout-validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = ["# Automatic report-region validation", "", f"Generated: {summary['generated_utc']}.", "",
             f"Long-strip acceptance: **{long_pass}/{len(long_rows)} ({100*summary['long_pass_fraction']:.1f}%)**; required >=90% with HR error <=3 bpm.",
             f"Short/uncalibrated layout handling: **{short_pass}/{len(short_rows)}** with an input-dependent quality Note.",
             f"Frozen fingerprint unchanged: **{unchanged}**, `{EXPECTED}`.", "",
             "All declared variants are included, including failures. These are engineering fixtures, not clinical accuracy evidence.", "",
             "| Case | Layout/grid | Status | Kind | Truth bpm | Measured bpm | Error bpm | Accepted |",
             "| --- | --- | --- | --- | ---: | ---: | ---: | --- |"]
    for row in rows:
        p = row["parameters"]
        lines.append(f"| {row['name']} | {p['layout']}/{p['grid']} | {row['status']} | {row['kind']} | {row['truth_bpm']:.2f} | {row['hr_bpm']} | {round(row['error_bpm'],3) if row['error_bpm'] is not None else 'n/a'} | {'PASS' if row['accepted'] else 'FAIL'} |")
    lines.extend(["", "## Selection and safety", "", "Dark mostly neutral ink components form horizontal bands. Separate lead cells are never stitched. Each of at most eight proposals uses the unchanged digitizer and measurement/quality pipeline. Passing proposals prefer long strips, then SNR, beats and bottom-most position. With no passing proposal, retain the available long strip/row with most beats; short cells carry a quality notice. Manual crops bypass automatic selection and orientation. Time-only fallback requires a strip spanning the page width; amplitude range/gain are unavailable and figure axes use arbitrary units.", "",
                  "32 fixtures cover 3x4 with/without rhythm strips, 12x1, three channels, four grid colors, grayscale/no grid, 90/180/270 rotation, 3-degree skew, JPEG q60, 4 px/mm and photo-like illumination/noise. Exact parameters, candidate ranks, Notes and operations are in layout-validation.json.", "", "## Supplied images", ""])
    if not directory.exists():
        lines.append("samples/reports/ is absent; no supplied report directory was available.")
    for name in missing:
        lines.append(f"{name} is absent from this checkout; no analysis or reference accuracy claim.")
    for row in local:
        lines.append(f"- {row['name']}: {row['status']}; {row['kind']}; HR {row['hr_bpm']}; box {row['box']}. Notes: {'; '.join(row['notes'])}")
    if local:
        lines.append("Outlined prepared-page previews are saved under results/layout-visual/. Source images are never modified.")
    lines.extend(["", "## Limits", "", "No perspective correction or OCR of speed/gain/lead names. Severe glare, missing ink, overlapping traces, unusual layouts and nonuniform scaling can defeat selection. A chosen lead is selected for measurement quality, not clinical relevance. A no-grid 10-second width is an explicit assumption and can be wrong for another duration. Short cells and unknown time scales remain qualified or unmeasured."])
    (output/"layout-validation.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    assert unchanged, "Frozen fingerprint changed during validation."
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"results")
    parser.add_argument("--limit", type=int, help="Development subset; omit for final acceptance.")
    args = parser.parse_args()
    summary = run(args.output, args.limit)
    print(json.dumps({key: summary[key] for key in ("variant_count", "long_pass", "long_total", "short_pass", "short_total", "fingerprint_unchanged")}, indent=2))
    if not args.limit and (summary["long_pass_fraction"] < 0.9 or summary["short_pass"] != summary["short_total"]):
        raise SystemExit(1)
