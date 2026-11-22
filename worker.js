import { analyzeImage, analysisTimeoutMs, jsonResponse, maxBodySize, securityHeaders, validateImage } from './lib/analyze.js';

async function readJson(request) {
  if (Number(request.headers.get('content-length')) > maxBodySize) {
    throw Object.assign(new Error('The image is too large. Choose a file under 10 MB.'), { status: 413 });
  }
  if (!request.body) throw Object.assign(new Error('Choose an image first.'), { status: 400 });

  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maxBodySize) {
        await reader.cancel();
        throw Object.assign(new Error('The image is too large. Choose a file under 10 MB.'), { status: 413 });
      }
      chunks.push(decoder.decode(value, { stream: true }));
    }
    chunks.push(decoder.decode());
  } finally {
    reader.releaseLock();
  }
  try {
    return JSON.parse(chunks.join(''));
  } catch {
    throw Object.assign(new Error('The upload could not be read. Choose the image again.'), { status: 400 });
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== '/api/analyze') {
      if (request.method !== 'GET' && request.method !== 'HEAD') {
        return jsonResponse(405, { error: 'Method not allowed.' }, { Allow: 'GET, HEAD' });
      }
      const assetRequest = url.pathname === '/'
        ? new Request(new URL('/index.html', url), request)
        : request;
      const asset = await env.ASSETS.fetch(assetRequest);
      const response = new Response(asset.body, asset);
      for (const [name, value] of Object.entries(securityHeaders)) response.headers.set(name, value);
      return response;
    }

    if (request.method !== 'POST') {
      return jsonResponse(405, { error: 'Use POST to analyze an image.' }, { Allow: 'POST' });
    }
    const origin = request.headers.get('origin');
    if (origin && origin !== url.origin) {
      return jsonResponse(403, { error: 'This request must come from the ECG analyzer page.' });
    }
    if (!request.headers.get('content-type')?.startsWith('application/json')) {
      return jsonResponse(415, { error: 'The image must be sent as JSON.' });
    }

    const apiKeys = [env.AGENTROUTER_API_KEY, env.AGENTROUTER_API_KEY_2].filter(Boolean);
    if (!apiKeys.length) return jsonResponse(503, { error: 'Set the Agentrouter API key on the server first.' });
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), analysisTimeoutMs);
    const cancel = () => controller.abort();
    request.signal.addEventListener('abort', cancel, { once: true });
    if (request.signal.aborted) cancel();
    const started = performance.now();

    try {
      const body = await readJson(request);
      if (!validateImage(body?.image)) {
        return jsonResponse(400, { error: 'Choose a valid PNG, JPG, or WebP image under 10 MB.' });
      }
      const response = await analyzeImage(body.image, apiKeys, fetch, controller.signal);
      console.log(JSON.stringify({ event: 'ecg_analysis', status: response.status, durationMs: Math.round(performance.now() - started) }));
      return response;
    } catch (error) {
      console.error(JSON.stringify({ event: 'ecg_analysis_failed', status: error.status || 502, timeout: controller.signal.aborted }));
      return jsonResponse(error.status || (controller.signal.aborted ? 504 : 502), {
        error: error.status ? error.message : controller.signal.aborted
          ? 'The analysis took too long. Please try again.'
          : 'Could not connect to Agentrouter. Please try again.',
      });
    } finally {
      clearTimeout(timeout);
      request.signal.removeEventListener('abort', cancel);
    }
  },
};
