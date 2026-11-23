# Measured ECG Analyzer

**Educational screening tool, not a medical device.**

The Node / vanilla web app presents single-lead ECG measurements as a scientific
report: sequential figures, a measured-values table,
JSON download and printing. The page always requests explain=false and leaves
interpretation to the clinician. The existing explanation API remains available.
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
                                               numeric / metric / unit guard
                                                               |
                                             explanation / null + error note

Raw / filtered, spectrum, R events, RR tachogram -> existing Node frontend
```

FastAPI owns DSP. Node serves the existing HTML/CSS/JS and proxies the API.
`scripts/agentrouter_bridge.mjs` reuses `lib/analyze.js`: original Responses
endpoint, CLI headers, models and key fallback. The image-only GPT entry point
is used exclusively by the comparison script.

## Run locally

Use **Python 3.13** (tested) and **Node 22.23+**. From this directory in PowerShell:

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

Open **http://localhost:3000**, choose a **Sample record** or **Choose file**, and
select **Analyze**. Five MIT-BIH records appear when downloaded; four synthetic
records work offline. The collapsed **Calibration** fields accept scale, speed,
gain, crop and mains frequency. The page displays measurements only.

Backend default: **127.0.0.1:8765**. Port 8000 was blocked on this Windows machine.
To choose another port, run `python -m uvicorn ecg.api:app --port PORT_NUMBER` in
the activated environment and set `ECG_API_URL` to the same local URL for Node.

Credentials retain the existing names `AGENTROUTER_API_KEY` and
`AGENTROUTER_API_KEY_2`; ignored `config.local.js` remains the local fallback.
Node also reads an optional `.env`; [.env.example](.env.example) contains no keys.
Environment variables take precedence. Models default to `gpt-5.6-sol` and
`gpt-6.1-sol`; `AGENTROUTER_MODEL` / `AGENTROUTER_FALLBACK_MODEL` are optional overrides.

**Temperature policy:** strict temperature 0.2 remains the default. Both current
AgentRouter models reject it, so strict mode returns `explanation: null` with an
error note. Set the API's allow_provider_default_temperature parameter to true
to explicitly request compatibility mode. Only an unsupported-temperature error
triggers one retry of the same measured JSON with the same model / key at the
provider default. The response includes `explanation_settings`. The report UI
does not request or display explanations. Other errors retain normal fallback / error handling.
Live five-section explanation evidence: [llm-compatibility.json](results/llm-compatibility.json).
The image-only benchmark continues to use the model default temperature.

**Explanation grounding:** a report-only copy of the measured JSON includes
metric definitions and screening thresholds from `ecg/config.py`. These remain
definitions, not observations. The report layer checks explicit numeric claims
against compatible units and named metrics, allowing honest rounding and
seconds/ms or fraction/percent conversions. Unsupported numbers, unavailable
waveform measurements and definite-condition claims return `explanation: null`
with an error note; the measured results remain available. The API exposes
`explanation_grounding` with the check status and reason codes.

Both synthetic live attempts are preserved: a
[rejected reply's API response](results/grounding-rejected.json) and a
[successful five-section reply](results/grounded-explanation.json) with 14 numeric
checks passed. This conservative guard may reject unfamiliar wording; it does
not prove all medical language is correct or check written-out numbers.

## Validate and compare

```powershell
# One-time, resumable download; data/ is excluded from Git.
.\.venv\Scripts\python.exe scripts/download_data.py
.\.venv\Scripts\python.exe scripts/validate.py
.\.venv\Scripts\python.exe scripts/validate.py --images
# Wider check against the committed whole-record protocol; preserves the first-minute table.
.\.venv\Scripts\python.exe scripts/validate_long.py

# Live GPT image-only calls, with checkpoints and bounded timeouts.
.\.venv\Scripts\python.exe scripts/compare_gpt.py
# Offline DSP; reuses matching GPT checkpoints or marks GPT not run.
.\.venv\Scripts\python.exe scripts/compare_gpt.py --offline

