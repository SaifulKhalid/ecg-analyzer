import assert from 'node:assert/strict';
import { test } from 'node:test';
import { explainMeasurements, estimateImageBaseline, explanationSections } from '../lib/analyze.js';

const payload = { measurements: { hr_mean_bpm: 72, sdnn_ms: 8 }, quality: { status: 'ok', beat_count: 14 },
  findings: [{ label: 'Suggestive of regular RR timing', confidence: 0.75, evidence: ['Measured HR 72 bpm.'] }],
  warnings: [], plots: { r_peaks: 'data:image/png;base64,not-sent' }, image: 'never sent' };
const explanation = Object.fromEntries(explanationSections.map(section => [section, 'Possible measured timing; clinician review advised.']));
const provider = report => Response.json({ output: [{ type: 'message', role: 'assistant',
  content: [{ type: 'output_text', text: JSON.stringify(report) }] }] });

test('measured explanation sends text JSON only at temperature 0.2 using original credentials and headers', async () => {
  const response = await explainMeasurements(payload, 'secret-key', async (url, options) => {
    assert.equal(url, 'https://agentrouter.org/v1/responses');
    assert.equal(options.headers.Authorization, 'Bearer secret-key');
    assert.equal(options.headers['X-App'], 'cli');
    const body = JSON.parse(options.body);
    assert.equal(body.temperature, 0.2);
    assert.equal(body.store, false);
    assert.equal(typeof body.input[1].content, 'string');
    assert.doesNotMatch(options.body, /input_image|image_url|data:image|not-sent/);
    const supplied = JSON.parse(body.input[1].content);
    assert.equal(supplied.measurements.hr_mean_bpm, 72);
    assert.deepEqual(Object.keys(supplied).sort(), ['findings', 'measurements', 'quality', 'warnings']);
    assert.match(body.input[0].content, /Never infer or invent a number/);
    assert.match(body.input[0].content, /never a diagnosis/);
    return provider({ explanation });
  });
  assert.equal(response.status, 200);
  assert.deepEqual((await response.json()).report.explanation, explanation);
});

test('quality failures and embedded images are rejected before contacting GPT', async () => {
  const noCall = () => assert.fail('Invalid report reached GPT.');
  assert.equal((await explainMeasurements({ ...payload, quality: { status: 'insufficient_quality' } }, 'key', noCall)).status, 400);
  assert.equal((await explainMeasurements({ ...payload, measurements: { note: 'data:image/png;base64,forbidden' } }, 'key', noCall)).status, 400);
});

test('an explanation must contain all five requested sections', async () => {
  const response = await explainMeasurements(payload, 'key', async () => provider({ explanation: { Summary: 'Partial.' } }));
  assert.equal(response.status, 502);
});

test('strict policy never removes temperature after an unsupported-parameter response', async () => {
  const temperatures = [];
  const response = await explainMeasurements(payload, 'key', async (url, options) => {
    temperatures.push(JSON.parse(options.body).temperature);
    return Response.json({ error: { code: 'unsupported_parameter', param: 'temperature',
      message: "Unsupported parameter: 'temperature' is not supported with this model." } }, { status: 400 });
  });
  assert.equal(response.status, 502);
  assert.deepEqual(temperatures, [0.2, 0.2]);
});

test('explicit compatibility retries the identical measured JSON once and reports provider default', async () => {
  const requests = [];
  const response = await explainMeasurements(payload, 'key', async (url, options) => {
    const body = JSON.parse(options.body);
    requests.push(body);
    if (requests.length === 1) return Response.json({ error: { code: 'unsupported_parameter', param: 'temperature',
      message: "Unsupported parameter: 'temperature' is not supported with this model." } }, { status: 400 });
    return provider({ explanation });
  }, undefined, { allowProviderDefaultTemperature: true });
  assert.equal(response.status, 200);
  assert.equal(requests.length, 2);
  assert.equal(requests[0].temperature, 0.2);
  assert.equal(requests[1].temperature, undefined);
  assert.deepEqual(requests[0].input, requests[1].input);
  assert.doesNotMatch(JSON.stringify(requests), /input_image|image_url|data:image/);
  const result = await response.json();
  assert.equal(result.attempts, 2);
  assert.equal(result.explanation_settings.requested_temperature, 0.2);
  assert.equal(result.explanation_settings.effective_temperature, 'provider_default');
  assert.equal(result.explanation_settings.used_provider_default, true);
});

test('compatibility does not remove temperature for unrelated provider errors', async () => {
  const requests = [];
  const response = await explainMeasurements(payload, 'key', async (url, options) => {
    requests.push(JSON.parse(options.body));
    return Response.json({ error: { message: 'Service temporarily unavailable.' } }, { status: 503 });
  }, undefined, { allowProviderDefaultTemperature: true });
  assert.equal(response.status, 502);
  assert.equal(requests.length, 2);
  assert.ok(requests.every(body => body.temperature === 0.2));
});

test('benchmark image-only mode is explicit and has a compact HR/rhythm contract', async () => {
  const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1sAAAAASUVORK5CYII=';
  const response = await estimateImageBaseline(image, 'key', async (url, options) => {
    const body = JSON.parse(options.body);
    assert.equal(body.input[1].content[1].image_url, image);
    assert.equal(body.temperature, undefined);
    assert.match(body.input[0].content, /provided.*\n.*image only/);
    assert.doesNotMatch(body.input[1].content[0].text, /72|ground.truth/);
    return provider({ heart_rate_bpm: 72, rhythm: 'regular' });
  });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).report.heart_rate_bpm, 72);
});
