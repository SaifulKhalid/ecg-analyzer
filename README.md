# Measured ECG Analyzer

**Educational screening tool, not a medical device.**

The existing Node / vanilla web app now measures single-lead ECG signals with
our own DSP. GPT explains the measured JSON; it receives no image or raw samples
in production. Findings are possible or suggestive and need clinician review.
There is no dataset training.

## Architecture

```text
Single-lead PNG/JPG/WebP -> grid calibration + column median -> mV signal
Raw {fs, samples[]} -----+                                      |
MIT-BIH / synthetic demo +-------------------------------> resample 250 Hz
                                                               |
                                     0.5–40 Hz SOS band-pass + 50/60 Hz notch
                                                               |
                                   Own Pan-Tompkins: 5–15 Hz -> derivative
                                      -> square -> 150 ms integration
                                      -> adaptive thresholds / search-back
                                      -> R refinement within +/-50 ms
                                                               |
                                               HR + descriptive RR metrics
                                                               |
                            +------------------ quality gate ---+
                            |                                   |
                   insufficient_quality                    possible rules
                   rules / GPT skipped                          |
                                                     MEASURED JSON ONLY
                                                               |
                                                   shared AgentRouter client
                                                               |
                                             explanation / null + error note

Raw / filtered, spectrum, R events, RR tachogram -> existing Node frontend
```

FastAPI owns DSP. Node serves the existing HTML/CSS/JS and proxies the API.
`scripts/agentrouter_bridge.mjs` reuses `lib/analyze.js`: original Responses
endpoint, CLI headers, models and key fallback. The image-only GPT entry point
is used exclusively by the comparison script.

## Run locally

Use **Python 3.13** (tested) and **Node 22.18+**. From this directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the backend in one terminal:

```powershell
.\.venv\Scripts\python.exe -m ecg.api
```

Start the existing frontend in another terminal:

```powershell
npm start
```

Open **http://localhost:3000** and choose **Try demo ECG**. Five MIT-BIH demos
appear when downloaded; four synthetic demos always work offline. Uncheck the
AI explanation option to use DSP alone.

Backend default: **127.0.0.1:8765**. Port 8000 was blocked on this Windows machine.
To choose another port, run `python -m uvicorn ecg.api:app --port PORT_NUMBER` in
the activated environment and set `ECG_API_URL` to the same local URL for Node.

Credentials retain the existing names `AGENTROUTER_API_KEY` and
`AGENTROUTER_API_KEY_2`; ignored `config.local.js` remains the local fallback.
Node also reads an optional `.env`; [.env.example](.env.example) contains no keys.
Environment variables take precedence. Models default to `gpt-5.6-sol` and
`gpt-6.1-sol`; `AGENTROUTER_MODEL` / `AGENTROUTER_FALLBACK_MODEL` are optional overrides.

**Current provider limitation:** both available AgentRouter models reject the
required explanation temperature 0.2. The app preserves that setting and
returns `explanation: null` with an error note. DSP, demos and plots remain
available. The benchmark uses the original image-client model default temperature.

## Validate and compare

```powershell
# One-time, resumable download; data/ is excluded from Git.
.\.venv\Scripts\python.exe scripts/download_data.py
.\.venv\Scripts\python.exe scripts/validate.py
.\.venv\Scripts\python.exe scripts/validate.py --images

# Live GPT image-only calls, with checkpoints and bounded timeouts.
.\.venv\Scripts\python.exe scripts/compare_gpt.py
# Offline DSP; reuses matching GPT checkpoints or marks GPT not run.
.\.venv\Scripts\python.exe scripts/compare_gpt.py --offline

.\.venv\Scripts\python.exe -m pytest -q
npm test
```

The nine direct Python dependencies are pinned in [requirements.txt](requirements.txt).
[constraints.txt](constraints.txt) pins WFDB's pandas dependency to a compatible
version. No model weights, training framework or library beat detector is used.

MIT-BIH validation uses the first 60 seconds of lead 0, expert beat annotations,
and one-to-one matching within 150 ms. Each annotation and detection can match once.

| Record | Sensitivity | PPV |
| --- | ---: | ---: |
| 100 | 100.00% | 100.00% |
| 101 | 100.00% | 100.00% |
| 106 | 100.00% | 100.00% |
| 119 | 100.00% | 100.00% |
| 201 | 98.89% | 100.00% |
| **Macro mean** | **99.78%** | **100.00%** |

The detector passes the requested gate: record 100 ≥99% sensitivity / PPV and
both means ≥95%. One beat is missed in record 201. Counts and timing errors:
[validation.md](results/validation.md), [validation.json](results/validation.json).

