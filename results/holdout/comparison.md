# Fresh synthetic validation: GPT-only versus frozen DSP

Educational screening tool, not a medical device.

Generated: 2026-11-22T12:58:23.369144+00:00

Ten fixed 12-second synthetic single-lead images, nominal HR 45–130 bpm,
including two irregular RR patterns and noisy / 50 Hz / baseline-wander cases.
Each method sees the **identical PNG**. Ground-truth HR is **60 / mean simulator RR**;
finite-strip irregular HR can differ from nominal HR. No dataset training.

| Case | True HR | True RR timing | GPT-only HR | GPT RR timing | Pipeline HR | Pipeline RR timing |
| --- | ---: | --- | ---: | --- | ---: | --- |
| holdout_01 | 48.75 | regular | 49.00 | regular | 48.77 | regular |
| holdout_02 | 65.12 | regular | 65.00 | regular | 65.12 | regular |
| holdout_03 | 50.60 | regular | 50.60 | regular | 50.62 | regular |
| holdout_04 | 83.18 | irregular | 83.00 | irregular | 83.18 | irregular |
| holdout_05 | 107.18 | regular | 107.00 | regular | 107.22 | regular |
| holdout_06 | 88.89 | regular | 89.00 | regular | 88.86 | regular |
| holdout_07 | 90.26 | regular | 90.00 | regular | 90.26 | regular |
| holdout_08 | 51.64 | regular | 52.00 | regular | 51.65 | regular |
| holdout_09 | 118.42 | irregular | 118.00 | irregular | 118.38 | irregular |
| holdout_10 | 46.07 | regular | 46.00 | regular | 46.06 | regular |

HR prediction coverage: GPT **10/10**; pipeline **10/10**.

| Metric | GPT-only | Measured pipeline |
| --- | ---: | ---: |
| HR mean absolute error, identical 10 paired cases | 0.194 bpm | 0.016 bpm |
| Pipeline HR MAE, all available cases | — | 0.016 bpm |
| HR estimates within ±3 bpm, out of all 10 cases | 10/10 | 10/10 |
| Regular/irregular RR timing accuracy (unknowns count as misses) | 10/10 (100.0%) | 10/10 (100.0%) |

**Measured result:** pipeline HR MAE is **92.0% lower** on these 10 identical paired images.

Reproducibility and limits:

- Model(s) actually returned: gpt-5.6-sol.
- The original AgentRouter Responses client, headers, key fallback and models are reused.
  Baseline temperature is omitted because the available models reject temperature overrides.
  Production JSON explanations retain the requested temperature 0.2 and return null on failure.
- Successful GPT predictions are checkpointed and reused only for the same image SHA-256 and GPT protocol fingerprint.
  DSP code has its own fingerprint, so an analytic DSP correction can be measured against unchanged GPT replies.
  Every case and failure is shown; no selection by error and no rerunning valid predictions to find a better score.
- Timing labels describe simulator RR variability only, not AFib or any clinical condition.
  These ten clean rendered strips are a small engineering benchmark; photo accuracy and clinical accuracy are unproven.
- `comparison.json` includes exact errors / calibration / status, case parameters and image hashes.
  Test PNGs live in ignored `results/images/` and can be regenerated.
- Run `python scripts/compare_gpt.py` to use live API calls / checkpoints, or `--offline` for offline pipeline results.
  No network / LLM is needed by the measured pipeline.

Study protocol: [manifest.json](manifest.json), declared 2026-11-22T12:56:33.259894+00:00.
Measurement modules frozen at SHA-256 `df4b1c6ac4feb0db7dbb91fa6a4f32ef779da9f2f91aba53fab7a0f7b75b5925`; unchanged throughout this run.
HR / noise parameters and new simulator seeds were fixed before model predictions; all ten cases are included.
No post-result DSP changes are permitted. These remain Gaussian-sum synthetic strips, not clinical validation.
