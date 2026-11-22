# GPT-only versus measured ECG pipeline

Educational screening tool, not a medical device.

Generated: 2026-11-22T10:06:41.424089+00:00

Ten fixed 12-second synthetic single-lead images, nominal HR 45–130 bpm,
including two irregular RR patterns and noisy / 50 Hz / baseline-wander cases.
Each method sees the **identical PNG**. Ground-truth HR is **60 / mean simulator RR**;
finite-strip irregular HR can differ from nominal HR. No dataset training.

| Case | True HR | True RR timing | GPT-only HR | GPT RR timing | Pipeline HR | Pipeline RR timing |
| --- | ---: | --- | ---: | --- | ---: | --- |
| regular_45 | 44.99 | regular | 45.00 | regular | 44.99 | regular |
| regular_58 | 58.00 | regular | 58.00 | regular | 58.01 | regular |
| regular_65 | 65.01 | regular | 65.00 | regular | 65.00 | regular |
| regular_72 | 72.01 | regular | 72.00 | regular | 72.01 | regular |
| regular_90 | 89.99 | regular | 90.00 | regular | 89.95 | regular |
| noisy_105 | 105.01 | regular | 105.00 | regular | 105.01 | regular |
| noisy_130 | 130.01 | regular | 130.00 | regular | 129.96 | regular |
| irregular_75 | 75.87 | irregular | 76.00 | irregular | 75.87 | irregular |
| irregular_110 | 110.99 | irregular | 111.00 | irregular | 110.99 | irregular |
| noisy_85 | 85.00 | regular | 85.00 | regular | 85.00 | regular |

HR prediction coverage: GPT **10/10**; pipeline **10/10**.

| Metric | GPT-only | Measured pipeline |
| --- | ---: | ---: |
| HR mean absolute error, identical 10 paired cases | 0.020 bpm | 0.008 bpm |
| Pipeline HR MAE, all available cases | — | 0.008 bpm |
| HR estimates within ±3 bpm, out of all 10 cases | 10/10 | 10/10 |
| Regular/irregular RR timing accuracy (unknowns count as misses) | 10/10 (100.0%) | 10/10 (100.0%) |

**Measured result:** pipeline HR MAE is **59.8% lower** on these 10 identical paired images.

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

Initial run and analytic correction:

- First run: GPT HR MAE **0.020 bpm**, pipeline **0.040 bpm**; GPT had lower error.
- The initial result is preserved in [comparison-initial.md](comparison-initial.md) and its JSON.
- A consistent calibration bias led to an analytic correction: normalize autocorrelation by
  overlapping sample count and derive time calibration from the horizontal grid rather than
  averaging it with the shorter vertical projection. No learned parameters or patient training.
- Revised pipeline results reuse the original GPT predictions for byte-identical PNGs.
  This is post-correction engineering validation on the same cases, not a held-out clinical study.
