# UI flow verification

Educational screening tool, not a medical device.

Generated: 2026-11-22T09:21:43.802352+00:00

Actual local services: Node :3000 -> FastAPI :8765 -> own DSP.
Live-flow requests disable LLM; the separate explanation rendering check uses a mock.

- PASS: desktop: MIT-BIH 100 demo -> actual Node proxy -> actual FastAPI -> 74 beats, HR 73.87 bpm -> 3 cards / 4 PNGs; no upload, no overflow.
- PASS: Synthetic irregular demo renders evidence and heuristic confidence badges through the actual DSP API.
- PASS: Mock-only UI explanation check: five sections render as text; injected HTML never executes.
- PASS: Existing image preview / removal flow is preserved.
- PASS: mobile: MIT-BIH 100 demo -> actual Node proxy -> actual FastAPI -> 74 beats, HR 73.87 bpm -> 3 cards / 4 PNGs; no upload, no overflow.
- PASS: No browser JavaScript / console errors on desktop or mobile.
