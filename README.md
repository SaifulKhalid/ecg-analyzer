# ECG Analyzer

A webpage for uploading an ECG image and requesting an AI interpretation from Agentrouter using `gpt-5.6-sol`, with `gpt-6.1-sol` as the fallback.

## Run

Install Node.js 22 or newer, then run:

```sh
npm start
```

Open http://localhost:3000. Local Node development needs no build step or runtime dependencies.

Local Node development loads `apiKey` and `apiKey2` from the ignored, server-only `config.local.js`. Environment variables `AGENTROUTER_API_KEY` and `AGENTROUTER_API_KEY_2` override them. The Node server serves only the public page files; Vite also denies access to local credential files. Neither key is included in the Worker source or public assets.

The server calls `https://agentrouter.org/v1/responses` with image input, `stream: false`, and `store: false`. It requests a JSON report, validates it, and renders a numerical measurements table followed by prose paragraphs. Values that cannot be reliably measured appear as “Not measurable.” The report omits generic next steps and clinician-review reminders. A short AI accuracy notice remains in the footer.

Requests start with `gpt-5.6-sol` and the first key. Authorization errors and rate limits try the second key with the same model. Model errors, incomplete or invalid reports, connection failures, and a 75-second primary timeout switch to `gpt-6.1-sol`, preferring the second key. Each fallback attempt is limited to 35 seconds, within the existing 120-second overall request limit. Explicit provider refusals and content blocks stop without retries. The page shows elapsed time and the final completion time.

Live latency checks on the same synthetic ECG returned the previous report in 36 seconds and a valid new JSON report in 60 seconds. Lower-reasoning and strict-schema variants failed or timed out through Agentrouter, so those options were removed. The added numerical measurements can require more model reasoning; a reduction in successful analysis time is not established. Fallback model access also depends on the provider: the live `gpt-6.1-sol` probe timed out. Retry routing is covered by mocked tests.

Live site: https://ecg-analyzer.labddb.workers.dev

The URL above is the existing deployment. These updates are local until deployed. Desktop and mobile Chromium checks cover the table, paragraph order, repeated analysis, removal, and page width. The API and Worker tests use mocked responses and do not spend credits.

## Deploy to Cloudflare Workers

Use Node.js 22.23 or newer, or a current Node.js LTS release. Install the deployment tools and sign in to Cloudflare:

```sh
npm install
npx cf auth login
npm run build
npx cf deploy --secrets-file .secrets.local.json
```

`cloudflare.config.ts` defines the `ecg-analyzer` Worker, its workers.dev route, and both API key secret bindings. `vite.config.js` builds the page and Worker separately; only built page assets are public. `worker.js` handles `/api/analyze` and serves the page through the `ASSETS` binding. The ignored `.secrets.local.json` provides both credentials during deployment; `.dev.vars` provides them for local Worker development. Recreate those ignored files or provide the equivalent secrets when copying the project. Cloudflare CLI sign-in is required to update the existing live site.

Use `npm run dev:worker` to test in the local Workers runtime. The CLI prints the local URL.

Images are limited to PNG, JPG, and WebP files up to 10 MB. They are held in memory for the request, not saved locally. Agentrouter handles the image according to its own data policies.

Use `npm run dev` to restart the server automatically after changes, or `npm test` to run API checks without making paid requests.

AI interpretations need review by a qualified clinician and cannot replace clinical assessment.
