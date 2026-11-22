# New laptop setup verification

Date: 2026-11-23 Asia/Dhaka (2026-11-22 UTC). Part A started at 20:51 UTC
and verification finished before 21:01 UTC, within the 15-minute maximum.

| Step | Result | Evidence |
| --- | --- | --- |
| 1 Repository review | PASS | PROGRESS.md, README.md and git log --oneline -15 read; stack summarized in five lines in PROGRESS.md |
| 2 Dependencies | PASS | Portable Python 3.13.7, .venv, pip install -r requirements.txt -c constraints.txt; pip check clean; wfdb 4.3.0/pandas 2.2.3 import; Node 22.23.0; npm install reports zero vulnerabilities |
| 3 Credential configuration | PASS (documented fallback) | AGENTROUTER_API_KEY and AGENTROUTER_API_KEY_2 names exist in .env.example. Neither environment key is configured; .env/config.local.js are absent. Create .env from .env.example when credentials are wanted. Continue with ECG_LLM_ENABLED=0; sample request sends explain=false. No secret values printed or committed. |
| 4 MIT-BIH download | PASS | python scripts/download_data.py downloaded all .hea/.dat/.atr files for 100, 101, 106, 119 and 201 into ignored data/mitdb |
| 5 Full tests | PASS | Final pytest -q: 111 passed, no skips, 56.06 s. npm test: 31 passed, zero failures. Matplotlib/PyParsing emits 14 nonfatal upstream deprecation warnings. |
| 6 Frozen measurements | PASS | The actual scripts.compare_holdout.measurement_fingerprint() matches the original manifest: df4b1c6ac4feb0db7dbb91fa6a4f32ef779da9f2f91aba53fab7a0f7b75b5925 |
| 7 Live services/sample | PASS | http://127.0.0.1:8765/health and http://127.0.0.1:3000/ work. Frontend serves HTML, JS and CSS with HTTP 200. Its /samples proxy returns nine records. /analyze-signal with mitdb-100/explain=false returns status ok, 60 s at 250 Hz, 74 peaks, HR 73.867 bpm and SNR 16.51 dB. All four plot payloads decode to valid PNGs. |

The initial Python run had one data-dependent skip while the download was in
progress; the full suite was repeated after download and all 111 tests executed.
The live sample check exercised Node -> FastAPI over HTTP. It was not a browser
layout, uploaded-image, mobile, or DOM-copy verification.

## Setup changes and assumptions

- .gitattributes: force LF for Python files. Windows core.autocrlf=true changed
  frozen source bytes on clone: initial checkout hash was
  3cf1d3d54764562982dba17118e3e37cd22b641da63da911c8bd89e7cd90a3b5.
  Committed source bytes matched the original manifest. Restoring LF fixed the
  checkout hash; no Python logic or tracked Python blob changed.
- package.json, package-lock.json and README.md: raise the Node minimum from
  22.18 to 22.23 to match the locked Cloudflare tool's engine requirement. No
  package versions were changed.
- PROGRESS.md and this report: assumptions, step results and the blocker.
- Portable tools live under C:/Users/acer/AppData/Local/ecg-tools. The user's
  PATH includes Python, Node/npm and the existing Git cmd directory. Open a
  new terminal to receive that PATH. .venv uses the portable Python installation.
- No Git author was configured; the setup commit uses repository-local Codex
  <codex@localhost>. No global author setting is changed.
- Automatic approval rejected the installer launch and the npm start launch
  without a more specific reason. Safe alternatives succeeded: extract the
  official portable Python package, and launch the reviewed server.js entry
  point directly with Node. Both normal local application services remain running.

## Part B / Part C blocker

Part B requires edits to ecg/plots.py (200 dpi, no in-image titles, new grid and
trace style) while requiring the existing frozen fingerprint to remain equal.
scripts/compare_holdout.py includes plots in MEASUREMENT_FILES and hashes every
byte of that file. results/holdout/manifest.json freezes the hash above.

These requirements cannot both be satisfied. Rewriting the fingerprint function,
removing plots from its file list, changing the manifest, or substituting a hash
would invalidate the predeclared study. The request explicitly requires retaining
the original match. Stopped before UI/plot modifications rather than falsifying
that check. Resolving this requires revising the plot-freeze constraint or the
requested plotting scope; no such authorization was assumed.

Part B files changed: none. Part C files changed: none. No new selection strategy
was implemented, no report variants or layout QA were run, and no UI/layout
validation success is claimed. Existing multi-lead rejection/manual cropping
behavior remains. sample_ECG_image.png, ECG .png and samples/reports/ are absent
from this cloned checkout; they were not analyzed.
