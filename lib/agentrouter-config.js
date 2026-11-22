import { fileURLToPath } from 'node:url';

// Server / command-line only. Reuse the original credential names and local fallback.
export async function loadAgentRouterConfig() {
  try { process.loadEnvFile(fileURLToPath(new URL('../.env', import.meta.url))); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const local = await import('../config.local.js').catch(error => {
    if (error.code === 'ERR_MODULE_NOT_FOUND') return {};
    throw error;
  });
  return {
    apiKeys: [process.env.AGENTROUTER_API_KEY || local.apiKey, process.env.AGENTROUTER_API_KEY_2 || local.apiKey2],
    primaryModel: process.env.AGENTROUTER_MODEL || 'gpt-5.6-sol',
    fallbackModel: process.env.AGENTROUTER_FALLBACK_MODEL || 'gpt-6.1-sol',
  };
}
