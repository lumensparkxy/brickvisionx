import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';

test('playground is responsive, uses real image assets, and links to the workflow',async({page})=>{
  await mkdir('var/evidence/landing-playground',{recursive:true});
  await page.goto('/');
  for(const width of [1199,768,390,320]){
    await page.setViewportSize({width,height:width===1199?1312:844});
    await expect(page.getByRole('button',{name:'Find my set',exact:true})).toBeInViewport();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.getByRole('link',{name:'How it works',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Three steps to a great build.'})).toBeInViewport();
    await expect.poll(()=>page.locator('.build-steps img').evaluateAll(images=>images.every(image=>(image as HTMLImageElement).complete&&(image as HTMLImageElement).naturalWidth>0))).toBe(true);
    await page.getByRole('link',{name:'Guide2Build 3D',exact:true}).click();
  }
  await page.screenshot({path:'var/evidence/landing-playground/phone-320.png',fullPage:true});
});

test('example shortcut resolves the supported guide and opens the real tutorial',async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.goto('/');
  await page.getByLabel('Your set number').selectOption('60400');
  await page.getByRole('button',{name:'Try the plane tutorial',exact:true}).click();
  await expect(page.locator('.workspace')).toBeVisible();
  await expect(page.locator('.candidate-status')).toContainText('needs review');
  expect(await page.evaluate(()=>scrollY)).toBe(0);
  await page.getByRole('button',{name:'Back to set lookup',exact:true}).click();
  await expect(page.getByRole('heading',{name:'30669 · Iconic Red Plane',exact:true})).toBeFocused();
  await expect(page.getByLabel('Your set number')).toHaveValue('30669');
});

test('example shortcut keeps unavailable-source preparation and lookup errors actionable',async({page})=>{
  await page.route('**/api/v1/sets/30669/guides/alt-02/scene',r=>r.fulfill({status:409,json:{detail:{code:'reconstruction_not_available',message:'The reconstruction is not prepared yet.'}}}));
  await page.route('**/api/v1/sets/30669/guides/alt-02/status',r=>r.fulfill({json:{source_available:true,latest_candidate_revision:null,latest_reviewed_revision:null,job:null,coverage:null}}));
  await page.goto('/');await page.getByRole('button',{name:'Try the plane tutorial',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('not prepared');
  await expect(page.getByRole('heading',{name:'Preparation needs attention'})).toBeFocused();
  await expect(page.getByRole('button',{name:'Prepare official booklet',exact:true})).toBeVisible();
  await expect(page.locator('.workspace')).toHaveCount(0);
  await page.getByRole('button',{name:'Close booklet selection'}).click();
  await page.route('**/api/v1/sets/30669',r=>r.fulfill({status:503,json:{detail:{code:'source_unavailable',message:'The official source is temporarily unavailable.'}}}));
  await page.getByRole('button',{name:'Find my set',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('temporarily unavailable');
  await expect(page.getByRole('heading',{name:'Set lookup',exact:true})).toBeFocused();
});
