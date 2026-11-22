import { analysisTimeoutMs, jsonResponse, maxBodySize, securityHeaders, validateImage } from './lib/analyze.js';

const measuredRoutes = {
  '/health': ['GET', '/health'], '/api/health': ['GET', '/health'],
  '/samples': ['GET', '/samples'], '/api/samples': ['GET', '/samples'],
  '/analyze-signal': ['POST', '/analyze-signal'], '/api/analyze-signal': ['POST', '/analyze-signal'],
  '/analyze': ['POST', '/analyze'], '/api/analyze': ['POST', '/analyze'],
};

async function readBody(request) {
  if (Number(request.headers.get('content-length')) > maxBodySize) {
    throw Object.assign(new Error('The upload is too large. Choose an image under 10 MB.'), { status: 413 });
  }
  if (!request.body) throw Object.assign(new Error('Provide an image or signal.'), { status: 400 });
  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maxBodySize) {
        await reader.cancel();
        throw Object.assign(new Error('The upload is too large. Choose an image under 10 MB.'), { status: 413 });
      }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
  return body;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const route = measuredRoutes[url.pathname];
    if (!route) {
      if (request.method !== 'GET' && request.method !== 'HEAD') {
        return jsonResponse(405, { error: 'Method not allowed.' }, { Allow: 'GET, HEAD' });
      }
      const assetRequest = url.pathname === '/' ? new Request(new URL('/index.html', url), request) : request;
      const asset = await env.ASSETS.fetch(assetRequest);
      const response = new Response(asset.body, asset);
      for (const [name, value] of Object.entries(securityHeaders)) response.headers.set(name, value);
      return response;
    }
    if (request.method !== route[0]) {
      return jsonResponse(405, { error: `Use ${route[0]} for this endpoint.` }, { Allow: route[0] });
    }
    const origin = request.headers.get('origin');
    if (origin && origin !== url.origin) return jsonResponse(403, { error: 'Use the ECG analyzer page.' });
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), analysisTimeoutMs);
    const cancel = () => controller.abort();
    request.signal.addEventListener('abort', cancel, { once: true });
    if (request.signal.aborted) cancel();
    const started = performance.now();
    try {
      let body;
      const headers = {};
      const contentType = request.headers.get('content-type') || '';
      if (request.method === 'POST') {
        if (route[1] === '/analyze' && contentType.startsWith('application/json')) {
          const bytes = await readBody(request);
          let upload;
          try { upload = JSON.parse(new TextDecoder().decode(bytes)); }
          catch { return jsonResponse(400, { error: 'The image upload could not be read.' }); }
          if (!validateImage(upload?.image)) return jsonResponse(400, { error: 'Choose a valid PNG, JPG, or WebP image under 10 MB.' });
          const [metadata, encoded] = upload.image.split(',');
          const mime = metadata.slice(5).split(';')[0];
          const imageBytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
          body = new FormData();
          body.set('image', new Blob([imageBytes], { type: mime }), 'ecg-strip');
          for (const field of ['pixels_per_mm', 'paper_speed', 'gain', 'crop_box', 'explain', 'notch_hz', 'allow_provider_default_temperature']) {
            if (upload[field] !== undefined) body.set(field, typeof upload[field] === 'object' ? JSON.stringify(upload[field]) : String(upload[field]));
          }
        } else if ((route[1] === '/analyze' && contentType.startsWith('multipart/form-data'))
                   || (route[1] === '/analyze-signal' && contentType.startsWith('application/json'))) {
          body = await readBody(request);
          headers['Content-Type'] = contentType;
        } else {
          return jsonResponse(415, { error: route[1] === '/analyze'
            ? 'Send the single-lead image as multipart form data.' : 'Send the signal as JSON.' });
        }
      }
      if (!env.ECG_API_URL) return jsonResponse(503, { error: 'Configure ECG_API_URL with a reachable FastAPI DSP service.' });
      const response = await fetch(new URL(route[1], env.ECG_API_URL), {
        method: request.method, headers, body, signal: controller.signal, redirect: 'manual',
      });
      if (response.status >= 300 && response.status < 400) {
        await response.body?.cancel();
        throw new Error('The configured ECG DSP service returned an unexpected redirect.');
      }
      console.log(JSON.stringify({ event: 'ecg_measured_proxy', path: route[1], status: response.status,
        durationMs: Math.round(performance.now() - started) }));
      return new Response(response.body, { status: response.status,
        headers: { 'Content-Type': response.headers.get('content-type') || 'application/json',
          'Cache-Control': 'no-store', ...securityHeaders } });
    } catch (error) {
      console.error(JSON.stringify({ event: 'ecg_measured_proxy_error', path: route[1],
        name: error.name, message: error.message, durationMs: Math.round(performance.now() - started) }));
      return jsonResponse(error.status || (controller.signal.aborted ? 504 : 503), {
        error: error.status ? error.message : controller.signal.aborted
          ? 'The measured analysis took too long. Please try again.'
          : 'Could not reach the configured ECG DSP service.',
      });
    } finally {
      clearTimeout(timeout);
      request.signal.removeEventListener('abort', cancel);
    }
  },
};
