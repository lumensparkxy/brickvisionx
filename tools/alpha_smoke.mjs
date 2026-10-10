// Verify exact prepared releases through the public UI. Never approves or publishes.
import {chromium, expect} from '@playwright/test';
import {mkdir, readFile, writeFile} from 'node:fs/promises';

const [base, indexPath, output] = process.argv.slice(2);
if (!base || !/^(?:http:\/\/127\.0\.0\.1:[0-9]+|https:\/\/guide2build-web-[a-z0-9.-]+\.run\.app)\/?$/.test(base)
    || !indexPath || !output?.startsWith('var/evidence/')) {
  throw new Error('Pass a loopback/public Guide2Build URL, exact prepared release index and ignored evidence directory');
}
const index = JSON.parse(await readFile(indexPath, 'utf8'));
if (index.release_kind !== 'unverified_alpha' || index.releases.length !== 13) throw new Error('Expected the exact 13-alpha campaign');
await mkdir(output, {recursive: true});
const browser = await chromium.launch();
const checks = [];
try {
  for (const entry of index.releases) {
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
    const page = await context.newPage();
    const errors = [], warnings = [], requests = [], failed = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => {
      if (m.type() === 'error') errors.push(m.text());
      if (m.type() === 'warning') warnings.push(m.text());
    });
    page.on('request', r => requests.push(r.url()));
    page.on('response', r => {if (r.status() >= 400) failed.push({url: r.url(), status: r.status()});});
    const identity = `${entry.set_number}-${entry.guide_id}`;
    const started = performance.now();
    try {
      const response = await context.request.get(`${base}/api/v1/sets/${entry.set_number}/guides/${entry.guide_id}/release`);
      expect(response.status()).toBe(200);
      const manifest = await response.json();
      expect(manifest.release_sha256).toBe(entry.release_sha256);
      expect(manifest.release_kind).toBe('unverified_alpha');
      expect(manifest.alpha).toMatchObject({accuracy: 'unverified', human_review: 'not_run', physical_build: 'not_run'});
      expect(manifest.status).toBe('needs_review');
      const catalogueResponse = await context.request.get(`${base}/api/v1/sets/${entry.set_number}`);
      const catalogue = await catalogueResponse.json();
      expect(catalogue.guides.find(g => g.guide_id === entry.guide_id)).toMatchObject({tutorial_available: true, status: 'alpha_unverified'});
      await page.goto(base);
      await page.getByRole('combobox', {name: 'Your set number'}).selectOption(entry.set_number);
      await page.getByRole('button', {name: 'Find my set', exact: true}).click();
      const row = page.locator('.guide-row').filter({hasText: catalogue.guides.find(g => g.guide_id === entry.guide_id).label});
      await row.getByRole('button', {name: 'Open alpha model', exact: true}).click();
      await expect(page.locator('.candidate-status')).toHaveText('Alpha model · unverified');
      await expect(page.locator('.viewport')).toHaveAttribute('data-step-id', manifest.step_index[0].step_id, {timeout: 120000});
      await expect(page.getByRole('button', {name: 'Replay', exact: true})).toBeEnabled({timeout: 180000});
      await expect(page.getByRole('alert')).toHaveCount(0);
      const firstReadyMs = performance.now() - started;
      await page.getByRole('combobox', {name: 'Jump to instruction'}).selectOption(String(manifest.step_index.length - 1));
      await expect(page.locator('.viewport')).toHaveAttribute('data-step-id', manifest.step_index.at(-1).step_id, {timeout: 120000});
      await expect(page.getByRole('button', {name: 'Replay', exact: true})).toBeEnabled({timeout: 180000});
      await expect(page.getByRole('button', {name: 'Next', exact: true})).toBeDisabled();
      await expect(page.getByRole('button', {name: 'Review candidate', exact: true})).toHaveCount(0);
      await expect(page.locator('.source-crop')).toHaveCount(0);
      await expect(page.getByRole('alert')).toHaveCount(0);
      await page.getByLabel('Source, revision and checks', {exact: true}).click();
      await expect(page.locator('details.provenance')).toContainText(manifest.alpha.coverage_text);
      await expect(page.locator('details.provenance')).toContainText('Human review: not run · Physical build: not run');
      await expect(page.locator('details.provenance')).toContainText(`${entry.instances} model components`);
      await page.getByLabel('Source, revision and checks', {exact: true}).click();
      await page.screenshot({path: `${output}/${identity}-final.png`});
      if (entry.set_number === '30669' || entry.set_number === '10316' && entry.guide_id === 'booklet-03') {
        await page.setViewportSize({width: 390, height: 844});
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await expect(page.locator('.viewport canvas')).toBeVisible();
        await page.screenshot({path: `${output}/${identity}-phone.png`});
        await page.getByRole('tab', {name: 'Guide', exact: true}).click();
      }
      const finalPanel = manifest.step_index.at(-1).source;
      const finalSource = manifest.sources.find(s => s.source_sha256 === finalPanel.source_sha256);
      await expect(page.getByRole('link', {name: 'Open official booklet', exact: false})).toHaveAttribute(
        'href', `${finalSource.official_url}#page=${finalPanel.page_index + 1}`);
      expect(requests.filter(url => /\/api\/v1\/(sources|reconstructions|conversions|jobs|engine-preview)\b|\.pdf(?:\?|$)|assets-local/.test(url))).toEqual([]);
      expect(errors).toEqual([]);
      expect(failed).toEqual([]);
      const gpuReadbackWarnings = warnings.filter(message => /^\[\.WebGL-[^\]]+\]GL Driver Message .*GPU stall due to ReadPixels/.test(message));
      const applicationWarnings = warnings.filter(message => !gpuReadbackWarnings.includes(message));
      expect(applicationWarnings).toEqual([]);
      const check = {identity, release_sha256: entry.release_sha256, snapshots: manifest.step_index.length,
        firstReadyMs, firstAndFinalReadyMs: performance.now() - started, errors, failed, warnings, applicationWarnings, gpuReadbackWarnings,
        requests: requests.length, passed: true, scope: 'First and final snapshot UI/geometry; no assembly accuracy claim'};
      checks.push(check);
      console.log(JSON.stringify(check));
      await writeFile(`${output}/report.json`, JSON.stringify({base, scope: 'Public-alpha runtime inspection', checks,
        complete: checks.length === index.releases.length, browser: browser.version()}, null, 2));
    } finally {await context.close();}
  }
} finally {await browser.close();}
