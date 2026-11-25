import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  server: {
    fs: { allow: [fileURLToPath(new URL('..', import.meta.url))] },
    proxy: { '/api': process.env.CITYRESCUE_API_URL ?? 'http://127.0.0.1:8002' },
  },
});
