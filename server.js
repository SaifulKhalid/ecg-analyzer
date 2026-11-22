import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

import { analyzeImage, analysisTimeoutMs, maxBodySize, securityHeaders, validateImage } from './lib/analyze.js';

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

async function readJson(req) {
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

  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    const error = new Error('The upload could not be read. Choose the image again.');
    error.status = 400;
    throw error;
  }
}

// The optional arguments let the API be checked without spending credits.
export function createApp({ apiKey, apiKey2, fetchImpl = fetch } = {}) {
  return createServer(async (req, res) => {
    for (const [name, value] of Object.entries(securityHeaders)) res.setHeader(name, value);

    const pathname = new URL(req.url, 'http://localhost').pathname;

    if (pathname === '/api/analyze') {
      if (req.method !== 'POST') {
        res.setHeader('Allow', 'POST');
        return sendJson(res, 405, { error: 'Use POST to analyze an image.' });
      }
      if (req.headers.origin && req.headers.origin !== `http://${req.headers.host}` && req.headers.origin !== `https://${req.headers.host}`) {
        return sendJson(res, 403, { error: 'This request must come from the ECG analyzer page.' });
      }
      if (!req.headers['content-type']?.startsWith('application/json')) {
        return sendJson(res, 415, { error: 'The image must be sent as JSON.' });
      }
      if (!apiKey && !apiKey2) return sendJson(res, 503, { error: 'Set the Agentrouter API key on the server first.' });

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), analysisTimeoutMs);
      res.on('close', () => controller.abort());

      try {
        const body = await readJson(req);
        if (!validateImage(body?.image)) {
          return sendJson(res, 400, { error: 'Choose a valid PNG, JPG, or WebP image under 10 MB.' });
        }

        const response = await analyzeImage(body.image, [apiKey, apiKey2], fetchImpl, controller.signal);
        res.writeHead(response.status, Object.fromEntries(response.headers));
        res.end(await response.text());
        return;
      } catch (error) {
        if (res.destroyed) return;
        return sendJson(res, error.status || (controller.signal.aborted ? 504 : 502), {
          error: error.status ? error.message : controller.signal.aborted
            ? 'The analysis took too long. Please try again.'
            : 'Could not connect to Agentrouter. Please try again.',
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
  const localConfig = await import('./config.local.js').catch(error => {
    if (error.code === 'ERR_MODULE_NOT_FOUND') return {};
    throw error;
  });
  const apiKey = process.env.AGENTROUTER_API_KEY || localConfig.apiKey;
  const apiKey2 = process.env.AGENTROUTER_API_KEY_2 || localConfig.apiKey2;
  const port = Number(process.env.PORT || 3000);
  const server = createApp({ apiKey, apiKey2 });
  server.listen(port, '127.0.0.1', () => console.log(`ECG analyzer: http://localhost:${port}`));
  server.on('error', error => {
    console.error(error.code === 'EADDRINUSE' ? `Port ${port} is already in use. Set PORT to another port.` : error.message);
    process.exitCode = 1;
  });
}
