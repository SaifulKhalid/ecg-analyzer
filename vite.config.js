import { defineConfig } from 'vite';
import { cloudflare } from '@cloudflare/vite-plugin';

export default defineConfig({
  publicDir: false,
  server: {
    fs: {
      deny: ['.env', '.env.*', '*.{crt,pem}', '**/.git/**', '**/config.local.js', '**/.secrets.local.json', '**/.dev.vars*'],
    },
  },
  plugins: [cloudflare()],
});
