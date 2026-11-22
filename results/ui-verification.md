# UI flow verification

## Report UI verification (2026-11-23 Asia/Dhaka)

Part B: PASS. Installed Chrome, driven through tests/ui_qa.mjs using CDP; no
additional QA or runtime dependency. Actual requests go through Node :3000 to
the local FastAPI service :8765. The UI always sends explain=false.

| Input | Width | Figures | Overflow | Console errors | Copy-deck audit |
| --- | ---: | ---: | --- | ---: | --- |
| MIT-BIH 100 | 1280 | 4, sequentially numbered | None | 0 | PASS |
| Calibrated 72 bpm image strip | 1280 | 6, sequentially numbered | None | 0 | PASS |
| MIT-BIH 100 | 390 | 4, sequentially numbered | None | 0 | PASS |
| Calibrated 72 bpm image strip | 390 | 6, sequentially numbered | None | 0 | PASS |

Checks: table contains all 11 parameters and correct rounding; RR CV displays
4.6% for record 100; sample Notes absent; image Notes contain only calibration
assumptions. Captions are one line below figures. One footer only. Calibration
starts collapsed. Enabled buttons are solid navy; disabled buttons are dimmed.
Print media hides Input and actions, and figures avoid internal page breaks.
The DOM text is saved in test-results/part-b-*-dom.txt; rg banned-word search
returns no matches. QA also checks all displayed text against the deck plus
record IDs, measured values and input-dependent Notes.

Report plots use ecg/report_plots.py: 200 dpi, no titles, labeled axes, pink
0.04 s/0.1 mV minor and 0.2 s/0.5 mV major grid, near-black waveforms, red filled
R markers, gray/navy spectra with a dashed mains legend entry, a 105 dB display
range, and small tachogram markers. Frozen ecg/plots.py remains unchanged.

Full pytest: 113 passed. npm test: 31 passed. Dedicated plot checks assert no
titles, axis units, marker color and encoded 200 dpi. Original explanation
code and its API/client tests still pass. Actual frozen fingerprint matches
df4b1c6ac4feb0db7dbb91fa6a4f32ef779da9f2f91aba53fab7a0f7b75b5925.

Local artifacts: test-results/part-b-qa.json and
test-results/part-b-{sample,image}-{1280,390}.png. Desktop screenshot visually
inspected. These generated artifacts are ignored; supplied images are untouched.
Browser resizing and full-report verification will be recorded below in Part C.

The earlier verification follows for historical context; it describes the old UI.

Educational screening tool, not a medical device.

Generated: 2026-11-22T16:43:26.582253+00:00

Actual local services: Node :3000 -> FastAPI :8765 -> own DSP.
Live DSP requests disable LLM; explanation rendering uses an injection mock and a replay of the saved actual grounded reply against matching fresh measurements.

Story: choose a demo or upload one strip -> Node proxy -> FastAPI DSP -> measured
JSON -> optional AgentRouter explanation and numeric check -> browser results.

| Boundary | Status | Evidence |
| --- | --- | --- |
| Browser -> Node -> FastAPI | PASS | Actual desktop/mobile MIT-BIH demos and multipart uploads return HTTP 200 |
| Signal -> measurements | PASS | MIT-BIH 100 has 74 detected beats; rendered strip measures 72.01 bpm |
| Measured JSON -> AgentRouter -> guard | PASS | Two actual synthetic live requests; one rejected reply preserved, one five-section reply passes 14 numeric checks |
| Response -> browser | PASS | Matching fresh synthetic measurements/plots plus replay of the actual saved reply render five sections and grounding metadata |
| Browser safety / layout | PASS | Mock injected HTML stays text; no overflow or console errors |

The first browser check found the grounding field missing from the expandable
JSON panel. `app.js` now includes it; the repeated complete flow passes. No
additional GPT calls were used for the browser replay.

- PASS: desktop: MIT-BIH 100 demo -> actual Node proxy -> actual FastAPI -> 74 beats, HR 73.87 bpm -> 3 cards / 4 PNGs; no upload, no overflow.
- PASS: Synthetic irregular demo renders evidence and heuristic confidence badges through the actual DSP API.
- PASS: Mock-only UI explanation: explicit compatibility flag sent, provenance visible, five sections render as text; injected HTML never executes.
- PASS: Saved actual gpt-5.6-sol reply renders all five sections with 14 numeric checks passed; replay uses freshly measured matching synthetic ECG/plots and no additional model call.
- PASS: Existing image preview / removal flow is preserved.
- PASS: Actual multipart image upload -> automatic grid -> shared DSP -> HR 72.01 bpm, recovered 8 px/mm and debug overlay.
- PASS: Local twelve-lead input works after explicit bottom-strip crop / manual 2.4 px/mm; HR 74.59 bpm is an assumed-calibration measurement, not accuracy ground truth.
- PASS: mobile: MIT-BIH 100 demo -> actual Node proxy -> actual FastAPI -> 74 beats, HR 73.87 bpm -> 3 cards / 4 PNGs; no upload, no overflow.
- PASS: No browser JavaScript / console errors on desktop or mobile.
