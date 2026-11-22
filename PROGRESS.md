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
| 1 Core DSP + gate | 75 min | Complete | 3.3 min | Record 100: 100% / 100%; means: 99.78% / 100%; 20 DSP tests pass |
| 2 Rules + LLM + API | 45 min | Complete | 12.5 min | 38 Python + 27 Node tests pass; signal API works; provider rejects required temperature |
| 3 UI + plots | 60 min | In progress | 0 | Start 09:03 UTC; preserve existing styling, add demo/results panel |
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
- Live AgentRouter catalog exposes only `gpt-5.6-sol` and `gpt-6.1-sol`. Both
  reject the required `temperature: 0.2`, including a short compatibility probe
  with reasoning disabled. Keep the requested temperature and return null
  explanation plus provider error; do not silently change it. The image-only
  comparison has no mandated temperature and uses the original model default.
- Plot response slot is implemented; actual figures are the phase 3 task.

## Definition of done

- [x] `validate.py` table exists with real numbers
- [ ] Demo dropdown works end to end
- [x] `/analyze-signal` works
- [ ] `/analyze` works on a rendered grid image
- [x] Production GPT gets measured JSON only
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
- 08:50 UTC — Own detector passed on the first attempt without dataset tuning:
  100 / 101 / 106 / 119 each 100% sensitivity and PPV; 201 98.89% sensitivity,
  100% PPV (one missed annotation at 48.7583 s). Macro means 99.78% / 100%.
  `results/validation.md` and JSON contain original counts and timing errors.
  20 tests pass (polarity, rates 45–130, hum / drift, resampling, feature formulas,
  double-count prevention and invalid / flat inputs). Fixed cp1252 console
  printing; no detector tuning is needed. Commit phase 1, then start phase 2.
- 08:50:30 UTC — Phase 1 committed; phase 2 started early after the gate passed.
- 09:02 UTC — Added rate / RR evidence rules, beat-repeatability SNR / quality
  gate, FastAPI signal and demo endpoints, and private stdin/stdout Node bridge
  to the existing AgentRouter client. Production Node and Worker routes proxy
  all images to DSP; even the old JSON image contract now digitizes first.
  Image-only GPT is retained solely as an explicit benchmark CLI entry point.
  Boundary tests verify no image / plots / raw samples reach the explainer.
  All 9 demos pass quality; 38 Python tests and 27 Node tests pass. Live call
  demonstrates graceful provider failure at the requested temperature. No
  phase overrun or fallback needed beyond the explicitly allowed null explanation.
