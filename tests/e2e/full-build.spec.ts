// Exclude floating UI from pixel comparisons: these checks measure the 3D renderer.
const modelOnly = {style: '.camera-controls,.model-caption,.gesture-hint,.placement-note {visibility:hidden!important}'};
import {test,expect,type Page} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
const evidence='var/evidence/full-build';
async function open(page:Page){
  await page.goto('/');await page.getByRole('button',{name:'Find my set',exact:true}).click();await page.getByRole('button',{name:'Open tutorial',exact:true}).click();
  await expect(page.getByRole('button',{name:'Play full build',exact:true})).toBeEnabled({timeout:30000});
}
const button=(page:Page,name:string)=>page.getByRole('button',{name,exact:true});
test('plays every real instruction slowly, freezes on pause, and reaches the exact final snapshot',async({page})=>{
  test.setTimeout(100000);await mkdir(evidence,{recursive:true});await page.setViewportSize({width:1440,height:1200});await open(page);
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  const status=await (await page.request.get('/api/v1/sets/30669/guides/alt-02/status')).json();
  const scene=await (await page.request.get(`/api/v1/reconstructions/${status.latest_candidate_revision}/scene`)).json();
  await page.getByLabel('Jump to instruction').selectOption(String(scene.steps.length-1));
  await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','idle');
  const canvas=page.locator('.viewport canvas');const final=await canvas.screenshot(modelOnly);
  const started=Date.now();await button(page,'Play full build').click();
  await expect(page.getByLabel('Jump to instruction')).toHaveValue('0');
  await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','playing');
  // Starting pieces have a labelled visual entrance, not a guessed attachment direction.
  await expect(page.locator('.viewport')).toHaveAttribute('data-placement-mode','preview');
  await expect(page.locator('.viewport')).toHaveAttribute('data-approach-reason','starting_pieces');
  await button(page,'Pause build').click();await expect(button(page,'Resume build')).toBeVisible();
  // A pause can land in the stationary hold between steps; both states must freeze the same snapshot.
  await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state',/^(paused|idle)$/);
  const frozen=await canvas.screenshot(modelOnly);await page.waitForTimeout(700);expect(frozen.equals(await canvas.screenshot(modelOnly))).toBe(true);
  await expect(page.getByLabel('Jump to instruction')).toHaveValue('0');
  await page.screenshot({path:`${evidence}/paused.png`,fullPage:true});
  await button(page,'Resume build').click();
  const seen:string[]=[];
  for(let i=0;i<scene.steps.length;i++){
    const step=scene.steps[i];
    await expect(page.getByLabel('Jump to instruction')).toHaveValue(String(i),{timeout:8000});
    await expect(page.locator('.viewport')).toHaveAttribute('data-step-id',step.step_id);
    await expect(page.locator('.source-crop canvas')).toHaveAttribute('data-panel',JSON.stringify(step.source));
    await expect(page.locator('.source-pane')).toContainText(`Main step ${step.main_step_number}`);
    const quantities=await page.locator('.parts-table tbody tr td:last-child').allTextContents();
    expect(quantities.reduce((sum,value)=>sum+Number(value.replace('×','')),0)).toBe(step.introduced_instance_ids.length);
    seen.push(step.step_id);
    if([2,4,10].includes(i))await page.screenshot({path:`${evidence}/instruction-${i+1}.png`,fullPage:true});
  }
  await expect(page.getByText('Playback complete · all instructions shown',{exact:true})).toBeVisible({timeout:8000});
  expect(Date.now()-started).toBeGreaterThan(40000);
  await button(page,'Reset view').click();expect(final.equals(await canvas.screenshot(modelOnly))).toBe(true);
  await page.screenshot({path:`${evidence}/complete.png`,fullPage:true});
  await writeFile(`${evidence}/complete-run.json`,JSON.stringify({revision:scene.revision,seen,elapsedMs:Date.now()-started,errors},null,2));
  expect(errors).toEqual([]);
  await page.reload();await button(page,'Find my set').click();await button(page,'Open tutorial').click();
  await expect(page.getByLabel('Jump to instruction')).toHaveValue(String(scene.steps.length-1));
  await expect(button(page,'Pause build')).toHaveCount(0);
});
test('stop, seek and normal replay cancel autoplay; controls work on a phone',async({page})=>{
  await page.setViewportSize({width:390,height:844});await open(page);
  await button(page,'Play full build').click();await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','playing');
  await button(page,'Stop build').click();await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','idle');
  await page.waitForTimeout(3100);await expect(page.getByLabel('Jump to instruction')).toHaveValue('0');
  await button(page,'Play full build').click();await page.getByLabel('Jump to instruction').selectOption('10');
  await expect(button(page,'Pause build')).toHaveCount(0);await page.waitForTimeout(3100);await expect(page.getByLabel('Jump to instruction')).toHaveValue('10');
  await button(page,'Replay').click();await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','playing');
  await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','idle',{timeout:2000});
  await expect(page.getByLabel('Jump to instruction')).toHaveValue('10');
  await button(page,'Play full build').click();await expect(page.getByLabel('Jump to instruction')).toHaveValue('0');
  await button(page,'Pause build').click();await mkdir(evidence,{recursive:true});await page.screenshot({path:`${evidence}/phone.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await button(page,'Next').click();await expect(button(page,'Pause build')).toHaveCount(0);await expect(page.getByLabel('Jump to instruction')).toHaveValue('1');
});
test('reduced motion advances snapshots without moving pieces',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});await open(page);await button(page,'Play full build').click();
  await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','idle');
  await expect(page.getByLabel('Jump to instruction')).toHaveValue('1',{timeout:4000});
  await button(page,'Pause build').click();await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','idle');
  const instruction=await page.getByLabel('Jump to instruction').inputValue();await page.waitForTimeout(1300);await expect(page.getByLabel('Jump to instruction')).toHaveValue(instruction);
  await button(page,'Stop build').click();
});
