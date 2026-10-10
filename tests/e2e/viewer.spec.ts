import {selectSyntheticSet} from './synthetic-selection';
import {test,expect} from '@playwright/test';
import fixture from '../fixtures/synthetic.scene.json';
// Structural fixture tests exercise UI state, never reconstruction accuracy for the target set.
async function synthetic(page: import('@playwright/test').Page) {
  await page.route('**/api/v1/sets/99999',r=>r.fulfill({json:{set_number:'99999',name:'Original synthetic test fixture',official_page:'https://www.lego.com/',guides:[{guide_id:'synthetic',label:'Synthetic test guide',expected_main_steps:3,tutorial_available:true,pdf_url:'https://www.lego.com/example.pdf'}]}}));
  await page.route('**/api/v1/sets/99999/guides/synthetic/scene',r=>r.fulfill({json:fixture}));
  await page.route('**/api/v1/sources/**',r=>r.fulfill({status:404,json:{detail:{message:'Test source intentionally absent'}}}));
  await page.goto('/'); await selectSyntheticSet(page);await page.getByRole('button',{name:'Find my set'}).click();await page.getByRole('button',{name:'Open tutorial',exact:true}).click();
  await expect(page.locator('.candidate-status')).toBeVisible();
  await page.locator('.provenance summary').click();
  await expect(page.getByText('Coverage: 3 of 3 main steps', {exact:false})).toBeVisible();
  await page.locator('.provenance summary').click();
}
test('snapshot navigation, attachment BOM, unavailable replay and revision-scoped resume',async({page})=>{
  await synthetic(page);await expect(page.getByRole('heading',{name:'Step 1 of 3',exact:true})).toBeVisible();
  await page.locator('.model-caption').click();await page.keyboard.press('ArrowRight');await expect(page.getByRole('heading',{name:'Step 2 of 3',exact:true})).toBeVisible();await page.keyboard.press('ArrowLeft');await expect(page.getByRole('heading',{name:'Step 1 of 3',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Next',exact:true}).click(); await expect(page.getByText('Build detached subassembly', {exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Next',exact:true}).click(); await expect(page.getByText('No new pieces.',{exact:false})).toBeVisible();
  await expect(page.getByRole('button',{name:'Replay',exact:true})).toBeDisabled();await expect(page.locator('.viewport')).toHaveAttribute('data-step-id','s3');
  await page.getByRole('button',{name:'Full parts list',exact:true}).click();await expect(page.locator('.parts-table')).toContainText('×2');
  await page.getByLabel('Jump to instruction').selectOption('0');await expect(page.locator('.viewport')).toHaveAttribute('data-step-id','s1');
  await page.getByLabel('Jump to instruction').selectOption('1');
  await page.reload();await selectSyntheticSet(page);await page.getByRole('button',{name:'Find my set'}).click();await page.getByRole('button',{name:'Open tutorial',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Step 2 of 3',exact:true})).toBeVisible();
});
test('narrow layout uses accessible panels and reports absent geometry',async({page})=>{
  await page.setViewportSize({width:390,height:844});await synthetic(page);
  await expect(page.getByRole('tab',{name:'3D',exact:true})).toHaveAttribute('aria-selected','true');
  await expect(page.getByRole('alert').filter({hasText:'Required geometry unavailable'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Play full build',exact:true})).toBeDisabled();
  await page.getByRole('tab',{name:'Pieces',exact:true}).click();await expect(page.getByRole('heading',{name:'Step 1 of 3',exact:true})).toBeVisible();
  await page.getByRole('tab',{name:'Guide',exact:true}).click();await expect(page.getByRole('heading',{name:'Original guide',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
test('WebGL failure retains source and navigation',async({page})=>{
  await page.addInitScript(()=>{const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type:string,...args:unknown[]){if(type.includes('webgl'))return null;return original.apply(this,[type,...args] as never);} as typeof original;});
  await synthetic(page);await expect(page.getByRole('alert').filter({hasText:'WebGL is unavailable'})).toBeVisible();await expect(page.getByRole('button',{name:'Play full build',exact:true})).toBeDisabled();await page.getByRole('button',{name:'Next',exact:true}).click();await expect(page.getByRole('heading',{name:'Step 2 of 3',exact:true})).toBeVisible();
});
test('correction editor preserves draft on conflict and saves a distinct revision',async({page})=>{
  await page.route('**/api/v1/reconstructions/*/review-items',r=>r.fulfill({json:{revision:'fixture-r1',items:[]}}));
  let conflict=true;let command:Record<string,unknown>|undefined;
  await page.route('**/api/v1/reconstructions/fixture-r1/corrections',async r=>{
    command=r.request().postDataJSON();
    if(conflict){conflict=false;await r.fulfill({status:409,json:{detail:{code:'stale_revision',message:'The base revision changed. Reopen the latest candidate.'}}});return;}
    const corrected=structuredClone(fixture);corrected.revision='fixture-r2';corrected.steps[0].poses.a.position_ldu=[20,0,0];
    await r.fulfill({json:{revision:corrected.revision,scene:corrected,checks:{structure:'pass',geometry:'not_run',connectors:'not_run'}}});
  });
  await synthetic(page);await page.getByRole('button',{name:'Review candidate',exact:true}).click();
  await page.getByText('Advanced corrections',{exact:true}).click();
  await page.getByRole('combobox',{name:'Correction actor',exact:true}).selectOption('agent');await page.getByLabel('Reviewer name',{exact:true}).fill('synthetic-browser-test');
  await page.getByLabel('Translation [x, y, z] in LDU',{exact:true}).fill('20, 0, 0');await page.getByLabel('Reason and source evidence',{exact:true}).fill('Synthetic UI correction test only.');
  await page.getByRole('button',{name:'Save revision and revalidate',exact:true}).click();await expect(page.getByRole('alert').filter({hasText:'base revision changed'})).toBeVisible();
  await expect(page.getByLabel('Translation [x, y, z] in LDU',{exact:true})).toHaveValue('20, 0, 0');
  await page.getByRole('button',{name:'Save revision and revalidate',exact:true}).click();
  await page.locator('.provenance summary').click();await expect(page.locator('.provenance')).toContainText('fixture-r2');
  expect(command?.actor_type).toBe('agent');expect(command?.expected_revision).toBe('fixture-r1');expect(command?.command).toMatchObject({type:'pose',instance_id:'a',pose:{position_ldu:[20,0,0]}});
});
