import {test,expect,type Page} from '@playwright/test';
import {createHash} from 'node:crypto';
import {mkdir} from 'node:fs/promises';
import fixture from '../fixtures/synthetic.scene.json';
import {selectSyntheticSet} from './synthetic-selection';

// Original 99999 transport fixture with deliberately absent geometry. This verifies
// public alpha disclosures and loading boundaries, never reconstruction accuracy.
const evidence='var/evidence/public-alpha/software';
const coverage='Reported coverage (unverified): synthetic transport only; 3 candidate instructions and 2 physical instances.';
const notes=['Synthetic transport fixture. Individual geometry is intentionally absent.'];
test.use({viewport:{width:1440,height:900}});
test.beforeAll(async()=>{await mkdir(evidence,{recursive:true});});

async function transport(page:Page) {
  const steps=fixture.steps.map((step,index)=>({...step,section_id:index<2?'first':'second',main_step_number:index<2?step.main_step_number:1}));
  const chunks=steps.map((step,index)=>{
    const body=JSON.stringify({steps:[step]});
    return {body,index,path:`chunks/${index}.json`,sha256:createHash('sha256').update(body).digest('hex'),bytes:Buffer.byteLength(body),step_ids:[step.step_id]};
  });
  const manifest={...fixture,schema_version:'2.0',status:'needs_review',release_sha256:'a'.repeat(64),release_kind:'unverified_alpha',
    alpha:{artifact_kind:'pdf_assisted_alpha_completion',generation_mode:'alpha_fast',source_coverage:'synthetic_transport_unverified',
      coverage_text:coverage,uncertainty_notes:notes,accuracy:'unverified',human_review:'not_run',physical_build:'not_run'},
    sources:[{guide_id:'synthetic',source_sha256:fixture.source_sha256,official_url:'https://www.lego.com/test.pdf',page_count:4}],
    sections:['first','second'].map(section_id=>({section_id,source_sha256:fixture.source_sha256,label:section_id})),
    step_index:steps.map(({poses,visible_instance_ids,active_instance_ids,...step},chunk_index)=>({...step,chunk_index,
      visible_instance_count:visible_instance_ids.length,active_instance_count:active_instance_ids.length})),
    chunks:chunks.map(({body,...chunk})=>chunk),asset_base_url:'/published-assets/alpha-transport/',geometry_base_url:'/published-assets/alpha-transport/ldraw/'};
  const requested:string[]=[];const errors:string[]=[];
  page.on('request',request=>requested.push(request.url()));page.on('pageerror',error=>errors.push(error.message));
  const control={manifest,requested,errors,releaseStatus:200,releaseGate:undefined as Promise<void>|undefined,thirdChunk:undefined as Promise<void>|undefined};
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.route('**/api/v1/config',route=>route.fulfill({json:{mode:'public',source_images:false,requests_enabled:false}}));
  await page.route('**/api/v1/sets/99999',route=>route.fulfill({json:{set_number:'99999',name:'Synthetic alpha transport fixture',official_page:'https://www.lego.com/',status:'alpha_unverified',guides:[
    {guide_id:'synthetic',label:'Synthetic alpha transport fixture',pdf_url:'https://www.lego.com/test.pdf',expected_main_steps:null,
      tutorial_available:true,alpha_available:true,release_kind:'unverified_alpha',status:'alpha_unverified'},
    {guide_id:'not-ready',label:'Unpublished synthetic booklet',pdf_url:'https://www.lego.com/unpublished-test.pdf',expected_main_steps:null,tutorial_available:false,status:'not_ready'}]}}));
  await page.route('**/api/v1/sets/99999/guides/synthetic/release',async route=>{
    await control.releaseGate;
    await route.fulfill({status:control.releaseStatus,json:control.releaseStatus===200?control.manifest:{detail:{code:'alpha_unavailable',message:'This alpha model is temporarily unavailable. Please try again.'}}});
  });
  await page.route('**/published-assets/alpha-transport/chunks/*.json',async route=>{
    const index=Number(route.request().url().split('/').at(-1)!.split('.')[0]);
    if(index===2)await control.thirdChunk;
    await route.fulfill({body:chunks[index].body,contentType:'application/json'});
  });
  await page.route('**/published-assets/alpha-transport/ldraw/**',route=>route.fulfill({status:404,body:'Geometry deliberately absent in the synthetic transport fixture.'}));
  await page.goto('/');await selectSyntheticSet(page);await page.getByRole('button',{name:'Find my set',exact:true}).click();
  await expect(page.getByRole('heading',{name:'99999 · Synthetic alpha transport fixture',exact:true})).toBeVisible();
  return control;
}