Fourteen calibrated image round trips also pass the ≤3 bpm gate, including
MIT-BIH 100, inversion, irregular timing, fractional grid spacing and calibration
overrides. Details: [digitization.md](results/digitization.md).

| Same ten benchmark PNGs | GPT-only | Measured pipeline |
| --- | ---: | ---: |
| HR mean absolute error | 0.02047 bpm | **0.00823 bpm** |
| HR predictions available | 10/10 | 10/10 |
| HR within ±3 bpm | 10/10 | 10/10 |
| Regular / irregular RR timing accuracy | 100% | 100% |

The pipeline's mean HR error is **59.8% lower on these ten images**. The absolute
difference is small; categorical accuracy ties. The first run favored GPT
(pipeline MAE 0.04037 bpm). An analytic correction to finite-overlap grid
autocorrelation and horizontal time calibration removed a consistent bias.
Revised scores use byte-identical images and the **original GPT predictions**.
No cases were selected or new predictions requested to obtain the revised score.
This is post-correction engineering validation, not a held-out clinical study.

See [comparison.md](results/comparison.md), [comparison.json](results/comparison.json),
and the preserved [initial result](results/comparison-initial.md).
[UI verification](results/ui-verification.md) records actual desktop/mobile demos
and multipart image uploads. [PROGRESS.md](PROGRESS.md) records phases and assumptions.

## API

- `GET /health`: service status, version and target sampling rate.
- `GET /samples`: demo IDs and descriptions.
- `POST /analyze-signal`: `{ "fs": 250, "samples": [...] }` in **mV**, or
  `{ "sample_id": "mitdb-100" }`. Optional `explain: false`, `notch_hz: 50/60/null`.
- `POST /analyze`: multipart `image` with optional `pixels_per_mm`, `paper_speed`,
  `gain`, `crop_box`, `explain`, `notch_hz`. Crop bounds: `[left, top, right, bottom]`.

Responses contain `status`, `quality`, `measurements`, `findings`, `explanation`,
`plots` (base64 PNGs), and `warnings`. Poor quality skips rules and GPT.
Source limits: 2–300 seconds, raw signal fs 80–2000 Hz, images under 10 MB.
Node also supports `/api/` aliases; the old JSON image upload contract now
converts to multipart and passes through the digitizer.

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
Invoke-RestMethod -Uri http://127.0.0.1:8765/analyze-signal -Method Post `
  -ContentType 'application/json' -Body '{"sample_id":"synth-regular","explain":false}'
curl.exe -F "image=@strip.png" -F "explain=false" http://127.0.0.1:8765/analyze
```

## Limits and future work

- Single-lead, horizontal, clean strips only. Crop twelve-lead layouts; skew,
  glare, faint ink and overlapping traces can defeat extraction.
- Auto calibration assumes visible 1 mm pink/red grid repeats and square paper.
  Paper speed / gain default to 25 mm/s / 10 mm/mV; printed values are not OCR-read.
  Provide overrides when needed. Without a grid or manual scale, screening is blocked.
- No PR, QT/QTc, ST, QRS-width or axis measurement. R-event detection alone does
  not establish sinus rhythm or a clinical condition.
- SDNN, RMSSD, pNN50 and CV describe **all detected RR**, including possible ectopy
  and errors. They are not adjudicated NN autonomic HRV; short strips limit interpretation.
- SNR measures beat-template repeatability; varying morphology can lower it.
  Confidence badges are heuristic, not validated disease probabilities. RR
  irregularity alone cannot establish AFib.
- Five short MIT-BIH segments and ten Gaussian-sum images are limited engineering
  evidence. Clinical screening accuracy and photograph accuracy remain unproven.
- Future work: validated PR/QT/ST delineation; a separate CNN study on PTB-XL;
  AD8232 hardware integration through `/analyze-signal` with mV conversion and
  appropriate handling of streaming/filter boundaries.

The newly supplied local 600×333 sample works with crop `[35,224,555,294]` and
manual 2.4 px/mm (observed HR 74.59 bpm). That scale is an assumption, not reference
accuracy evidence. The original image is preserved and excluded from Git.

## Existing Cloudflare deployment

The Worker / Vite build remains supported. With Node 22.18+, run `npm run build`.
This machine's Node 22.14 required an isolated runtime for verification:

```powershell
npm.cmd exec --yes --package=node@22.18.0 -c "cf build"
```

The Worker proxies measured endpoints to a reachable FastAPI service configured
by `ECG_API_URL`. That service needs Python and Node for the shared AgentRouter
bridge. The old live site was not deployed by this mission; hosting the DSP
service is required before publishing the measured version.

**Educational screening tool, not a medical device.**
