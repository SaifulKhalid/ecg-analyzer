# Production deployment verification

Verified on 2026-11-23 (Asia/Dhaka).

- Public repository: https://github.com/SaifulKhalid/ecg-analyzer
- Frontend: https://ecg-analyzer.labddb.workers.dev
- Backend: https://ecg-analyzer-dsp-khalid-saifullahs-projects-239e324e.vercel.app
- Frontend source commit: `eb7efa79d5746963d9b112706f0bb62d05e2d5da`
- Cloudflare version: `eea32c96-74b3-4701-aba1-19e2c45cba24`
- Backend source commit: `e268af789e9f40613f9a25b489a4aa451101fdab`
- Vercel deployment: `dpl_2g8fb8z8zMBDwfUhPZ77RwgmZHTC`, READY, production, Singapore.

The backend container includes Python 3.13 and Node 22.18 for the existing
explanation bridge. Vercel built the image from the public Git repository.
Cloudflare serves the frontend and proxies the measured API. Backend measurement
modules are identical across the two deployment source commits.

| Check | Result |
| --- | --- |
| Cloudflare build and deployment | PASS |
| Vercel container build and production health | PASS; target sampling rate 250 Hz |
| Python regression suite | 111 passed |
| Node regression suite | 31 passed, including explicit backend redirect rejection |
| Desktop, 1280 x 1000 | Demo and multipart image upload return 200; both 72.009 bpm |
| Mobile, 390 x 844 | Demo and multipart image upload return 200; both 72.009 bpm |
| Rendered evidence | Four plots, eight numerical rows, digitization overlay for upload |
| Browser errors and horizontal overflow | None in the verified demo and upload flows |
| Image above 4 MB | Rejected in the frontend before upload |
| Credential paths and `.git/config` | Return 404 |
| Cross-origin analysis request | Rejected with 403 |
| Public Git history audit | No configured credential values or secret files found; no co-author trailers |

The browser tests used actual public requests and newly rendered synthetic ECG
images; analysis responses were not mocked. Screenshots and raw synthetic smoke
responses remain in ignored `test-results/`.

An optional live AI request with temperature compatibility enabled returned
HTTP 200, measured HR 72.009 bpm, and `explanation: null`. The provider error was
`Agentrouter returned no analysis. Please try again.` This verifies graceful
preservation of measurements, but does not establish a successful production AI
explanation. The strict-temperature default and numeric grounding remain intact.

Production serves four synthetic demos; MIT-BIH data is excluded from the image.
Vercel has a 4.5 MB request/response limit, so the frontend caps images at 4 MB.
Idle containers scale to zero and may need additional startup time. The
Cloudflare Worker uses manual redirect handling because its runtime rejects
`redirect: 'error'`; unexpected backend redirects are rejected explicitly.
