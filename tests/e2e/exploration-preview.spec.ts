import {test,expect} from '@playwright/test';
import {createHash} from 'node:crypto';
import fixture from '../fixtures/synthetic.scene.json';
import {selectSyntheticSet} from './synthetic-selection';

// Original synthetic transport fixture. No LEGO reconstruction accuracy is inferred.
test('exploration exposes unresolved instructions while later snapshots remain inspectable',async({page})=>{
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  const steps=fixture.steps.map((step,index)=>({...step,section_id:'synthetic',main_step_number:index===0?1:index+2}));
  const chunks=steps.map((step,index)=>{
    const body=JSON.stringify({steps:[step]});
    return {body,index,path:`chunks/${index}.json`,sha256:createHash('sha256').update(body).digest('hex'),bytes:Buffer.byteLength(body),step_ids:[step.step_id]};
  });
  const manifest={...fixture,schema_version:'2.0',release_sha256:'a'.repeat(64),
    sources:[{guide_id:'synthetic',source_sha256:fixture.source_sha256,official_url:'https://www.lego.com/test.pdf',page_count:1}],
    sections:[{section_id:'synthetic',source_sha256:fixture.source_sha256,label:'Synthetic exploration transport'}],
    step_index:steps.map(({poses,visible_instance_ids,active_instance_ids,...step},chunk_index)=>({...step,chunk_index,
      visible_instance_count:visible_instance_ids.length,active_instance_count:active_instance_ids.length})),
    chunks:chunks.map(({body,...chunk})=>chunk),asset_base_url:'/exploration-fixture/',geometry_base_url:'/exploration-fixture/ldraw/'};
  const records=[
    {ordinal:0,main_step_number:1,page_index:0,step_ids:['s1'],reconstructed:true,finding_count:1,
      findings:[{category:'source_view',message:'Source camera unavailable; overview retained.',instance_ids:['a'],step_ids:['s1']}]},
    {ordinal:1,main_step_number:2,page_index:0,step_ids:[],reconstructed:false,finding_count:1,
      findings:[{category:'no_candidate',message:'No renderable proposal. Source evidence is retained.',instance_ids:[],step_ids:[]}]},
    {ordinal:2,main_step_number:3,page_index:0,step_ids:['s2'],reconstructed:true,needs_recheck:true,finding_count:1,
      findings:[{category:'unsupported_connector',message:'Attachment needs later source review.',instance_ids:['b'],step_ids:['s2']}]},
    {ordinal:3,main_step_number:4,page_index:0,step_ids:['s3'],reconstructed:true,finding_count:0,findings:[]},
  ];
  const status={job_id:'a'.repeat(32),set_number:'99999',guide_id:'synthetic',state:'paused',stage:'exploration_complete_with_findings',
    revision:fixture.revision,experiment_revision:'software-fixture',completed_panels:3,total_panels:4,instance_count:2,step_count:3,
    candidate_available:true,candidate_message:null,error:null,execution_policy:'explore',artifact_kind:'exploration_candidate',
    exploration:{processed_panels:4,reconstructed_panels:3,model_calls_used:12,max_model_calls:100,instructions:records}};
  await page.route('**/api/v1/config',route=>route.fulfill({json:{mode:'preview',source_images:true,requests_enabled:false}}));
  await page.route('**/api/v1/engine-preview**',route=>route.fulfill({json:status}));
  await page.route('**/api/v1/sets/99999',route=>route.fulfill({json:{set_number:'99999',name:'Synthetic exploration transport',official_page:'https://www.lego.com/',
    guides:[{guide_id:'synthetic',label:'Synthetic exploration transport',pdf_url:'https://www.lego.com/test.pdf',expected_main_steps:4,tutorial_available:true}]}}));
  await page.route('**/api/v1/sets/99999/guides/synthetic/release',route=>route.fulfill({json:manifest}));
  await page.route('**/exploration-fixture/chunks/*.json',route=>{
    const index=Number(route.request().url().split('/').at(-1)!.split('.')[0]);
    return route.fulfill({body:chunks[index].body,contentType:'application/json'});
  });
  await page.route('**/exploration-fixture/ldraw/**',route=>route.fulfill({status:404,body:'Geometry intentionally absent in transport test.'}));
  await page.route('**/api/v1/sources/**',route=>route.fulfill({status:404,body:'No real PDF in the synthetic transport test.'}));
  await page.goto('/');await selectSyntheticSet(page);await page.getByRole('button',{name:'Find my set',exact:true}).click();
  await expect(page.getByLabel('Engine candidate preview')).toContainText('4 of 4 instructions processed · 3 reconstructed');
  await page.getByRole('button',{name:'Open candidate',exact:true}).click();
  await expect(page.locator('.candidate-status')).toHaveText('Exploration · provisional');
  const findings=page.locator('.exploration-findings');
  await findings.locator('summary').first().click();
  await expect(findings).toContainText('Source camera unavailable; overview retained.');
  await findings.getByRole('button',{name:'All findings',exact:true}).click();
  await expect(findings.getByLabel('Findings for instruction 2')).toContainText('No reconstruction available');
  await expect(findings.getByLabel('Findings for instruction 2')).toContainText('No renderable proposal.');
  await expect(findings.getByLabel('Findings for instruction 2').getByRole('link')).toHaveAttribute('href',`/api/v1/sources/${fixture.source_sha256}/pages/0`);
  await findings.getByRole('button',{name:'Inspect step 3',exact:true}).click();
  await expect(page.locator('.viewport')).toHaveAttribute('data-step-id','s2');
  await findings.getByRole('button',{name:'This instruction',exact:true}).click();
  await expect(findings).toContainText('Attachment needs later source review.');
  await expect(findings).toContainText('These findings were recorded before the correction and need a fresh review.');
  await expect(findings).not.toContainText('No renderable proposal.');
  await page.getByRole('button',{name:'Next',exact:true}).click();
  await expect(page.locator('.viewport')).toHaveAttribute('data-step-id','s3');
  await expect(page.locator('.end-note')).toContainText('4 instructions processed, 3 reconstructed');
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('tab',{name:'Pieces',exact:true}).click();
  await expect(findings).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
