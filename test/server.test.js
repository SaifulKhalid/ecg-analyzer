import assert from 'node:assert/strict';
import { once } from 'node:events';
import { test } from 'node:test';
import { createApp } from '../server.js';

const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1sAAAAASUVORK5CYII=';
const report = {
  measurements: [{ label: 'Heart rate', value: '72', unit: 'bpm', note: 'Estimated.' }],
  explanation: ['The visible rhythm appears regular.', 'Image quality limits detailed interpretation.'],
};

async function startServer(t, fetchImpl, apiKey = 'test-key') {
  const server = createApp({ apiKey, fetchImpl });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => new Promise(resolve => {
    server.close(resolve);
    server.closeAllConnections();
  }));
  const url = `http://127.0.0.1:${server.address().port}`;
  return {
    url,
    analyze: (body = { image }, headers = {}) => fetch(`${url}/api/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers },
      body: typeof body === 'string' ? body : JSON.stringify(body),
    }),
  };
}

test('sends the image to the requested provider and returns its analysis', async t => {
  let sent;
  const app = await startServer(t, async (url, options) => {
    sent = { url, options };
    return Response.json({ output: [{ type: 'message', role: 'assistant', content: [{ type: 'output_text', text: JSON.stringify(report) }] }] });
  });

  const response = await app.analyze();
  assert.equal(response.status, 200);
  const data = await response.json();
  assert.deepEqual(data.report, report);
  assert.equal(data.model, 'gpt-5.6-sol');
  assert.equal(data.attempts, 1);
  assert.equal(typeof data.durationMs, 'number');
  assert.equal(sent.url, 'https://agentrouter.org/v1/responses');
  assert.equal(sent.options.headers.Authorization, 'Bearer test-key');
  assert.equal(sent.options.headers['User-Agent'], 'claude-cli/2.1.158 (external, sdk-cli)');
  assert.equal(sent.options.headers['X-App'], 'cli');
  const payload = JSON.parse(sent.options.body);
  assert.equal(payload.model, 'gpt-5.6-sol');
  assert.equal(payload.input[1].content[1].image_url, image);
  assert.equal(payload.input[1].content[1].type, 'input_image');
  assert.equal(payload.store, false);
  assert.equal(payload.stream, false);
  assert.equal(payload.reasoning, undefined);
  assert.equal(payload.text, undefined);
  assert.match(payload.input[0].content, /Return only valid JSON/);
  assert.match(payload.input[0].content, /Do not invent findings/);
});

test('rejects invalid uploads before calling the provider', async t => {
  const app = await startServer(t, () => assert.fail('Invalid images must not reach Agentrouter.'));
  for (const body of [{}, null, { image: 'hello' }, { image: 'data:image/png;base64,aGVsbG8=' }, '{broken']) {
    const response = await app.analyze(body);
    assert.equal(response.status, 400);
    assert.equal(typeof (await response.json()).error, 'string');
  }
});

test('rejects oversized uploads with a useful response', async t => {
  const app = await startServer(t, () => assert.fail('Oversized images must not reach Agentrouter.'));
  const response = await app.analyze({ image: 'data:image/png;base64,' + 'A'.repeat(14 * 1024 * 1024) });
  assert.equal(response.status, 413);
  assert.match((await response.json()).error, /too large/);
});

test('returns provider rejection details without leaking credentials', async t => {
  const app = await startServer(t, async () => Response.json({
    error: { message: 'unauthorized client detected test-key sk-secret' },
  }, { status: 401 }));
  const response = await app.analyze();
  assert.equal(response.status, 502);
  const data = await response.json();
  assert.match(data.error, /unauthorized client detected/);
  assert.doesNotMatch(data.error, /test-key|sk-secret/);
});

test('handles rate limits, network failures, empty and non-JSON responses', async t => {
  const cases = [
    [async () => Response.json({}, { status: 429 }), 429, /limit/],
    [async () => { throw new TypeError('Connection failed'); }, 502, /connect/],
    [async () => Response.json({ output: [] }), 502, /no analysis/],
    [async () => new Response('<html>Bad gateway</html>', { status: 502 }), 502, /could not analyze/],
  ];
  for (const [fetchImpl, expectedStatus, message] of cases) {
    const app = await startServer(t, fetchImpl);
    const response = await app.analyze();
    assert.equal(response.status, expectedStatus);
    assert.match((await response.json()).error, message);
  }
});

test('accepts text block responses', async t => {
  const text = JSON.stringify(report);
  const app = await startServer(t, async () => Response.json({ output: [{ type: 'message', role: 'assistant', content: [
    { type: 'output_text', text: text.slice(0, 1) },
    { type: 'output_text', text: text.slice(1) },
  ] }] }));
  const response = await app.analyze();
  assert.deepEqual((await response.json()).report, report);
});

test('serves only public files and enforces request boundaries', async t => {
  const app = await startServer(t, () => assert.fail('These requests must not reach Agentrouter.'));
  const page = await fetch(app.url);
  assert.equal(page.status, 200);
  assert.match(await page.text(), /ECG Analyzer/);
  assert.match(page.headers.get('content-security-policy'), /frame-ancestors 'none'/);
  for (const path of ['/config.local.js', '/.secrets.local.json', '/.dev.vars', '/server.js', '/package.json', '/..%2fconfig.local.js']) {
    assert.equal((await fetch(app.url + path)).status, 404);
  }
  assert.equal((await fetch(app.url + '/api/analyze')).status, 405);
  assert.equal((await app.analyze({ image }, { Origin: 'https://another-site.example' })).status, 403);
  assert.equal((await app.analyze({ image }, { 'Content-Type': 'text/plain' })).status, 415);
});

test('reports missing server configuration', async t => {
  const app = await startServer(t, () => assert.fail('Missing keys must not reach Agentrouter.'), '');
  const response = await app.analyze();
  assert.equal(response.status, 503);
  assert.match((await response.json()).error, /API key/);
});
