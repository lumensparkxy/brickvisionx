import { defineConfig } from '@playwright/test';
const softwareSpecs = [
  '**/booklet-preparation.spec.ts', '**/chunked-playback.spec.ts', '**/public-portal.spec.ts',
  '**/set-readiness-audit.spec.ts', '**/starter.spec.ts', '**/viewer.spec.ts', '**/public-alpha.spec.ts',
  '**/exploration-preview.spec.ts',
];
export default defineConfig({
  testDir: './tests/e2e',
  // Pixel and native-focus checks share the host GPU; keep their execution isolated.
  workers: 1,
  projects: [
    { name: 'software', testMatch: softwareSpecs },
    // Still part of the default local suite; requires the recorded official-source cache.
    { name: 'reference', testIgnore: softwareSpecs },
  ],
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure' },
  webServer: [
    { command: 'PYTHONPATH=apps/api/src .venv/bin/python -m uvicorn guide2build.main:app --host 127.0.0.1 --port 8000', url: 'http://127.0.0.1:8000/api/v1/health', reuseExistingServer: !process.env.CI },
    { command: 'npm run dev', url: 'http://127.0.0.1:5173', reuseExistingServer: !process.env.CI },
  ],
});
