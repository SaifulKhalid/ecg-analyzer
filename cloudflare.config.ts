import { bindings, defineConfig } from 'cf/config';

export default defineConfig({
  worker: {
    name: 'ecg-analyzer',
    entrypoint: './worker.js',
    compatibilityDate: '2026-11-21',
    workersDev: true,
    env: {
      ASSETS: bindings.assets(),
      AGENTROUTER_API_KEY: bindings.secret(),
      AGENTROUTER_API_KEY_2: bindings.secret(),
    },
    assets: {
      runWorkerFirst: true,
      htmlHandling: 'none',
      notFoundHandling: 'none',
    },
    observability: {
      enabled: true,
      traces: { enabled: true, headSamplingRate: 0.01 },
    },
  },
});
