# MIT-BIH detector validation

Educational screening tool, not a medical device.

Generated: 2026-11-22T08:50:29.904686+00:00

First 60 s, lead 0, original expert beat annotations; processing at 250 Hz.
One-to-one matching within ±150 ms; non-beat annotation symbols excluded.

| Record | Lead | Reference | Detected | TP | FP | FN | Sensitivity | PPV | Timing MAE |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | MLII | 74 | 74 | 74 | 0 | 0 | 100.00% | 100.00% | 1.05 ms |
| 101 | MLII | 71 | 71 | 71 | 0 | 0 | 100.00% | 100.00% | 1.57 ms |
| 106 | MLII | 67 | 67 | 67 | 0 | 0 | 100.00% | 100.00% | 1.36 ms |
| 119 | MLII | 65 | 65 | 65 | 0 | 0 | 100.00% | 100.00% | 2.80 ms |
| 201 | MLII | 90 | 89 | 89 | 0 | 1 | 98.89% | 100.00% | 1.88 ms |
| **Macro mean (5/5)** | | | | | | | **99.78%** | **100.00%** | |

**Gate: PASS** — record 100 needs ≥99% sensitivity / PPV; both macro means need ≥95%, with all five records available.

No dataset training or library peak detector. These five minutes are a small
engineering validation set, not a held-out clinical study. A passed detector
gate does not validate image digitization, AFib screening, or clinical use.

See `validation.json` for unmatched event times and reproducible counts.
