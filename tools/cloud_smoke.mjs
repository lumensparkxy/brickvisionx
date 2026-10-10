// Actual public deployment checks. Never creates or approves tutorial releases.
import {chromium, expect} from '@playwright/test';
import {mkdir, readFile, writeFile} from 'node:fs/promises';

const base = process.argv[2];
const preview = process.argv[3];
if (!base || !/^https:\/\/guide2build-web-[a-z0-9.-]+\.run\.app$/.test(base)) {
  throw new Error('Pass the verified Guide2Build Cloud Run public URL');
}
const output = 'var/evidence/cloud-release/browser-live';
await mkdir(output, {recursive: true});
const browser = await chromium.launch();
const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
const page = await context.newPage();
const errors = [], warnings = [], urls = [], timings = [];
const catalogue = JSON.parse(await readFile(new URL('../config/sets.json', import.meta.url), 'utf8')).sets;
const catalogueChecks = [];
page.on('pageerror', error => errors.push(error.message));
page.on('console', message => {
  if (message.type() === 'error') errors.push(message.text());
  if (message.type() === 'warning') warnings.push(message.text());
});
page.on('request', request => urls.push(request.url()));
async function waitForArtwork() {
  await page.locator('#how-it-works').scrollIntoViewIfNeeded();
  await expect.poll(() => page.locator('img').evaluateAll(images =>
    images.length === 4 && images.every(image => image.complete && image.naturalWidth > 0))).toBe(true);
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(Array.from(document.images, image => image.decode()));
    window.scrollTo(0, 0);
  });
}
try {
  const config = await context.request.get(`${base}/api/v1/config`);
  expect(config.status()).toBe(200);
  expect(await config.json()).toEqual({mode: 'public', source_images: false, requests_enabled: true});
  for (const path of ['jobs/example', 'conversions', 'sources/example/pages/0',
    'reconstructions/example/scene', 'approvals', 'corrections']) {
    expect((await context.request.get(`${base}/api/v1/${path}`)).status()).toBe(404);
  }
  if (preview) expect((await context.request.get(preview)).status()).toBe(403);
  const cdp = await context.newCDPSession(page);
  await cdp.send('Network.enable');
  // Controlled network conditions measure this portal only, not missing 3D tutorials.
  await cdp.send('Network.emulateNetworkConditions', {
    offline: false, latency: 40, downloadThroughput: 5_000_000 / 8, uploadThroughput: 1_000_000 / 8,
  });
  for (const state of ['cold', 'warm']) {
    await cdp.send('Network.setCacheDisabled', {cacheDisabled: state === 'cold'});
    if (state === 'cold') await cdp.send('Network.clearBrowserCache');
    const start = performance.now();
    await page.goto(base);
    await expect(page.getByRole('button', {name: 'Find my set', exact: true})).toBeEnabled();
    timings.push({state, portalReadyMs: performance.now() - start,
      navigation: await page.evaluate(() => performance.getEntriesByType('navigation')[0]?.toJSON())});
  }
  const selector = page.getByRole('combobox', {name: 'Your set number'});
  expect(await selector.locator('option').allTextContents()).toEqual(
    catalogue.map(set => `${set.set_number} - ${set.name}`));
  await expect(page.getByRole('button', {name: /^Open set /})).toHaveCount(0);
  for (const set of catalogue) {
    const response = await context.request.get(`${base}/api/v1/sets/${set.set_number}`);
    expect(response.status()).toBe(200);
    const value = await response.json();
    expect(value.set_number).toBe(set.set_number);
    expect(value.name).toBe(set.name);
    expect(value.guides.map(guide => guide.guide_id)).toEqual(set.guides.map(guide => guide.guide_id));
    catalogueChecks.push({set_number: value.set_number, name: value.name,
      guides: value.guides.map(guide => ({guide_id: guide.guide_id, tutorial_available: guide.tutorial_available,
        release_kind: guide.release_kind}))});
  }
  await waitForArtwork();
  await page.screenshot({path: `${output}/desktop.png`, fullPage: true});
  await selector.selectOption('30669');
  const planeAlpha = catalogueChecks.find(set => set.set_number === '30669').guides
    .some(guide => guide.release_kind === 'unverified_alpha');
  const recorded = !planeAlpha && page.waitForResponse(r => r.url() === `${base}/api/v1/requests` && r.request().method() === 'POST');
  await page.getByRole('button', {name: 'Find my set', exact: true}).click();
  const message = 'This build isn’t ready yet. We’ve added it to our building list. Come back later to see what’s new!';
  await expect(page.getByRole('button', {name: 'Open tutorial', exact: true})).toHaveCount(0);
  if (planeAlpha) {
    await page.getByRole('button', {name: 'Open alpha model', exact: true}).click();
    await expect(page.locator('.candidate-status')).toHaveText('Alpha model · unverified');
    await expect(page.getByRole('button', {name: 'Replay', exact: true})).toBeEnabled({timeout: 120000});
    await expect(page.getByRole('alert')).toHaveCount(0);
    await page.screenshot({path: `${output}/plane-alpha.png`});
    await page.getByRole('button', {name: 'Back to set lookup'}).click();
  } else {
    expect((await recorded).status()).toBe(202);
    await expect(page.getByRole('status').filter({hasText: message})).toBeVisible();
    await page.screenshot({path: `${output}/recorded-request.png`});
  }
  const duplicate = await context.request.post(`${base}/api/v1/requests`, {
    data: {set_number: '30669'}, headers: {Origin: base},
  });
  expect(duplicate.status()).toBe(202);
  expect((await duplicate.json()).duplicate).toBe(true);
  await page.getByRole('button', {name: 'Close booklet selection'}).click();
  await page.setViewportSize({width: 390, height: 844});
  await selector.selectOption('10316');
  await waitForArtwork();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: `${output}/phone-home.png`, fullPage: true});
  await selector.selectOption('60400');
  await page.getByRole('button', {name: 'Find my set', exact: true}).click();
  const kartAlpha = catalogueChecks.find(set => set.set_number === '60400').guides
    .some(guide => guide.release_kind === 'unverified_alpha');
  if (kartAlpha) await expect(page.getByRole('button', {name: 'Open alpha model', exact: true})).toHaveCount(2);
  else await expect(page.getByRole('status').filter({hasText: message})).toBeVisible();
  await expect(page.getByRole('heading', {name: '60400 · Go-Karts and Race Drivers', exact: true})).toBeVisible();
  await expect(page.getByRole('link', {name: 'View official instructions'})).toBeVisible();
  const unknown = await context.request.get(`${base}/api/v1/sets/99998`);
  expect(unknown.status()).toBe(200);
  expect(await unknown.json()).toMatchObject({set_number: '99998', name: null, guides: []});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: `${output}/phone.png`});
  expect(urls.filter(url => /\/api\/v1\/(sources|reconstructions|conversions|jobs)\b|\.pdf(?:\?|$)|assets-local/.test(url))).toEqual([]);
  expect(errors).toEqual([]);
  // Chromium can warn during thumbnail/screenshot pixel readback. Keep these in
  // evidence; they are distinct from application warnings and GPU benchmarks.
  const gpuReadbackWarnings = warnings.filter(message => /^\[\.WebGL-[^\]]+\]GL Driver Message .*GPU stall due to ReadPixels/.test(message));
  const applicationWarnings = warnings.filter(message => !gpuReadbackWarnings.includes(message));
  expect(applicationWarnings).toEqual([]);
  await writeFile(`${output}/report.json`, JSON.stringify({base, preview, passed: true, timings, catalogueChecks,
    network: {latencyMs: 40, downloadMbps: 5, uploadMbps: 1}, urls, errors, warnings, applicationWarnings, gpuReadbackWarnings,
    screenshotArtwork: 'all four landing images decoded; fonts ready',
    tutorialLoadAndGpu: planeAlpha ? 'plane_alpha_geometry_loaded; accuracy and GPU timing not certified' : 'not_measured_no_published_complete_tutorial',
    browser: await browser.version()}, null, 2));
  console.log(JSON.stringify({passed: true, base, output, timings: timings.map(({state, portalReadyMs}) => ({state, portalReadyMs}))}));
} finally {
  await browser.close();
}
