# Whole-record MIT-BIH detector validation

Educational screening tool, not a medical device.

Generated: 2026-11-22T14:10:17.130550+00:00

Command: `python scripts/validate_long.py` after preparing and committing `--prepare`.
Complete cached recordings, lead 0; one-to-one matching to expert beat annotations within ±150 ms.
290 s central windows with 5 s context on each side (at most 300 s per DSP input).
Only detections inside each half-open central interval count; no seam deduplication or beat exclusions.

| Record | Minutes | Reference | Detected | TP | FP | FN | Sensitivity | PPV | Timing MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 30.09 | 2273 | 2273 | 2273 | 0 | 0 | 100.00% | 100.00% | 1.22 ms |
| 101 | 30.09 | 1865 | 1868 | 1864 | 4 | 1 | 99.95% | 99.79% | 2.02 ms |
| 106 | 30.09 | 2027 | 2023 | 2022 | 1 | 5 | 99.75% | 99.95% | 3.98 ms |
| 119 | 30.09 | 1987 | 1988 | 1987 | 1 | 0 | 100.00% | 99.95% | 2.08 ms |
| 201 | 30.09 | 1963 | 1917 | 1917 | 0 | 46 | 97.66% | 100.00% | 4.84 ms |

Coverage: **5/5 recordings / 150.46 minutes**.
Macro sensitivity **99.47%**, PPV **99.94%**.
Pooled sensitivity **99.49%**, PPV **99.94%**.
Pooled counts: 10063 TP, 6 FP, 52 FN.

The protocol and measurement code were frozen before this extended run. No post-result tuning.
The requested first-minute gate remains separate in [validation.md](validation.md).
This wider check uses the same five previously selected records, not an independent patient holdout.
It validates R-event detection from raw lead-0 signals, not image extraction or disease screening.
Physical recording edges and detector reinitialization may still affect event timing.
Unmatched event times, per-window counts, file hashes and protocol are in [long-validation.json](long-validation.json).
Protocol: [long-validation-protocol.json](long-validation-protocol.json).
