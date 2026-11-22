import assert from 'node:assert/strict';
import { once } from 'node:events';
import { test } from 'node:test';
import { createApp } from '../server.js';

const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1sAAAAASUVORK5CYII=';
const measured = { status: 'ok', quality: { status: 'ok', beat_count: 14 }, measurements: { hr_mean_bpm: 72 },
  findings: [], explanation: null, plots: {}, warnings: ['Educational screening tool, not a medical device.'] };

async function startServer(t, fetchImpl) {
  const server = createApp({ fetchImpl, dspUrl: 'http://dsp.example:8000' });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  const url = `http://127.0.0.1:${server.address().port}`;
  return { url, post: (path, body, headers = {}) => fetch(url + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...headers },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  }) };
}

test('Node serves only public files and retains security headers', async t => {
  const app = await startServer(t, () => assert.fail('Static page must not reach the provider.'));
  const page = await fetch(app.url);
  assert.equal(page.status, 200);
  assert.match(await page.text(), /ECG Analyzer/);
  assert.match(page.headers.get('content-security-policy'), /frame-ancestors 'none'/);
  for (const path of ['/config.local.js', '/.env', '/.secrets.local.json', '/.dev.vars', '/ecg/config.py',
    '/data/mitdb/100.dat', '/server.js', '/package.json', '/..%2fconfig.local.js']) {
    assert.equal((await fetch(app.url + path)).status, 404);
  }
});

test('health and demo aliases proxy only to the DSP service without provider credentials', async t => {
  const seen = [];
  const app = await startServer(t, async (url, options) => {
    seen.push(String(url));
    assert.equal(options.method, 'GET');
    assert.equal(options.headers.Authorization, undefined);
    return Response.json(String(url).endsWith('/samples') ? [{ sample_id: 'synth-regular' }] : { status: 'ok' });
  });
  for (const path of ['/health', '/api/health', '/samples', '/api/samples']) {
    assert.equal((await fetch(app.url + path)).status, 200);
  }
  assert.deepEqual(seen, ['http://dsp.example:8000/health', 'http://dsp.example:8000/health',
    'http://dsp.example:8000/samples', 'http://dsp.example:8000/samples']);
});

test('raw samples and demo IDs reach the measured signal endpoint', async t => {
  const app = await startServer(t, async (url, options) => {
    assert.equal(String(url), 'http://dsp.example:8000/analyze-signal');
    const payload = JSON.parse(options.body.toString());
    assert.ok(payload.sample_id || payload.samples);
    return Response.json(measured);
  });
  for (const body of [{ sample_id: 'synth-regular' }, { fs: 250, samples: [0, 1, 0] }]) {
    const response = await app.post('/analyze-signal', body);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), measured);
  }
});

test('legacy JSON image uploads are converted to multipart for digitization, never GPT', async t => {
  const app = await startServer(t, async (url, options) => {
    assert.equal(String(url), 'http://dsp.example:8000/analyze');
    assert.ok(options.body instanceof FormData);
    assert.equal(options.body.get('pixels_per_mm'), '8');
    assert.equal(options.body.get('image').type, 'image/png');
    assert.equal(Buffer.from(await options.body.get('image').arrayBuffer()).subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
    return Response.json(measured);
  });
  const response = await app.post('/api/analyze', { image, pixels_per_mm: 8 });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).measurements.hr_mean_bpm, 72);
});

test('multipart uploads preserve their body and calibration fields for the DSP API', async t => {
  const app = await startServer(t, async (url, options) => {
    assert.equal(String(url), 'http://dsp.example:8000/analyze');
    assert.match(options.headers['Content-Type'], /multipart\/form-data; boundary=/);
    const decoded = await new Response(options.body, { headers: options.headers }).formData();
    assert.equal(decoded.get('gain'), '10');
    return Response.json(measured);
  });
  const form = new FormData();
  form.set('image', new Blob([Buffer.from(image.split(',')[1], 'base64')], { type: 'image/png' }), 'strip.png');
  form.set('gain', '10');
  const response = await fetch(app.url + '/analyze', { method: 'POST', body: form });
  assert.equal(response.status, 200);
});

test('invalid legacy uploads fail before contacting DSP', async t => {
  const app = await startServer(t, () => assert.fail('Invalid upload reached DSP.'));
  for (const body of [{}, null, { image: 'hello' }, { image: 'data:image/png;base64,aGVsbG8=' }, '{broken']) {
    assert.equal((await app.post('/api/analyze', body)).status, 400);
  }
});

test('oversized uploads retain a useful 413 response', async t => {
  const app = await startServer(t, () => assert.fail('Oversized upload reached DSP.'));
  const response = await app.post('/api/analyze', { image: 'data:image/png;base64,' + 'A'.repeat(14 * 1024 * 1024) });
  assert.equal(response.status, 413);
  assert.match((await response.json()).error, /too large/);
});

test('method, origin and content-type boundaries are enforced', async t => {
  const app = await startServer(t, () => assert.fail('Invalid request reached DSP.'));
  assert.equal((await fetch(app.url + '/analyze-signal')).status, 405);
  assert.equal((await app.post('/api/analyze', { image }, { Origin: 'https://another-site.example' })).status, 403);
  assert.equal((await app.post('/analyze-signal', {}, { 'Content-Type': 'text/plain' })).status, 415);
  assert.equal((await app.post('/analyze', {}, { 'Content-Type': 'text/plain' })).status, 415);
});

test('quality errors and null explanations are preserved without requiring an API key', async t => {
  const qualityResult = { ...measured, status: 'insufficient_quality', findings: [], explanation: null,
    quality: { status: 'insufficient_quality', reasons: ['Only two beats detected.'] } };
  const app = await startServer(t, async () => Response.json(qualityResult));
  assert.deepEqual(await (await app.post('/analyze-signal', { sample_id: 'synth-regular' })).json(), qualityResult);
});

test('an unavailable backend tells the user how to start DSP', async t => {
  const app = await startServer(t, async () => { throw new TypeError('Connection failed'); });
  const response = await app.post('/analyze-signal', { sample_id: 'synth-regular' });
  assert.equal(response.status, 503);
  assert.match((await response.json()).error, /FastAPI/);
});
