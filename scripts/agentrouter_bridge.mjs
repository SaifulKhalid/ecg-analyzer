// Private stdin/stdout bridge: Python reuses the existing JS Responses API client.
// Only the offline comparison command uses kind=baseline; no HTTP route exposes it.
import { explainMeasurements, estimateImageBaseline } from '../lib/analyze.js';
import { loadAgentRouterConfig } from '../lib/agentrouter-config.js';

try {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  const config = await loadAgentRouterConfig();
  const timeoutMs = Math.min(120_000, Math.max(1000, Number(request.timeout_seconds || 75) * 1000));
  const signal = AbortSignal.timeout(timeoutMs);
  const options = { primaryModel: config.primaryModel, fallbackModel: config.fallbackModel,
    temperature: request.temperature ?? 0.2,
    attemptTimeoutMs: Math.min(timeoutMs, Number(request.attempt_timeout_seconds || 35) * 1000) };
  const response = request.kind === 'baseline'
    ? await estimateImageBaseline(request.image, config.apiKeys, fetch, signal, options)
    : request.kind === 'explain'
      ? await explainMeasurements(request.payload, config.apiKeys, fetch, signal, options)
      : Response.json({ error: 'Unknown bridge operation.' }, { status: 400 });
  process.stdout.write(JSON.stringify({ status_code: response.status, ...await response.json() }));
} catch {
  // No credential / process details on stdout or stderr.
  process.stdout.write(JSON.stringify({ status_code: 502, error: 'AgentRouter bridge failed or timed out.' }));
}
