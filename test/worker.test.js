import assert from 'node:assert/strict';
import { test } from 'node:test';
import worker from '../worker.js';

const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1sAAAAASUVORK5CYII=';
const report = {
  measurements: [{ label: 'Heart rate', value: null, unit: 'bpm', note: 'Trace not readable.' }],
  explanation: ['Please upload a clearer ECG.'],
};
const keys = { AGENTROUTER_API_KEY: 'worker-test-key' };
const origin = 'https://ecg-analyzer.example.workers.dev';
const request = (body, headers = {}) => new Request(origin + '/api/analyze', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', ...headers },
  body: JSON.stringify(body),
});

test('Worker serves built static assets with the page security headers', async () => {
  const response = await worker.fetch(new Request(origin + '/assets/app-123.js'), {
    ASSETS: { fetch: async () => new Response('console.log("app")', { headers: { 'Content-Type': 'text/javascript' } }) },
  });
  assert.equal(response.status, 200);
  assert.equal(await response.text(), 'console.log("app")');
  assert.match(response.headers.get('content-security-policy'), /script-src 'self'/);
  const homepage = await worker.fetch(new Request(origin + '/'), {
    ASSETS: { fetch: async req => {
      assert.equal(new URL(req.url).pathname, '/index.html');
      return new Response('<h1>ECG Analyzer</h1>');
    } },
  });
  assert.equal(homepage.status, 200);
  assert.match(await homepage.text(), /ECG Analyzer/);
});

test('Worker validates API requests before making a provider call', async () => {
  assert.equal((await worker.fetch(new Request(origin + '/api/analyze'), {})).status, 405);
  assert.equal((await worker.fetch(request({ image }, { Origin: 'https://another-site.example' }), {})).status, 403);
  assert.equal((await worker.fetch(request({ image: 'not an image' }), keys)).status, 400);
  const oversized = new Request(origin + '/api/analyze', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': '15000000' }, body: '{}',
  });
  assert.equal((await worker.fetch(oversized, keys)).status, 413);
  assert.equal((await worker.fetch(request({ image }), {})).status, 503);
});

test('Worker uses the configured key and returns Responses API text', async t => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (url, options) => {
    assert.equal(url, 'https://agentrouter.org/v1/responses');
    assert.equal(options.headers.Authorization, 'Bearer worker-test-key');
    const body = JSON.parse(options.body);
    assert.equal(body.model, 'gpt-5.6-sol');
    assert.equal(body.input[1].content[1].image_url, image);
    return Response.json({ status: 'completed', output: [
      { type: 'reasoning', summary: [] },
      { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: JSON.stringify(report) }] },
    ] });
  };
  const response = await worker.fetch(request({ image }), { AGENTROUTER_API_KEY: 'worker-test-key' });
  assert.equal(response.status, 200);
  assert.deepEqual((await response.json()).report, report);
  assert.equal(response.headers.get('cache-control'), 'no-store');
});

test('Worker reports an incomplete report as an error', async t => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async () => Response.json({ status: 'incomplete', output: [
    { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: 'Partial report' }] },
  ] });
  const response = await worker.fetch(request({ image }), { AGENTROUTER_API_KEY: 'worker-test-key' });
  assert.equal(response.status, 502);
  assert.match((await response.json()).error, /incomplete analysis/);
});

test('Worker passes its second secret to the model fallback', async t => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  const attempts = [];
  globalThis.fetch = async (url, options) => {
    attempts.push([JSON.parse(options.body).model, options.headers.Authorization]);
    if (attempts.length === 1) return Response.json({ error: { message: 'Model unavailable.' } }, { status: 503 });
    return Response.json({ status: 'completed', output: [
      { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: JSON.stringify(report) }] },
    ] });
  };
  const response = await worker.fetch(request({ image }), { ...keys, AGENTROUTER_API_KEY_2: 'worker-second-key' });
  assert.equal(response.status, 200);
  assert.deepEqual(attempts, [['gpt-5.6-sol', 'Bearer worker-test-key'], ['gpt-6.1-sol', 'Bearer worker-second-key']]);
});
