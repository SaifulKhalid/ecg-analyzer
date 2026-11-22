# Automatic report-region validation

Final robustness/QA supplement:
- All 13 specified adverse image/format cases return structured responses with
  plain Notes; eight ECG format/rotation/compression/resolution cases also meet
  the <=3 bpm check. Tests additionally verify EXIF, white alpha flattening,
  manual precedence, cap-8 ranking, touching lead separation, leading pulse
  trimming and full-page overlay bounds.
- A real public non-ECG landscape photo from https://picsum.photos/id/29/800/600
  returns no_ecg_detected. An initial Wikimedia download was rate-limited (429);
  the alternative source succeeded. The photo is a local ignored QA asset.
- Browser QA at 1280/390 passes on full reports with no crop. A 17.9 MB original
  resizes to a 1.05 MB JPEG upload with unchanged filename and the single resize
  Note. Manual crop, short-region table/notice and blank-image flows pass.
- Automatic regions under five seconds have null HR/RR summary values. Event
  counts, timing lists and figures remain available with the quality notice.
- No new dependencies, provider calls during selection, deployments, or changes
  to the nine frozen modules. Full suite results are in PROGRESS.md.

Reproduce region validation with python scripts/validate_layout.py and robustness
with python -m pytest -q tests/test_layout.py. All declared cases follow below.

Generated: 2026-11-22T21:59:23.087495+00:00.

Long-strip acceptance: **27/27 (100.0%)**; required >=90% with HR error <=3 bpm.
Short/uncalibrated layout handling: **5/5** with an input-dependent quality Note.
Frozen fingerprint unchanged: **True**, `df4b1c6ac4feb0db7dbb91fa6a4f32ef779da9f2f91aba53fab7a0f7b75b5925`.

All declared variants are included, including failures. These are engineering fixtures, not clinical accuracy evidence.

| Case | Layout/grid | Status | Kind | Truth bpm | Measured bpm | Error bpm | Accepted |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| report_01 | 3x4/pink | ok | long strip | 48.00 | 47.989 | 0.011 | PASS |
| report_02 | 3x4/red | ok | long strip | 60.00 | 60.0 | 0.0 | PASS |
| report_03 | 3x4/green | ok | long strip | 71.99 | 72.012 | 0.018 | PASS |
| report_04 | 3x4/blue | ok | long strip | 85.01 | 84.986 | 0.02 | PASS |
| report_05 | 3x4/pink | ok | long strip | 105.01 | 104.987 | 0.023 | PASS |
| report_06 | 3x4/red | ok | long strip | 120.00 | 120.0 | 0.0 | PASS |
| report_07 | 3x4/green | ok | long strip | 48.00 | 48.011 | 0.011 | PASS |
| report_08 | 3x4/blue | ok | long strip | 60.00 | 60.0 | 0.0 | PASS |
| report_09 | 3x4/pink | ok | long strip | 71.99 | 72.012 | 0.018 | PASS |
| report_10 | 3x4/red | ok | long strip | 85.01 | 84.986 | 0.02 | PASS |
| report_11 | 3x4/green | ok | long strip | 105.01 | 104.987 | 0.023 | PASS |
| report_12 | 3x4/blue | ok | long strip | 120.00 | 119.628 | 0.372 | PASS |
| report_13 | 3x4/pink | ok | long strip | 48.00 | 47.989 | 0.011 | PASS |
| report_14 | 3x4/red | ok | long strip | 60.00 | 60.0 | 0.0 | PASS |
| report_15 | 3x4/green | ok | long strip | 71.99 | 72.012 | 0.018 | PASS |
| report_16 | 3x4/blue | ok | long strip | 85.01 | 84.986 | 0.02 | PASS |
| report_17 | 3x4/pink | ok | long strip | 105.01 | 104.987 | 0.023 | PASS |
| report_18 | 3x4/red | ok | long strip | 120.00 | 120.0 | 0.0 | PASS |
| report_19 | 3x4/green | ok | long strip | 48.00 | 48.011 | 0.011 | PASS |
| report_20 | 3x4/blue | ok | long strip | 60.00 | 60.0 | 0.0 | PASS |
| report_21 | 3x4/pink | ok | long strip | 71.99 | 72.012 | 0.018 | PASS |
| report_22 | 3x4/red | ok | long strip | 85.01 | 84.946 | 0.06 | PASS |
| report_23 | 3x4/green | ok | long strip | 105.01 | 104.987 | 0.023 | PASS |
| report_24 | 3x4/blue | ok | long strip | 120.00 | 120.0 | 0.0 | PASS |
| report_25 | 3x4/pink | insufficient_quality | segment | 71.99 | None | n/a | PASS |
| report_26 | 3x4/blue | insufficient_quality | segment | 71.99 | None | n/a | PASS |
| report_27 | 3x4/green | insufficient_quality | segment | 71.99 | None | n/a | PASS |
| report_28 | 3x4/red | insufficient_quality | segment | 71.99 | None | n/a | PASS |
| report_29 | 12x1/pink | ok | long strip | 71.99 | 71.977 | 0.017 | PASS |
| report_30 | 3-channel/pink | ok | long strip | 71.99 | 71.977 | 0.017 | PASS |
| report_31 | 3x4/None | ok | long strip | 71.99 | 72.464 | 0.47 | PASS |
| report_32 | 3x4/None | insufficient_quality | segment | 71.99 | None | n/a | PASS |

## Selection and safety

Dark mostly neutral ink components form horizontal bands. Separate lead cells are never stitched. Each of at most eight proposals uses the unchanged digitizer and measurement/quality pipeline. Passing proposals prefer long strips, then SNR, beats and bottom-most position. With no passing proposal, retain the available long strip/row with most beats; short cells carry a quality notice. Manual crops bypass automatic selection and orientation. Time-only fallback requires a strip spanning the page width; amplitude range/gain are unavailable and figure axes use arbitrary units.

32 fixtures cover 3x4 with/without rhythm strips, 12x1, three channels, four grid colors, grayscale/no grid, 90/180/270 rotation, 3-degree skew, JPEG q60, 4 px/mm and photo-like illumination/noise. Exact parameters, candidate ranks, Notes and operations are in layout-validation.json.

## Supplied images

samples/reports/ is absent; no supplied report directory was available.
sample_ECG_image.png is absent from this checkout; no analysis or reference accuracy claim.
ECG .png is absent from this checkout; no analysis or reference accuracy claim.

## Limits

No perspective correction or OCR of speed/gain/lead names. Severe glare, missing ink, overlapping traces, unusual layouts and nonuniform scaling can defeat selection. A chosen lead is selected for measurement quality, not clinical relevance. A no-grid 10-second width is an explicit assumption and can be wrong for another duration. Short cells and unknown time scales remain qualified or unmeasured.
