import { test, expect } from '@playwright/test';
// Network fixtures test UI states only; these do NOT prove PDF reconstruction or backend integration.
test('set lookup does not pretend that a model already exists', async ({ page }) => {
  await page.route('**/api/v1/sets/30669', route => route.fulfill({ json: {
    set_number: '30669', name: 'Iconic Red Plane', official_page: 'https://www.lego.com/en-ch/service/building-instructions/30669',
    guides: [{ guide_id: 'alt-02', label: 'Alternate aeroplane — booklet 02', expected_main_steps: 12, tutorial_available: true,
      pdf_url: 'https://www.lego.com/cdn/product-assets/product.bi.additional.extra.pdf/30669_02_BI_Build_Alt.pdf' }],
  } }));
  await page.route('**/api/v1/sets/30669/guides/alt-02/scene', route => route.fulfill({ status: 409,
    json: { detail: { code: 'reconstruction_not_available', message: 'The 3D reconstruction has not been prepared yet.' } } }));
  await page.route('**/api/v1/sets/30669/guides/alt-02/status',route=>route.fulfill({json:{source_available:true,latest_candidate_revision:null,latest_reviewed_revision:null,job:null,coverage:null}}));
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
test('preparation reports persisted stages and supports cancellation and retry',async({page})=>{
  let state='queued';let attempts=1;
  const job=()=>({job_id:'test-job',state,stage:state==='queued'?'fetching':state,completed_units:0,total_units:null,attempts,output_revision:null,source_sha256:null,error:state==='failed'?'Source download interrupted':null});
  await page.route('**/api/v1/sets/30669',r=>r.fulfill({json:{set_number:'30669',name:'Iconic Red Plane',official_page:'https://www.lego.com/',guides:[{guide_id:'alt-02',label:'Alternate booklet 02',expected_main_steps:12,tutorial_available:true,pdf_url:'https://www.lego.com/example.pdf'}]}}));
  await page.route('**/api/v1/sets/30669/guides/alt-02/scene',r=>r.fulfill({status:409,json:{detail:{code:'reconstruction_not_available',message:'No reconstruction yet.'}}}));
  await page.route('**/api/v1/sets/30669/guides/alt-02/status',r=>r.fulfill({json:{source_available:true,job:null,latest_candidate_revision:null,latest_reviewed_revision:null,coverage:null}}));
  await page.route('**/api/v1/conversions',r=>r.fulfill({status:202,json:job()}));
  await page.route('**/api/v1/jobs/test-job',r=>r.fulfill({json:job()}));
  await page.route('**/api/v1/jobs/test-job/cancel',r=>{state='cancelled';return r.fulfill({json:job()});});
  await page.route('**/api/v1/jobs/test-job/retry',r=>{state='failed';attempts++;return r.fulfill({json:job()});});
  await page.goto('/');await page.getByRole('button',{name:'Find my set'}).click();await page.getByRole('button',{name:'Open tutorial',exact:true}).click();
  await page.getByRole('button',{name:'Prepare official booklet',exact:true}).click();await expect(page.getByText('Stage: fetching')).toBeVisible();
  await page.getByRole('button',{name:'Cancel preparation',exact:true}).click();await expect(page.locator('.job-state')).toContainText('cancelled');
  await page.getByRole('button',{name:'Retry preparation',exact:true}).click();await expect(page.locator('.job-state')).toContainText('Source download interrupted');
});