test('public alpha transport exposes honest labels, immutable navigation, official links and named missing geometry',async({page})=>{
  const control=await transport(page);
  expect(await page.title()).toBe('Guide2Build 3D');
  await expect(page.getByText('Choose an alpha model to explore in 3D. Accuracy is unverified.',{exact:true})).toBeVisible();
  await expect(page.getByText('ALPHA MODEL · UNVERIFIED',{exact:true})).toBeVisible();
  await expect(page.getByText('NOT READY YET',{exact:true})).toBeVisible();
  await expect(page.getByText('READY TO BUILD',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Open alpha model',exact:true})).toHaveCount(1);
  await expect(page.getByRole('button',{name:/Prepare|conversion|Open tutorial/})).toHaveCount(0);
  const details=page.locator('details').filter({has:page.getByText('Alpha accuracy and review details',{exact:true})});
  await expect(details).not.toHaveAttribute('open');
  await details.locator('summary').focus();await page.keyboard.press('Enter');
  await expect(details).toHaveAttribute('open','');await expect(details).toContainText('Human review: not run · Physical build: not run');
  await details.locator('summary').press('Enter');
  await page.screenshot({path:`${evidence}/desktop-booklet.png`});
  await page.getByRole('button',{name:'Open alpha model',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Step 1',exact:true})).toBeVisible();
  await expect(page.locator('.candidate-status')).toHaveText('Alpha model · unverified');
  await expect(page.getByRole('button',{name:'Review candidate',exact:true})).toHaveCount(0);
  await expect(page.locator('.source-crop')).toHaveCount(0);
  await expect(page.getByRole('link',{name:'Open official booklet',exact:false})).toHaveAttribute('href','https://www.lego.com/test.pdf#page=1');
  await expect(page.getByRole('alert').filter({hasText:'Required geometry unavailable'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Play full build',exact:true})).toBeDisabled();
  const provenance=page.locator('details.provenance');
  await expect(provenance).not.toHaveAttribute('open');
  await page.getByLabel('Source, revision and checks',{exact:true}).click();
  await expect(provenance).toContainText(coverage);await expect(provenance).toContainText(notes[0]);
  await expect(provenance).toContainText('Human review: not run · Physical build: not run');
  await expect(provenance).toContainText('Geometry: not_run · Connections: not_run');
  await expect(provenance).not.toContainText('Human acceptance: recorded');
  await expect(page.getByRole('link',{name:'Individual geometry notices',exact:false})).toHaveAttribute('href',/\/published-assets\/alpha-transport\/ldraw\/NOTICES\.txt$/);
  await page.getByLabel('Source, revision and checks',{exact:true}).click();
  let releaseThird!:()=>void;control.thirdChunk=new Promise<void>(resolve=>{releaseThird=resolve;});
  try {
    await page.getByRole('button',{name:'Go to main step 1 in second',exact:true}).click();
    await expect(page.getByText('Loading this instruction…',{exact:true})).toBeVisible();await expect(page.locator('.viewport')).toHaveCount(0);
    releaseThird();await expect(page.locator('.viewport')).toHaveAttribute('data-step-id','s3');
    await expect(page.getByRole('heading',{name:'Step 1',exact:true})).toBeVisible();
    await expect(page.getByText('No new pieces.',{exact:false})).toBeVisible();
    await page.getByRole('button',{name:'Full parts list',exact:true}).click();await expect(page.locator('.parts-table')).toContainText('×2');
    await page.getByRole('button',{name:'New pieces',exact:true}).click();
    await page.getByText('Active model components (2)',{exact:true}).click();
    await expect(page.locator('.physical-pieces ol li')).toHaveText(['a','b']);
    await page.getByRole('button',{name:'Previous',exact:true}).click();await expect(page.locator('.viewport')).toHaveAttribute('data-step-id','s2');
    await page.getByRole('button',{name:'Next',exact:true}).click();await expect(page.locator('.viewport')).toHaveAttribute('data-step-id','s3');
    await expect(page.getByText('No new pieces.',{exact:false})).toBeVisible();
  } finally {releaseThird?.();}
  await page.screenshot({path:`${evidence}/desktop-missing-geometry.png`});
  await page.setViewportSize({width:390,height:844});
  await expect(page.locator('.candidate-status')).toBeVisible();
  await expect(page.getByRole('alert').filter({hasText:'Required geometry unavailable'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`${evidence}/mobile-missing-geometry.png`});
  await page.getByRole('tab',{name:'Guide',exact:true}).click();
  await expect(page.getByRole('link',{name:'Open official booklet',exact:false})).toHaveAttribute('href','https://www.lego.com/test.pdf#page=1');
  await expect(page.locator('vite-error-overlay')).toHaveCount(0);
  expect(control.requested.some(url=>/\/api\/v1\/(engine-preview|jobs|conversions|sources|reconstructions)\b|assets-local/.test(url))).toBe(false);
  expect(control.requested.some(url=>url.startsWith('https://www.lego.com/'))).toBe(false);
  expect(control.errors).toEqual([]);
  await test.info().attach('synthetic-public-alpha-traffic',{body:JSON.stringify({identity:'99999/synthetic',purpose:'Transport and UI only; deliberately missing geometry',requests:control.requested,pageErrors:control.errors}),contentType:'application/json'});
});

test('alpha release loading and temporary failure preserve a visible retry action',async({page})=>{
  const control=await transport(page);let finishRelease!:()=>void;
  control.releaseStatus=503;control.releaseGate=new Promise<void>(resolve=>{finishRelease=resolve;});
  try {
    await page.getByRole('button',{name:'Open alpha model',exact:true}).click();
    await expect(page.getByRole('button',{name:'Open alpha model',exact:true})).toBeDisabled();
    await expect(page.getByLabel('Your set number')).toBeDisabled();
    await expect(page.getByText('Working on your request…',{exact:true})).toBeVisible();
    finishRelease();
    await expect(page.getByRole('alert')).toContainText('This alpha model is temporarily unavailable. Please try again.');
    await expect(page.getByRole('heading',{name:'Let’s try again',exact:true})).toBeFocused();
    await expect(page.getByRole('button',{name:'Open alpha model',exact:true})).toBeEnabled();
    await expect(page.locator('.workspace')).toHaveCount(0);
    control.releaseStatus=200;control.releaseGate=undefined;
    await page.getByRole('button',{name:'Open alpha model',exact:true}).click();
    await expect(page.locator('.candidate-status')).toHaveText('Alpha model · unverified');
    expect(control.errors).toEqual([]);
  } finally {finishRelease?.();}
});

test('misleading reviewed alpha metadata is rejected before entering the viewer',async({page})=>{
  const control=await transport(page);control.manifest.alpha.human_review='pass';
  await page.getByRole('button',{name:'Open alpha model',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Invalid tutorial release: alpha metadata');
  await expect(page.getByRole('heading',{name:'Let’s try again',exact:true})).toBeFocused();
  await expect(page.locator('.workspace')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Open alpha model',exact:true})).toBeEnabled();
  expect(control.requested.some(url=>url.includes('/published-assets/alpha-transport/'))).toBe(false);
  expect(control.errors).toEqual([]);
});