.\.venv\Scripts\python.exe -m pytest -q
npm test
```

Offline mode preserves historical GPT replies when their PNG hashes match,
even after a client-only update. Source protocol fingerprints are retained;
this is a comparison against the recorded replies, with no new API calls.

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

The unchanged detector was also checked on all five complete lead-0 recordings.
The protocol and file hashes were committed before evaluation. Processing uses
290-second central intervals plus five seconds of context on each side, retaining
events only in half-open central intervals to avoid double counting at seams:

| Complete record | Reference beats | Sensitivity | PPV |
| --- | ---: | ---: | ---: |
| 100 | 2,273 | 100.00% | 100.00% |
| 101 | 1,865 | 99.95% | 99.79% |
| 106 | 2,027 | 99.75% | 99.95% |
| 119 | 1,987 | 100.00% | 99.95% |
| 201 | 1,963 | 97.66% | 100.00% |
| **Macro mean** | **10,115 total** | **99.47%** | **99.94%** |

Coverage: **150.46 minutes**; pooled counts **10,063 TP / 6 FP / 52 FN**.
Pooled sensitivity is **99.49%**, PPV **99.94%**. Every missed/extra event is
recorded in [long-validation.json](results/long-validation.json); see the
[full table](results/long-validation.md) and
[predeclared protocol](results/long-validation-protocol.json). No detector tuning
followed this run. These are the same five selected records, not an independent
patient holdout; the check validates raw-signal R detection, not disease screening.

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

An additional fresh synthetic study committed its case manifest before GPT
requests and froze all measurement modules. HRs were uniformly sampled from
45–130 bpm with unused seeds, noise, two irregular and two inverted strips.
All ten cases are reported, with no post-result DSP changes:

| Fresh validation, frozen DSP | GPT-only | Measured pipeline |
| --- | ---: | ---: |
| HR mean absolute error | 0.19436 bpm | **0.01551 bpm** |
| Predictions available / HR within ±3 bpm | 10/10 | 10/10 |
| Regular / irregular RR timing accuracy | 100% | 100% |

HR MAE is **92.0% lower** on these fresh images. This is independent synthetic
parameter validation, with a small absolute difference; clinical accuracy remains
unproven. See [protocol](results/holdout/manifest.json) and
[fresh validation results](results/holdout/comparison.md). Reproduce with
`python scripts/compare_holdout.py --offline`; the committed manifest and
measurement-code fingerprint prevent silently changing the study.

[UI verification](results/ui-verification.md) records actual desktop/mobile demos
and multipart image uploads. [PROGRESS.md](PROGRESS.md) records phases and assumptions.

## API

- `GET /health`: service status, version and target sampling rate.
- `GET /samples`: demo IDs and descriptions.
- `POST /analyze-signal`: `{ "fs": 250, "samples": [...] }` in **mV**, or
  `{ "sample_id": "mitdb-100" }`. Optional `explain: false`, `notch_hz: 50/60/null`,
  `allow_provider_default_temperature: true` for explicit compatibility.
- `POST /analyze`: multipart `image` with optional `pixels_per_mm`, `paper_speed`,
  `gain`, `crop_box`, `explain`, `notch_hz`, `allow_provider_default_temperature`.
  Crop bounds: `[left, top, right, bottom]`.

Responses contain `status`, `quality`, `measurements`, `findings`, `explanation`,
`plots` (base64 PNGs), and `warnings`. Poor quality skips rules and GPT.
When GPT is called successfully, `explanation_grounding` records whether its
numbers passed the report checks. A rejected explanation keeps signal status
and measurements intact and supplies `explanation_error`.
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

- Images are prepared and one lead region is selected automatically when Crop
  is empty, including full 3x4, 12x1 and three-channel reports. Manual crops win.
  Separate lead cells are not stitched. Selection favors measurement quality,
  not clinical lead relevance. Glare, faint ink, overlapping traces, unusual
  labels/layouts and perspective distortion can defeat extraction.
- Preparation applies EXIF orientation, RGB/white-alpha conversion, quarter-turn
  orientation, deskew up to 15 degrees and a 3000 px long-side limit. No perspective
  correction or OCR. Without directional text, 180-degree orientation can be
  ambiguous. Manual crops use EXIF-oriented upload coordinates and disable
  automatic rotation/deskew; resizing scales crop coordinates and pixels/mm.
- Auto calibration supports colored and faint gray grid repeats and assumes the
  first recovered repeat is 1 mm on square paper. Major-grid-only images can
  give the wrong scale; provide pixels/mm when calibration is uncertain.
  Paper speed / gain default to 25 mm/s / 10 mm/mV; printed values are not OCR-read.
  Without grid/manual scale, a page-width strip assumes 10 s at 25 mm/s and adds
  that explicit Note. Amplitude range/gain are unavailable and axes use arbitrary
  units. Other unknown time scales remain unmeasured. Automatic regions under
  five seconds show the quality notice and unavailable HR/RR summary values.
- No PR, QT/QTc, ST, QRS-width or axis measurement. R-event detection alone does
  not establish sinus rhythm or a clinical condition.
- SDNN, RMSSD, pNN50 and CV describe **all detected RR**, including possible ectopy
  and errors. They are not adjudicated NN autonomic HRV; short strips limit interpretation.
- SNR measures beat-template repeatability; varying morphology can lower it.
  The report UI shows measurements and quality notices, with no badges or
  interpretation. RR irregularity alone cannot establish AFib.
- Five MIT-BIH recordings (150.46 minutes) and twenty Gaussian-sum comparison
  images are limited engineering evidence. Clinical screening accuracy and
  photograph accuracy remain unproven; no independent patient holdout was used.
- Explanation numbers are checked conservatively; written-out numbers and
  arbitrary medical prose are outside that check's scope. Clinician review
  remains necessary even when the numeric check passes.
- Future work: validated PR/QT/ST delineation; a separate CNN study on PTB-XL;
  AD8232 hardware integration through `/analyze-signal` with mV conversion and
  appropriate handling of streaming/filter boundaries.

The previous local 600×333 sample worked with manual crop `[35,224,555,294]`
and 2.4 px/mm (observed HR 74.59 bpm); this is historical functional evidence.
That sample and `ECG .png` are absent from the new clone. Their automatic-selection
accuracy has not been assessed here. Supplied images are never modified.

Run `python scripts/validate_layout.py` to reproduce the 32 report variants and
process every available image in `samples/reports/`, plus those two named samples.
Results: [layout-validation.md](results/layout-validation.md). Local outlined
previews go to `results/layout-visual/`. Synthetic validation is engineering
evidence, not clinical accuracy. Image responses add `region_selection` and
`plots.prepared_image`; existing request parameters and fields remain available.

## Production deployment

- Frontend: https://ecg-analyzer.labddb.workers.dev
- Backend: https://ecg-analyzer-dsp-khalid-saifullahs-projects-239e324e.vercel.app
- Public source: https://github.com/SaifulKhalid/ecg-analyzer

The Worker / Vite build remains supported. With Node 22.23+, run `npm run build`.
For an older local Node version, use an isolated runtime:

```powershell
npm.cmd exec --yes --package=node@22.23.0 -c "cf build"
```

The frontend runs on Cloudflare Workers. The Worker proxies measured endpoints
to the FastAPI backend configured by `ECG_API_URL` at build time. Deploy the
backend first, then build and deploy the frontend with that public HTTPS URL.

The backend uses Vercel's Container preset and [Dockerfile.vercel](Dockerfile.vercel).
It includes Python 3.13, Node 22.18 for the existing explanation bridge, and the
pinned API dependencies in [requirements-runtime.txt](requirements-runtime.txt).
It listens on port 80. Configure `AGENTROUTER_API_KEY` and
`AGENTROUTER_API_KEY_2` as encrypted production environment variables in Vercel;
credential files are excluded from the build context and image. The production
image serves the four synthetic demos; cached MIT-BIH data stays local.

Vercel builds the container from the Git repository, so Docker is not required
on this Windows machine. Container Functions scale to zero after five minutes
idle and can take longer on the first request. Vercel's request/response limit
is 4.5 MB; uploads below 3.5 MB leave headroom for multipart fields.
The report UI accepts original files up to 25 MB and resizes files above 3.5 MB
with canvas (long side <=3000 px, JPEG quality 0.9), preserving the filename.
Resize metadata is included in the JSON download. The local API limit remains 10 MB.
The explanation API retains its strict-temperature and numeric-grounding checks;
the report UI always sends explain=false.

```powershell
# ECG_API_URL overrides the deployed backend default when needed.
npm.cmd exec --yes --package=node@22.23.0 -c "cf build"
npm.cmd exec --yes --package=node@22.23.0 -c "cf deploy --prebuilt"
```

**Educational screening tool, not a medical device.**
