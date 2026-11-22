import assert from 'node:assert/strict';
import { test } from 'node:test';
import worker from '../worker.js';

const origin = 'https://ecg-analyzer.example.workers.dev';
const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1sAAAAASUVORK5CYII=';
const env = { ECG_API_URL: 'https://dsp.example' };
const post = (path, body, headers = {}) => new Request(origin + path, {
  method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body),
});

test('Worker preserves static assets and security headers', async () => {
  const response = await worker.fetch(new Request(origin + '/'), { ASSETS: { fetch: async req => {
    assert.equal(new URL(req.url).pathname, '/index.html');
    return new Response('<h1>ECG Analyzer</h1>');
  } } });
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-security-policy'), /script-src 'self'/);
});

test('Worker validates method, origin, content type, size and legacy image data', async () => {
  assert.equal((await worker.fetch(new Request(origin + '/api/analyze'), env)).status, 405);
  assert.equal((await worker.fetch(post('/analyze', { image }, { Origin: 'https://other.example' }), env)).status, 403);
  assert.equal((await worker.fetch(post('/analyze', { image: 'not an image' }), env)).status, 400);
  assert.equal((await worker.fetch(post('/analyze-signal', {}, { 'Content-Type': 'text/plain' }), env)).status, 415);
  const oversized = new Request(origin + '/analyze', { method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Content-Length': '15000000' }, body: '{}' });
  assert.equal((await worker.fetch(oversized, env)).status, 413);
});

test('Worker requires a reachable DSP URL instead of sending images to GPT', async () => {
  const response = await worker.fetch(post('/analyze-signal', { sample_id: 'synth-regular' }), {});
  assert.equal(response.status, 503);
  assert.match((await response.json()).error, /ECG_API_URL/);
});

test('Worker proxies demo and raw signal JSON without AgentRouter credentials', async t => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (url, options) => {
    assert.equal(String(url), 'https://dsp.example/analyze-signal');
    assert.equal(options.headers.Authorization, undefined);
    assert.equal(JSON.parse(new TextDecoder().decode(options.body)).sample_id, 'synth-regular');
    return Response.json({ status: 'ok', measurements: { hr_mean_bpm: 72 }, explanation: null });
  };
  const response = await worker.fetch(post('/analyze-signal', { sample_id: 'synth-regular' }), env);
  assert.equal(response.status, 200);
  assert.equal((await response.json()).measurements.hr_mean_bpm, 72);
  assert.equal(response.headers.get('cache-control'), 'no-store');
});

test('Worker converts legacy images to the same measured multipart endpoint', async t => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (url, options) => {
    assert.equal(String(url), 'https://dsp.example/analyze');
    assert.ok(options.body instanceof FormData);
    assert.equal(options.body.get('pixels_per_mm'), '8');
    return Response.json({ status: 'ok', measurements: { hr_mean_bpm: 72 } });
  };
  assert.equal((await worker.fetch(post('/api/analyze', { image, pixels_per_mm: 8 }), env)).status, 200);
});
