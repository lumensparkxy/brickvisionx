import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';

// Network fixtures exercise the source-only UI; they are not reconstruction evidence.
test('source-only booklets retain identity, render page progress, and resume without a new job',async({page})=>{
  let state='rendering'; let queued=0; let sceneRequests=0;
  const job=()=>({job_id:'booklet-job',state,stage:state==='rendering'?'rendering':'complete',completed_units:state==='rendering'?50:600,total_units:600,attempts:1,output_revision:null,source_sha256:'a'.repeat(64),error:state==='needs_review'?{code:'assisted_reference_unavailable',message:'No authored reference is available.'}:null});
  await page.route('**/api/v1/sets/10316',r=>r.fulfill({json:{set_number:'10316',name:'Rivendell',official_page:'https://www.lego.com/en-us/service/building-instructions/10316',guides:[1,2,3].map(n=>({guide_id:`booklet-0${n}`,label:`Official booklet ${n} of 3`,expected_main_steps:null,tutorial_available:false,pdf_url:`https://www.lego.com/cdn/product-assets/product.bi.core.pdf/${['6455635','6698730','6455639'][n-1]}.pdf`}))}}));
  await page.route('**/api/v1/sets/10316/guides/*/scene',r=>{sceneRequests++;return r.fulfill({status:409,json:{detail:{code:'reconstruction_not_available',message:'No reconstruction'}}});});
  await page.route('**/api/v1/sets/10316/guides/booklet-02/status',r=>r.fulfill({json:{source_available:queued>0,latest_candidate_revision:null,latest_reviewed_revision:null,job:queued?job():null,coverage:null}}));
  await page.route('**/api/v1/conversions',r=>{expect(r.request().postDataJSON()).toEqual({set_number:'10316',guide_id:'booklet-02',mode:'assisted'});queued++;return r.fulfill({status:202,json:job()});});
  await page.route('**/api/v1/jobs/booklet-job',r=>r.fulfill({json:job()}));
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');await page.getByLabel('Your set number').selectOption('10316');await page.getByRole('button',{name:'Find my set',exact:true}).click();
  await expect(page.getByRole('button',{name:'Open tutorial',exact:true})).toHaveCount(0);
  await expect(page.getByText('Official booklet',{exact:true})).toHaveCount(3);
  await expect(page.locator('.guide-row').getByText(/Booklet:.*main steps/)).toHaveCount(0);
  await page.locator('.guide-row').filter({hasText:'Official booklet 2 of 3'}).getByRole('button',{name:'Prepare booklet',exact:true}).click();
  await expect(page.getByText('50 of 600 pages rendered',{exact:true})).toBeVisible();
  await expect(page.getByRole('progressbar')).toHaveAttribute('max','600');
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(sceneRequests).toBe(0);
  state='needs_review';
  await expect(page.locator('.job-state')).toContainText('Booklet prepared');
  await expect(page.locator('.job-state')).toContainText('No 3D reconstruction is available for this booklet yet.');
  await expect(page.getByText('The official pages are prepared. No 3D reconstruction is available for this booklet yet.',{exact:true})).toBeInViewport();
  await expect(page.getByRole('button',{name:'Close booklet selection',exact:true})).toBeInViewport();
  await expect(page.getByRole('button',{name:'Open candidate for review',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Prepare official booklet',exact:true})).toHaveCount(0);
  await mkdir('var/evidence/large-source-pipeline',{recursive:true});
  await page.screenshot({path:'var/evidence/large-source-pipeline/source-only-phone.png',fullPage:true});
  await page.getByRole('button',{name:'Close booklet selection',exact:true}).click();
  await page.getByRole('button',{name:'Find my set',exact:true}).click();
  await page.locator('.guide-row').filter({hasText:'Official booklet 2 of 3'}).getByRole('button',{name:'Prepare booklet',exact:true}).click();
  await expect(page.locator('.job-state')).toContainText('Booklet prepared');
  expect(queued).toBe(1);
  expect(await page.locator('.booklet-dialog').evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
});
