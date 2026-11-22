# UI flow verification

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
