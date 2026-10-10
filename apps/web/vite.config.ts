import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
// Override when port 8000 is taken locally, e.g. GUIDE2BUILD_API_ORIGIN=http://127.0.0.1:8123.
const env = (globalThis as {process?: {env: Record<string, string | undefined>}}).process?.env ?? {};
const api = env.GUIDE2BUILD_API_ORIGIN ?? 'http://127.0.0.1:8000';
export default defineConfig({
  plugins: [react()],
  server: { proxy: {
    '/api': api,
    '/assets-local': api,
  } },
});
