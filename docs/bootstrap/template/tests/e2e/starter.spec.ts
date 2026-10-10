import { test, expect } from '@playwright/test';
// Network fixtures test UI states only; these do NOT prove PDF reconstruction or backend integration.
test('set lookup does not pretend that a model already exists', async ({ page }) => {
  await page.route('**/api/v1/sets/30669', route => route.fulfill({ json: {
    set_number: '30669', name: 'Iconic Red Plane', official_page: 'https://www.lego.com/en-ch/service/building-instructions/30669',
    guides: [{ guide_id: 'alt-02', label: 'Alternate aeroplane — booklet 02', expected_main_steps: 12,
      pdf_url: 'https://www.lego.com/cdn/product-assets/product.bi.additional.extra.pdf/30669_02_BI_Build_Alt.pdf' }],
  } }));
  await page.route('**/api/v1/sets/30669/guides/alt-02/scene', route => route.fulfill({ status: 409,
    json: { detail: { code: 'reconstruction_not_available', message: 'The 3D reconstruction has not been prepared yet.' } } }));
  await page.goto('/');
  await expect(page.getByLabel('Set number')).toHaveValue('30669');
  await page.getByRole('button', { name: 'Find my set' }).click();
  await expect(page.getByRole('heading', { name: '30669 · Iconic Red Plane' })).toBeVisible();
  await page.getByRole('button', { name: 'Open tutorial' }).click();
  await expect(page.getByRole('alert')).toContainText('not been prepared');
  await expect(page.locator('input[type=file]')).toHaveCount(0);
});
test('small-screen landing is usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Find my set' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
