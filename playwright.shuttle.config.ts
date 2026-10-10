import { defineConfig } from '@playwright/test';

const evidence = 'var/experiments/adk-31134-booklet01-20261010/evidence/browser';

// This opt-in suite owns no servers and cannot start or replace the red-plane app.
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/adk-shuttle-preview.spec.ts',
  workers: 1,
  retries: 0,
  outputDir: `${evidence}/test-results`,
  reporter: [['list'], ['json', { outputFile: `${evidence}/playwright-results.json` }]],
  use: {
    baseURL: process.env.GUIDE2BUILD_SHUTTLE_PREVIEW_URL ?? 'http://127.0.0.1:4176',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});
