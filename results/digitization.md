# Calibrated image round-trip validation

Educational screening tool, not a medical device.

Generated: 2026-11-22T09:41:08.806357+00:00

Command: `python scripts/validate.py --images` (offline; MIT-BIH row included when cached).

| Case | Ground-truth HR | Measured HR | Absolute error | Recovered px/mm | Quality |
| --- | ---: | ---: | ---: | ---: | --- |
| Synthetic 45 bpm / 6 px/mm | 44.99 | 44.99 | 0.000 bpm | 5.999 | ok |
| Synthetic 72 bpm / 6 px/mm | 72.01 | 71.98 | 0.027 bpm | 5.999 | ok |
| Synthetic 130 bpm / 6 px/mm | 130.01 | 130.01 | 0.000 bpm | 6.000 | ok |
| Synthetic 45 bpm / 8 px/mm | 44.99 | 44.99 | 0.000 bpm | 8.000 | ok |
| Synthetic 72 bpm / 8 px/mm | 72.01 | 71.98 | 0.027 bpm | 7.999 | ok |
| Synthetic 130 bpm / 8 px/mm | 130.01 | 129.96 | 0.047 bpm | 8.000 | ok |
| Synthetic 45 bpm / 12 px/mm | 44.99 | 44.99 | 0.000 bpm | 12.000 | ok |
| Synthetic 72 bpm / 12 px/mm | 72.01 | 72.01 | 0.000 bpm | 12.000 | ok |
| Synthetic 130 bpm / 12 px/mm | 130.01 | 130.01 | 0.000 bpm | 12.000 | ok |
| Irregular RR | 75.87 | 75.84 | 0.027 bpm | 7.999 | ok |
| Inverted trace | 75.00 | 74.97 | 0.029 bpm | 7.999 | ok |
| Fractional spacing | 75.00 | 75.09 | 0.087 bpm | 7.509 | ok |
| 50 mm/s / 5 mm/mV overrides | 91.99 | 91.99 | 0.000 bpm | 8.000 | ok |
| MIT-BIH 100 / first 12 s | 73.88 | 73.84 | 0.042 bpm | 7.994 | ok |

**Gate: PASS** — every case needs valid quality and HR error ≤3 bpm.
Mean absolute error: **0.021 bpm**; maximum: **0.087 bpm**.

Ground truth uses simulator R timing or original MIT-BIH beat annotations.
These are clean, aligned, known-calibration rendered strips; they do not establish
accuracy on photographs or twelve-lead layouts. All cases use the same measured pipeline
and no LLM / dataset training. Synthetic noisy cases use seed 7, 0.015 mV white noise,
0.08 mV 50 Hz interference and 0.15 mV baseline drift. Irregularity is timing only.
