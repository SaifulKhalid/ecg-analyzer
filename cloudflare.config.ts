import { bindings, defineConfig } from 'cf/config';

export default defineConfig({
  worker: {
    name: 'ecg-analyzer',
    entrypoint: './worker.js',
    compatibilityDate: '2026-11-21',
    workersDev: true,
    env: {
      ASSETS: bindings.assets(),
      // Provider credentials live in the backend's production environment.
      ECG_API_URL: bindings.text(process.env.ECG_API_URL || 'https://ecg-analyzer-dsp-khalid-saifullahs-projects-239e324e.vercel.app'),
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
