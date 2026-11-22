# ECG measurement mission

Educational screening tool, not a medical device.

Start: **2026-11-22 08:33:48 UTC / 14:33:48 Asia/Dhaka**.
Hard stop: **2026-11-22 13:33:48 UTC / 19:33:48 Asia/Dhaka** (300 minutes).
Time boxes are ceilings: advance as soon as a phase is complete. If a phase
exceeds its box by 20%, use its fallback, document it, and advance. No individual
problem gets more than 10 uninterrupted minutes; change approach or seek the
permitted helper second opinion.

| Phase | Budget | Status | Time spent | Evidence / fallback |
| --- | ---: | --- | ---: | --- |
| 0 Recon + skeleton | 15 min | Complete | 13.4 min | Baseline + skeleton; pinned environment; all five MIT-BIH records cached |
| 1 Core DSP + gate | 75 min | In progress | 0 | Started 08:47:13 UTC; gate required before phase 2 |
| 2 Rules + LLM + API | 45 min | Pending | 0 | Explanation may be null; measurements remain usable without API |
| 3 UI + plots | 60 min | Pending | 0 | Preserve existing white/blue styling and add demo/results panel |
| 4 Image digitizer | 75 min | Pending | 0 | If auto grid fails, require explicit pixels/mm; single-lead only |
| 5 GPT comparison | 25 min | Pending | 0 | Unavailable GPT calls must be marked not run, never fabricated |
| 6 Wrap + checks | 5 min | Pending | 0 | Full pytest + existing Node tests, reproducible README |

## Recon and assumptions

- Existing stack: Node HTTP server (`server.js`), vanilla `app.js` / `index.html`
  / `style.css`; Vite + Cloudflare Worker build remains supported.
- Existing AgentRouter client: `lib/analyze.js`, POST
  `https://agentrouter.org/v1/responses`, primary `gpt-5.6-sol`, fallback
  `gpt-6.1-sol`, existing CLI User-Agent + X-App headers. Keys are
  `AGENTROUTER_API_KEY` and `AGENTROUTER_API_KEY_2`, with ignored local
  `config.local.js` fallback. Reuse this client through a small Node bridge for
  Python, sharing credentials, headers, fallback, and transport.
- No Python backend existed. Add FastAPI for DSP; retain Node as the frontend
  server and proxy measured endpoints to FastAPI. No dataset training.
- No Git repository existed. Created a baseline commit before new implementation.
  `data/`, all local credential files, virtual environment, images and helper
  prompts are ignored. Only `.env.example` may be committed.
- PowerShell has no `which`; ran its `Get-Command agy, freebuff` equivalent.
  Both exist. `agy --help` offers `--print` + `--print-timeout`; `freebuff --help`
  provides no one-shot flag. Use agy only for README, styling, boilerplate tests,
  or second opinions; review every diff. All DSP / digitizer logic is my own.
- Use Python 3.13 in an isolated `.venv`, with exactly the requested nine pinned
  direct dependencies; dependencies brought in by those packages are expected.
- Validate lead 0, first 60 s, with beat annotation symbols only and 150 ms
  one-to-one matching. Preserve annotation timing when resampling to 250 Hz.
- RR variability is descriptive, not normal-to-normal HRV: ectopic intervals
  remain included. A possible irregular-rhythm flag cannot establish AFib.
- Comparison uses the same calibrated image per method and fixed unseen
  synthetic test parameters; simulator beat timing supplies ground truth.
  Report paired coverage and errors before claiming improvement.

## Known issues

- PyPI and PhysioNet are reachable. An initial download timed out and was retried with a 60 s
  socket timeout. wfdb 4.3.0 import fails with newly released pandas 3.1.1;
  `constraints.txt` pins its existing transitive dependency to pandas 2.2.3.
- Existing image-only path is a legacy baseline; the finished UI must use only
  measured endpoints. Cloudflare needs an external reachable DSP service.

## Definition of done

- [ ] `validate.py` table exists with real numbers
- [ ] Demo dropdown works end to end
- [ ] `/analyze-signal` works
- [ ] `/analyze` works on a rendered grid image
- [ ] Production GPT gets measured JSON only
- [ ] `comparison.md` exists
- [ ] `pytest` passes
- [ ] README has architecture diagram + limitations

## Work log

- 08:33:48 UTC — Start; checked helper help, source files, environment and
  credential names without printing secrets.
- 08:35 UTC — Created baseline commit; skeleton and pinned requirements added.
- 08:43 UTC — agy wrote an ignored README draft only. Reviewed its output:
  remove unproved superiority claims, incorrect interval-delineation statements,
  speculative clipping checks, and machine-specific file:// links before use.
- 08:45 UTC — Dependency compatibility fixed. PhysioNet returned HTTP 502 during
  wfdb's record-header preflight; switch to wfdb's exact-file download rather
  than repeatedly requesting metadata. Data remain uncommitted.
- 08:47:13 UTC — Phase 0 complete: all 15 requested MIT-BIH files cached; 9.75 MB
  of signal data plus original headers / annotations; pip check passes. Retried
  only missing files after transient 502 responses. Start phase 1 (75 min box).
