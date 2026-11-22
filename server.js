import { createServer } from 'node:http';
import { pipeline } from 'node:stream/promises';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

import { analysisTimeoutMs, maxBodySize, securityHeaders, validateImage } from './lib/analyze.js';

const measuredRoutes = {
  '/health': ['GET', '/health'], '/api/health': ['GET', '/health'],
  '/samples': ['GET', '/samples'], '/api/samples': ['GET', '/samples'],
  '/analyze-signal': ['POST', '/analyze-signal'], '/api/analyze-signal': ['POST', '/analyze-signal'],
  '/analyze': ['POST', '/analyze'], '/api/analyze': ['POST', '/analyze'],
};

const publicFiles = {
  '/': ['index.html', 'text/html; charset=utf-8'],
  '/index.html': ['index.html', 'text/html; charset=utf-8'],
  '/style.css': ['style.css', 'text/css; charset=utf-8'],
  '/app.js': ['app.js', 'text/javascript; charset=utf-8'],
};

function sendJson(res, status, body) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(JSON.stringify(body));
}

async function readBody(req) {
  let size = 0;
  const chunks = [];

  for await (const chunk of req.iterator({ destroyOnReturn: false })) {
    size += chunk.length;
    if (size > maxBodySize) {
      const error = new Error('The image is too large. Choose a file under 10 MB.');
      error.status = 413;
      req.resume();
      throw error;
    }
    chunks.push(chunk);
  }

  return Buffer.concat(chunks);
}

async function readJson(req) {
  const contents = await readBody(req);
  try {
    return JSON.parse(contents.toString('utf8'));
  } catch {
    const error = new Error('The upload could not be read. Choose the image again.');
    error.status = 400;
    throw error;
  }
}

// Inject the DSP fetch for tests; this server never sends images to GPT.
export function createApp({ fetchImpl = fetch, dspUrl = process.env.ECG_API_URL || 'http://127.0.0.1:8765' } = {}) {
  return createServer(async (req, res) => {
    for (const [name, value] of Object.entries(securityHeaders)) res.setHeader(name, value);

    const pathname = new URL(req.url, 'http://localhost').pathname;

    const route = measuredRoutes[pathname];
    if (route) {
      if (req.method !== route[0]) {
        res.setHeader('Allow', route[0]);
        return sendJson(res, 405, { error: `Use ${route[0]} for this endpoint.` });
      }
      if (req.headers.origin && req.headers.origin !== `http://${req.headers.host}` && req.headers.origin !== `https://${req.headers.host}`) {
        return sendJson(res, 403, { error: 'This request must come from the ECG analyzer page.' });
      }
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), analysisTimeoutMs);
      res.on('close', () => controller.abort());

      try {
        let body;
        const headers = {};
        const contentType = req.headers['content-type'] || '';
        if (req.method === 'POST') {
          if (route[1] === '/analyze' && contentType.startsWith('application/json')) {
            // Preserve the old upload contract while routing it through digitization.
            const upload = await readJson(req);
            if (!validateImage(upload?.image)) {
              return sendJson(res, 400, { error: 'Choose a valid PNG, JPG, or WebP image under 10 MB.' });
            }
            const [metadata, base64] = upload.image.split(',');
            const mime = metadata.slice(5).split(';')[0];
            body = new FormData();
            body.set('image', new Blob([Buffer.from(base64, 'base64')], { type: mime }), 'ecg-strip');
            for (const field of ['pixels_per_mm', 'paper_speed', 'gain', 'crop_box', 'explain', 'notch_hz']) {
              if (upload[field] !== undefined) body.set(field, typeof upload[field] === 'object' ? JSON.stringify(upload[field]) : String(upload[field]));
            }
          } else if ((route[1] === '/analyze' && contentType.startsWith('multipart/form-data'))
                     || (route[1] === '/analyze-signal' && contentType.startsWith('application/json'))) {
            body = await readBody(req);
            headers['Content-Type'] = contentType;
          } else {
            return sendJson(res, 415, { error: route[1] === '/analyze'
              ? 'Send the single-lead image as multipart form data.' : 'Send fs and samples or sample_id as JSON.' });
          }
        }
        const response = await fetchImpl(new URL(route[1], dspUrl), {
          method: req.method, headers, body, signal: controller.signal, redirect: 'error',
        });
        res.writeHead(response.status, { 'Content-Type': response.headers.get('content-type') || 'application/json; charset=utf-8',
          'Cache-Control': 'no-store' });
        if (response.body) await pipeline(response.body, res, { signal: controller.signal });
        else res.end();
        return;
      } catch (error) {
        if (res.destroyed) return;
        if (res.headersSent) return res.destroy();
        return sendJson(res, error.status || (controller.signal.aborted ? 504 : 503), {
          error: error.status ? error.message : controller.signal.aborted
            ? 'The analysis took too long. Please try again.'
            : 'Could not reach the ECG DSP service. Start FastAPI on port 8765 or set ECG_API_URL.',
        });
      } finally {
        clearTimeout(timeout);
      }
    }

    const file = publicFiles[pathname];
    if (!file) return sendJson(res, 404, { error: 'Page not found.' });
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      res.setHeader('Allow', 'GET, HEAD');
      return sendJson(res, 405, { error: 'Method not allowed.' });
    }

    try {
      const contents = await readFile(new URL(`./${file[0]}`, import.meta.url));
      res.writeHead(200, { 'Content-Type': file[1], 'Cache-Control': 'no-cache' });
      res.end(req.method === 'HEAD' ? undefined : contents);
    } catch {
      sendJson(res, 500, { error: 'The page could not be loaded.' });
    }
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try { process.loadEnvFile(fileURLToPath(new URL('./.env', import.meta.url))); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const port = Number(process.env.PORT || 3000);
  const server = createApp();
  server.listen(port, '127.0.0.1', () => console.log(`ECG analyzer: http://localhost:${port}`));
  server.on('error', error => {
    console.error(error.code === 'EADDRINUSE' ? `Port ${port} is already in use. Set PORT to another port.` : error.message);
    process.exitCode = 1;
  });
}
