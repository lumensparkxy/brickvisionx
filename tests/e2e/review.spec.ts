import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
const evidence='var/evidence/review-panel';
async function open(page:import('@playwright/test').Page){
  await page.goto('/');await page.getByRole('button',{name:'Find my set',exact:true}).click();await page.getByRole('button',{name:'Open tutorial',exact:true}).click();
  await expect(page.locator('.viewport canvas')).toBeVisible();await expect(page.getByText('Loading individual part geometry…')).toBeHidden({timeout:30000});
  await page.getByRole('button',{name:'Review candidate',exact:true}).click();
}
test('real candidate review groups all records and navigates to the affected piece and guide',async({page})=>{
  await mkdir(evidence,{recursive:true});await page.setViewportSize({width:1440,height:1000});await open(page);
  await page.getByLabel('Jump to instruction').selectOption('15');
  const panel=page.getByRole('region',{name:'Reconstruction review'});
  await expect(panel.getByText('Loading review findings…')).toBeHidden();
  await expect(page.getByLabel('Translation [x, y, z] in LDU',{exact:true})).toBeHidden();
  await page.getByLabel('Show findings').selectOption('all');
  await expect(panel.getByRole('status')).toHaveText('40 of 40 findings · 9 grouped topics');
  await expect(panel.getByText('Candidate part mapping requires source comparison.',{exact:true})).toHaveCount(1);
  const mapping=panel.locator('.finding-card').filter({has:page.getByRole('heading',{name:'Part identity checks',exact:true})});
  await mapping.getByText('Affected pieces and instructions (32 findings)',{exact:true}).click();
  await expect(mapping.locator('.finding-context')).toHaveCount(32);
  const base=mapping.locator('.finding-context').filter({hasText:'Record: mapping-base'});
  await base.getByRole('button',{name:'Inspect step 1',exact:true}).click();
  await expect(page.getByLabel('Jump to instruction')).toHaveValue('0');
  await expect(page.locator('.source-pane')).toContainText('Main step 1');
  await panel.getByText('Advanced corrections',{exact:true}).click();
  await expect(page.getByRole('combobox',{name:'Physical instance',exact:true})).toHaveValue('base');
  await panel.getByText('Advanced corrections',{exact:true}).click();
  await page.getByLabel('Show findings').selectOption('current');
  await expect(panel.getByText('Uncertain colour',{exact:true})).toHaveCount(0);
  await panel.getByText('Affected pieces and instructions (3 findings)',{exact:true}).click();
  await panel.screenshot({path:`${evidence}/current-instruction.png`});
  await page.getByLabel('Show findings').selectOption('all');
  await panel.screenshot({path:`${evidence}/all-topics.png`});
  await page.setViewportSize({width:390,height:844});await panel.screenshot({path:`${evidence}/phone.png`});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
test('findings failure is distinct from empty findings and can retry',async({page})=>{
  let attempts=0;let unavailable=true;
  await page.route('**/api/v1/reconstructions/*/review-items',async route=>{
    attempts++;await route.fulfill(unavailable?{status:503,json:{detail:{message:'Review service temporarily unavailable'}}}:{json:{items:[]}});
  });
  await open(page);const panel=page.getByRole('region',{name:'Reconstruction review'});
  await expect(panel.getByRole('alert')).toContainText('Could not load review findings');
  await expect(panel.getByText('No recorded findings for this revision.',{exact:false})).toHaveCount(0);
  unavailable=false;const beforeRetry=attempts;
  await panel.getByRole('button',{name:'Retry findings',exact:true}).click();
  await expect(panel.getByText('No recorded findings for this revision.',{exact:false})).toBeVisible();
  expect(attempts).toBe(beforeRetry+1);
});
