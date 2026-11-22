# UI flow verification

Educational screening tool, not a medical device.

Generated: 2026-11-22T13:15:56.177575+00:00

Actual local services: Node :3000 -> FastAPI :8765 -> own DSP.
Live-flow requests disable LLM; the separate explanation rendering check uses a mock.

- PASS: desktop: MIT-BIH 100 demo -> actual Node proxy -> actual FastAPI -> 74 beats, HR 73.87 bpm -> 3 cards / 4 PNGs; no upload, no overflow.
- PASS: Synthetic irregular demo renders evidence and heuristic confidence badges through the actual DSP API.
- PASS: Mock-only UI explanation: explicit compatibility flag sent, provenance visible, five sections render as text; injected HTML never executes.
- PASS: Existing image preview / removal flow is preserved.
- PASS: Actual multipart image upload -> automatic grid -> shared DSP -> HR 72.01 bpm, recovered 8 px/mm and debug overlay.
- PASS: Local twelve-lead input works after explicit bottom-strip crop / manual 2.4 px/mm; HR 74.59 bpm is an assumed-calibration measurement, not accuracy ground truth.
- PASS: mobile: MIT-BIH 100 demo -> actual Node proxy -> actual FastAPI -> 74 beats, HR 73.87 bpm -> 3 cards / 4 PNGs; no upload, no overflow.
- PASS: No browser JavaScript / console errors on desktop or mobile.
