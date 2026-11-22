import assert from 'node:assert/strict';
import { test } from 'node:test';
import { analyzeImage } from '../lib/analyze.js';

const image = 'test-image';
const report = {
  measurements: [
    { label: 'Heart rate', value: '60–70', unit: 'bpm', note: 'Estimated from the visible trace.' },
    { label: 'QTc', value: null, unit: 'ms', note: 'Calibration not readable.' },
  ],
  explanation: ['The rhythm appears regular. The image limits interval measurement.'],
};
const success = () => Response.json({ status: 'completed', output: [
  { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: JSON.stringify(report) }] },
] });
const attempt = options => [JSON.parse(options.body).model, options.headers.Authorization];

test('a successful primary report preserves uncertain numerical values and needs one call', async () => {
  const attempts = [];
  const response = await analyzeImage(image, ['first-key', 'second-key'], async (url, options) => {
    attempts.push(attempt(options));
    return success();
  });
  assert.equal(response.status, 200);
  assert.deepEqual((await response.json()).report, report);
  assert.deepEqual(attempts, [['gpt-5.6-sol', 'Bearer first-key']]);
});

test('primary model failures immediately use gpt-6.1-sol with the second key', async () => {
  for (const firstResponse of [
    () => Response.json({ error: { message: 'Unavailable model' } }, { status: 404 }),
    () => Response.json({ status: 'incomplete' }),
    () => Response.json({ output: [] }),
    () => { throw new TypeError('Offline'); },
  ]) {
    const attempts = [];
    const response = await analyzeImage(image, ['first-key', 'second-key'], async (url, options) => {
      attempts.push(attempt(options));
      return attempts.length === 1 ? firstResponse() : success();
    });
    assert.equal(response.status, 200);
    const data = await response.json();
    assert.equal(data.model, 'gpt-6.1-sol');
    assert.equal(data.attempts, 2);
    assert.deepEqual(attempts, [['gpt-5.6-sol', 'Bearer first-key'], ['gpt-6.1-sol', 'Bearer second-key']]);
  }
});

test('authorization errors and rate limits try the other key and never reuse the blocked key', async () => {
  for (const status of [401, 403, 429]) {
    const attempts = [];
    const response = await analyzeImage(image, ['first-key', 'second-key'], async (url, options) => {
      attempts.push(attempt(options));
      if (attempts.length === 1) return Response.json({}, { status });
      if (attempts.length === 2) return Response.json({}, { status: 503 });
      return success();
    });
    assert.equal(response.status, 200);
    assert.deepEqual(attempts, [
      ['gpt-5.6-sol', 'Bearer first-key'],
      ['gpt-5.6-sol', 'Bearer second-key'],
      ['gpt-6.1-sol', 'Bearer second-key'],
    ]);
  }
});

test('a stalled primary request is aborted before the fallback starts', async () => {
  const attempts = [];
  let aborted = false;
  const response = await analyzeImage(image, ['first-key', 'second-key'], async (url, options) => {
    attempts.push(attempt(options));
    if (attempts.length !== 1) {
      assert.equal(aborted, true);
      return success();
    }
    return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => {
      aborted = true;
      reject(options.signal.reason);
    }, { once: true }));
  }, undefined, { attemptTimeoutMs: 10 });
  assert.equal(response.status, 200);
  assert.deepEqual(attempts, [['gpt-5.6-sol', 'Bearer first-key'], ['gpt-6.1-sol', 'Bearer second-key']]);
});

test('parent cancellation aborts the active request and prevents another attempt', async () => {
  const controller = new AbortController();
  let calls = 0;
  const pending = analyzeImage(image, ['first-key', 'second-key'], async (url, options) => {
    calls += 1;
    return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true }));
  }, controller.signal);
  controller.abort();
  await assert.rejects(pending, { name: 'AbortError' });
  assert.equal(calls, 1);
});

test('invalid reports are rejected and provider errors redact both configured keys', async () => {
  const invalid = await analyzeImage(image, 'first-key', async () => Response.json({ output: [
    { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: '{"measurements":[],"explanation":[]}' }] },
  ] }));
  assert.equal(invalid.status, 502);
  assert.match((await invalid.json()).error, /invalid report/);
  const failure = await analyzeImage(image, ['first-key', 'second-key'], async () => Response.json({
    error: { message: 'Rejected first-key second-key sk-secret' },
  }, { status: 401 }));
  assert.equal(failure.status, 502);
  assert.doesNotMatch((await failure.json()).error, /first-key|second-key|sk-secret/);
});

test('refusals stop without retrying and duplicate keys produce only one attempt per model', async () => {
  let calls = 0;
  const refusal = await analyzeImage(image, ['first-key', 'second-key'], async () => {
    calls += 1;
    return Response.json({ output: [{ type: 'message', role: 'assistant', content: [{ type: 'refusal', refusal: 'Declined.' }] }] });
  });
  assert.equal(refusal.status, 502);
  assert.equal(calls, 1);
  calls = 0;
  await analyzeImage(image, ['first-key', 'first-key'], async () => {
    calls += 1;
    return Response.json({}, { status: 503 });
  });
  assert.equal(calls, 2);
});

test('provider content blocks stop without retrying another key or model', async () => {
  let calls = 0;
  const response = await analyzeImage(image, ['first-key', 'second-key'], async () => {
    calls += 1;
    return Response.json({ error: { message: 'content-blocked' } }, { status: 400 });
  });
  assert.equal(response.status, 502);
  assert.equal(calls, 1);
});
