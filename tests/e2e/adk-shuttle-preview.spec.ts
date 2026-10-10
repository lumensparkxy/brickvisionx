import { test, expect, type Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';

const previewURL = process.env.GUIDE2BUILD_SHUTTLE_PREVIEW_URL;
const evidence = 'var/experiments/adk-31134-booklet01-20261010/evidence/browser';
const manifestPath = '/api/v1/sets/31134/guides/booklet-01/release';
const button = (page: Page, name: string) => page.getByRole('button', { name, exact: true });
type Source = { source_sha256: string; page_index: number; bbox: number[] };
type Step = {
  step_id: string; section_id: string; main_step_number: number | null;
  source: Source; action: string; substep_label: string | null;
  introduced_instance_ids: string[]; active_instance_ids: string[];
};

test.describe('opt-in real ADK Shuttle candidate: read-only browser evidence', () => {
  test.skip(!previewURL, 'Set GUIDE2BUILD_SHUTTLE_PREVIEW_URL to enable the isolated real-data preview checks.');

  for (const viewport of [{ name: 'desktop', width: 1440, height: 900 },
    { name: 'phone', width: 390, height: 844 }]) {
    test(`${viewport.name}: source, callouts, navigation, replay, full playback and reload`, async ({ page }) => {
      test.setTimeout(600_000);
      const target = new URL(previewURL!);
      expect(target.protocol).toBe('http:');
      expect(target.hostname).toBe('127.0.0.1');
      expect(target.port).toBe('4176');
      expect(target.pathname).toBe('/');
      expect(target.username + target.password + target.search + target.hash).toBe('');
      const directory = `${evidence}/${viewport.name}`;
      await mkdir(directory, { recursive: true });
      const errors: string[] = [];
      const consoleErrors: string[] = [];
      const consoleWarnings: string[] = [];
      const networkErrors: { url: string; status?: number; failure?: string }[] = [];
      const interruptedReads: { url: string; failure: string }[] = [];
      const unsafeRequests: { url: string; method: string }[] = [];
      const requests: { url: string; method: string }[] = [];
      const checkedSteps: { index: number; step_id: string; source: Source }[] = [];
      const playbackSteps: string[] = [];
      let identity: Record<string, unknown> = {};
      let callout: Record<string, unknown> = {};
      let previewStatusAtStart: Record<string, unknown> | null = null;
      let previewStatusAtEnd: Record<string, unknown> | null = null;
      let completed = false;
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => {
        if (message.type() === 'error') consoleErrors.push(message.text());
        if (message.type() === 'warning') consoleWarnings.push(message.text());
      });
      page.on('response', response => {
        if (response.status() >= 400) networkErrors.push({ url: response.url(), status: response.status() });
      });
      page.on('requestfailed', request => {
        const failure = request.failure()?.errorText ?? 'unknown';
        const record = { url: request.url(), failure };
        // Source images can be cancelled when a seek changes pages; retain these separately.
        if (failure === 'net::ERR_ABORTED') interruptedReads.push(record);
        else networkErrors.push(record);
      });
      await page.route('**/*', async route => {
        const request = route.request();
        if (['data:', 'blob:'].includes(new URL(request.url()).protocol)) {
          await route.continue();
          return;
        }
        const record = { url: request.url(), method: request.method() };
        requests.push(record);
        if (!['GET', 'HEAD'].includes(record.method) || new URL(record.url).origin !== target.origin) {
          unsafeRequests.push(record);
          await route.abort('blockedbyclient');
          return;
        }
        await route.continue();
      });
      const get = async (path: string) => {
        const url = new URL(path, target);
        expect(url.origin).toBe(target.origin);
        const response = await page.request.get(url.href);
        expect(response.ok(), `GET ${url.pathname}: ${response.status()}`).toBe(true);
        return response;
      };
      const screenshot = async (name: string) => page.screenshot({ path: `${directory}/${name}.png`, fullPage: true });
      const selectBooklet = async (navigate = true) => {
        if (navigate) await page.goto(target.href);
        await expect(page).toHaveTitle('Guide2Build 3D');
        await expect(page.getByLabel('Your set number')).toBeEnabled();
        await page.getByLabel('Your set number').selectOption('31134');
        await button(page, 'Find my set').click();
        const details = page.getByLabel('Set details');
        await expect(details).toContainText('31134');
        await expect(details).toContainText('Space Shuttle');
        return details;
      };
      const open = async (navigate = true, prefix = '') => {
        const details = await selectBooklet(navigate);
        const available = details.getByRole('button', { name: /^(Open candidate|Open tutorial)$/ });
        await expect(available).toHaveCount(1);
        await expect(available).toBeEnabled();
        await screenshot(`${prefix}selected-booklet`);
        await available.click();
        await expect(page.locator('.workspace-heading h1')).toContainText('31134');
        await expect(page.locator('.candidate-status')).toContainText(/provisional|candidate|unverified/i);
        await expect(page.locator('.viewport canvas')).toBeVisible({ timeout: 60_000 });
        await expect(page.getByText('Loading individual part geometry…', { exact: true })).toBeHidden({ timeout: 60_000 });
        await expect(button(page, 'Play full build')).toBeEnabled({ timeout: 60_000 });
        await expect(page.locator('vite-error-overlay')).toHaveCount(0);
        await expect(page.locator('.viewport-message.error')).toHaveCount(0);
      };
      try {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        const configuration = await (await get('/api/v1/config')).json();
        expect(configuration).toEqual({ mode: 'preview', source_images: true, requests_enabled: false });
        const status = await (await get('/api/v1/engine-preview?set_number=31134&guide_id=booklet-01')).json();
        previewStatusAtStart = status;
        expect(status.set_number).toBe('31134');
        expect(status.guide_id).toBe('booklet-01');
        identity = { job_id: status.job_id, set_number: status.set_number, guide_id: status.guide_id,
          state: status.state, stage: status.stage, revision: status.revision,
          candidate_available: status.candidate_available, candidate_message: status.candidate_message,
          error: status.error, artifact_kind: status.artifact_kind, execution_policy: status.execution_policy,
          model_calls_used: status.exploration?.model_calls_used,
          software_evidence_only: true, human_review: 'not_run', physical_build: 'not_run' };
        if (status.candidate_available === false) {
          const details = await selectBooklet();
          identity.blocked_selection_text = await details.innerText();
          await page.locator('.booklet-sample-details summary').click();
          const previewDetails = page.getByLabel('Engine candidate preview');
          await expect(previewDetails).toContainText('31134 / booklet-01');
          identity.blocked_preview_text = await previewDetails.innerText();
          await screenshot('blocked-selection');
        }
        expect(status.candidate_available,
          `Real Shuttle candidate unavailable at stage ${status.stage}; see blocked-selection.png and checks.json.`).toBe(true);
        const manifest = await (await get(manifestPath)).json();
        expect(manifest.set_number).toBe('31134');
        expect(manifest.guide_id).toBe('booklet-01');
        expect(manifest.revision).toBe(status.revision);
        expect(manifest.step_index.length).toBeGreaterThan(1);
        const steps: Step[] = [];
        for (const chunk of manifest.chunks) {
          const response = await get(new URL(chunk.path, new URL(manifest.asset_base_url, target)).href);
          const body = await response.body();
          expect(createHash('sha256').update(body).digest('hex')).toBe(chunk.sha256);
          expect(body.length).toBe(chunk.bytes);
          steps.push(...JSON.parse(body.toString('utf8')).steps);
        }
        expect(steps.map(step => step.step_id)).toEqual(manifest.step_index.map((step: Step) => step.step_id));
        identity = { ...identity, revision: manifest.revision, source_sha256: manifest.source_sha256,
          source_coverage: status.source_coverage, step_count: steps.length, instance_count: manifest.instances.length,
          artifact_kind: status.artifact_kind, execution_policy: status.execution_policy,
          model_calls_used: status.exploration?.model_calls_used, final_source_page: steps.at(-1)!.source.page_index,
          software_evidence_only: true, human_review: 'not_run', physical_build: 'not_run' };
        await open();
        const seek = page.getByLabel('Jump to instruction');
        const current = page.locator('.viewport');
        const source = page.locator('.source-crop canvas');
        const showGuide = async () => {
          if (viewport.name === 'phone') await page.getByRole('tab', { name: 'Guide', exact: true }).click();
          await expect(source).toBeVisible();
        };
        const showModel = async () => {
          if (viewport.name === 'phone') await page.getByRole('tab', { name: '3D', exact: true }).click();
          await expect(page.locator('.viewport canvas')).toBeVisible();
        };
        const assertStep = async (index: number) => {
          const step = steps[index];
          await expect(seek).toHaveValue(String(index));
          await expect(current).toHaveAttribute('data-step-id', step.step_id);
          await expect(source).toHaveAttribute('data-panel', JSON.stringify(step.source), { timeout: 30_000 });
          await expect(current).toHaveAttribute('data-animation-state', 'idle', { timeout: 10_000 });
          checkedSteps.push({ index, step_id: step.step_id, source: step.source });
        };
        const jump = async (index: number) => { await seek.selectOption(String(index)); await assertStep(index); };
        await jump(0);
        await showGuide();
        const firstPage = await get(`/api/v1/sources/${steps[0].source.source_sha256}/pages/${steps[0].source.page_index}`);
        expect(firstPage.headers()['content-type']).toContain('image/png');
        await screenshot('early-source');
        await showModel();
        await screenshot('early-model');
        await button(page, 'Next').click(); await assertStep(1);
        await button(page, 'Previous').click(); await assertStep(0);

        const calloutIndex = steps.findIndex((step, index) => step.action === 'build_subassembly'
          && steps.some((other, otherIndex) => otherIndex !== index && other.section_id === step.section_id
            && other.main_step_number === step.main_step_number));
        expect(calloutIndex, 'The selected real Shuttle candidate should expose booklet callout snapshots').toBeGreaterThanOrEqual(0);
        await jump(calloutIndex);
        const calloutStep = steps[calloutIndex];
        const substeps = page.getByRole('navigation', { name: `Step ${calloutStep.main_step_number} substeps`, exact: true });
        await expect(substeps).toBeVisible();
        await expect(page.locator('.model-caption')).toContainText('Build detached subassembly');
        const siblingIndexes = steps.map((step, index) => ({ step, index })).filter(({ step }) =>
          step.section_id === calloutStep.section_id && step.main_step_number === calloutStep.main_step_number);
        const controls = substeps.getByRole('button');
        expect(await controls.count()).toBe(siblingIndexes.length);
        const selectedSibling = siblingIndexes.findIndex(item => item.index === calloutIndex);
        const otherSibling = (selectedSibling + 1) % siblingIndexes.length;
        await controls.nth(otherSibling).click(); await assertStep(siblingIndexes[otherSibling].index);
        await controls.nth(selectedSibling).click(); await assertStep(calloutIndex);
        callout = { index: calloutIndex, main_step_number: calloutStep.main_step_number,
          step_id: calloutStep.step_id, sibling_step_ids: siblingIndexes.map(item => item.step.step_id) };
        await screenshot('callout');
        await button(page, 'Replay').click();
        await expect(current).toHaveAttribute('data-animation-state', 'playing');
        await screenshot('replay-playing');
        await assertStep(calloutIndex);

        for (let index = 0; index < steps.length; index++) await jump(index);
        await showGuide();
        const last = steps.at(-1)!;
        const finalPage = await get(`/api/v1/sources/${last.source.source_sha256}/pages/${last.source.page_index}`);
        expect(finalPage.headers()['content-type']).toContain('image/png');
        await screenshot('final-source');
        await showModel();
        await screenshot('final-model');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await expect(button(page, 'Next')).toBeDisabled();
        await page.locator('summary[aria-label="Source, revision and checks"]').click();
        await expect(page.locator('.provenance-content')).toContainText(manifest.source_sha256);
        await expect(page.locator('.provenance-content')).toContainText('Physical build: not run');
        await screenshot('provenance');
        await page.locator('summary[aria-label="Source, revision and checks"]').click();

        // Desktop uses normal motion; phone also verifies reduced-motion full playback.
        if (viewport.name === 'phone') await page.emulateMedia({ reducedMotion: 'reduce' });
        await button(page, 'Play full build').click();
        await expect(seek).toHaveValue('0');
        await button(page, 'Pause build').click();
        await expect(button(page, 'Resume build')).toBeVisible();
        const pausedIndex = await seek.inputValue();
        await page.waitForTimeout(350);
        await expect(seek).toHaveValue(pausedIndex);
        await screenshot('playback-paused');
        await button(page, 'Resume build').click();
        for (let index = 0; index < steps.length; index++) {
          await expect(seek).toHaveValue(String(index), { timeout: 15_000 });
          await expect(current).toHaveAttribute('data-step-id', steps[index].step_id);
          await expect(source).toHaveAttribute('data-panel', JSON.stringify(steps[index].source), { timeout: 10_000 });
          playbackSteps.push(steps[index].step_id);
        }
        await expect(page.getByText('Playback complete · all instructions shown', { exact: true })).toBeVisible({ timeout: 15_000 });
        expect(playbackSteps).toEqual(steps.map(step => step.step_id));
        await screenshot('playback-complete');
        await page.reload();
        await open(false, 'reload-');
        await assertStep(steps.length - 1);
        await expect(button(page, 'Pause build')).toHaveCount(0);
        await screenshot('reload-resumed-final');
        const finalStatus = await (await get('/api/v1/engine-preview?set_number=31134&guide_id=booklet-01')).json();
        previewStatusAtEnd = finalStatus;
        expect(finalStatus.job_id).toBe(status.job_id);
        expect(finalStatus.candidate_available).toBe(true);
        expect(finalStatus.revision, 'The selected candidate changed during browser verification.').toBe(manifest.revision);
        expect(finalStatus.step_count).toBe(steps.length);
        expect(finalStatus.instance_count).toBe(manifest.instances.length);
        expect(finalStatus.exploration?.model_calls_used,
          'Model usage changed during the read-only browser run.').toBe(status.exploration?.model_calls_used);
        expect(errors).toEqual([]);
        expect(consoleErrors).toEqual([]);
        expect(networkErrors).toEqual([]);
        expect(unsafeRequests).toEqual([]);
        completed = true;
      } finally {
        await writeFile(`${directory}/checks.json`, JSON.stringify({ preview_url: target.href, viewport,
          browser_path: 'Playwright; Browser plugin not available', identity, previewStatusAtStart, previewStatusAtEnd,
          callout, checkedSteps, playbackSteps,
          completed, errors, consoleErrors, consoleWarnings, networkErrors, interruptedReads, unsafeRequests, requests,
          claim: 'Browser software behavior only; source agreement, reconstruction accuracy and physical assembly require separate review.' }, null, 2));
        if (!completed) await screenshot('failure-state').catch(() => {});
      }
    });
  }
});
