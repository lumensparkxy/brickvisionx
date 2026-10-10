// Exclude floating UI from pixel comparisons: these checks measure the 3D renderer.
const modelOnly = {style: '.camera-controls,.model-caption,.gesture-hint,.placement-note {visibility:hidden!important}'};
import {test,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
const evidence='var/evidence/browser';
test('real backend lookup, malformed input, unsupported set and provider boundary',async({page})=>{
  await mkdir(evidence,{recursive:true});await page.setViewportSize({width:1440,height:900});await page.goto('/');await page.screenshot({path:`${evidence}/lookup-desktop.png`,fullPage:true});
  const invalid=await page.request.get('/api/v1/sets/x');expect(invalid.status()).toBe(422);expect((await invalid.json()).detail.code).toBe('invalid_set_number');
  const unsupported=await page.request.get('/api/v1/sets/12345');expect(unsupported.status()).toBe(404);expect((await unsupported.json()).detail.code).toBe('unsupported_set');
  const field=page.getByRole('combobox',{name:'Your set number'});
  await expect(field.locator('option[value="x"],option[value="12345"]')).toHaveCount(0);
  await field.selectOption('30669');await page.getByRole('button',{name:'Find my set'}).click();await expect(page.getByRole('heading',{name:'30669 · Iconic Red Plane'})).toBeVisible();
  await expect(page.locator('input[type=file]')).toHaveCount(0);await page.screenshot({path:`${evidence}/source-found-desktop.png`,fullPage:true});
  const unavailable=await page.request.post('/api/v1/conversions',{headers:{'Idempotency-Key':`e2e-auto-${Date.now()}`},data:{set_number:'30669',guide_id:'alt-02',mode:'automated'}});expect(unavailable.status()).toBe(503);expect((await unavailable.json()).detail.code).toBe('provider_unavailable');
});
test('real source candidate workspace, navigation, camera, callouts and review',async({page})=>{
  test.setTimeout(90000); // Captures all 16 real steps, camera reversals and viewer reopen cycles.
  const status=await page.request.get('/api/v1/sets/30669/guides/alt-02/status');const info=await status.json();
  expect(info.latest_candidate_revision,'The reference project requires the recorded PDF-assisted scene and source/part cache.').toBeTruthy();
  await mkdir(evidence,{recursive:true});await page.setViewportSize({width:1440,height:900});await page.goto('/');
  const runtimeErrors:string[]=[];page.on('pageerror',e=>runtimeErrors.push(e.message));
  await page.getByRole('button',{name:'Find my set'}).click();const loadStart=Date.now();await page.getByRole('button',{name:'Open tutorial',exact:true}).click();
  await expect(page.locator('.candidate-status')).toContainText('PDF-assisted · needs review');await expect(page.locator('.candidate-banner')).toHaveCount(0);await page.locator('.provenance summary').click();await expect(page.locator('.provenance')).toContainText('not an automatic PDF conversion');await expect(page.locator('.provenance')).toContainText('16 instructions · 32 physical pieces');await page.locator('.provenance summary').click();await expect(page.getByText('Loading individual part geometry…')).toBeHidden({timeout:30000});
  await expect(page.locator('.viewport-message.error')).toHaveCount(0);await expect(page.locator('.source-crop canvas')).toBeVisible();
  const cachedLoadMs=Date.now()-loadStart;
  await page.screenshot({path:`${evidence}/early-assembly-desktop.png`,fullPage:true});
  const modelCanvas=page.locator('.viewport canvas');const originalRender=await modelCanvas.screenshot(modelOnly);
  for(const name of ['Rotate left','Zoom in','Pan left']){
    await page.getByRole('button',{name,exact:true}).click();
    await expect.poll(async()=>originalRender.equals(await modelCanvas.screenshot(modelOnly))).toBe(false);
    await page.getByRole('button',{name:'Reset view',exact:true}).click();
    await expect.poll(async()=>originalRender.equals(await modelCanvas.screenshot(modelOnly))).toBe(true);
  }
  for(const name of ['Rotate right','Zoom out','Pan right'])await page.getByRole('button',{name,exact:true}).click();
  await page.getByRole('button',{name:'Reset view',exact:true}).click();
  await page.getByRole('button',{name:'Next',exact:true}).click();await page.getByRole('button',{name:'Previous',exact:true}).click();
  const scene=await (await page.request.get(`/api/v1/reconstructions/${info.latest_candidate_revision}/scene`)).json();
  await mkdir(`${evidence}/steps`,{recursive:true});
  await writeFile(`${evidence}/steps/revision.json`,JSON.stringify({revision:scene.revision,source_sha256:scene.source_sha256,step_ids:scene.steps.map((s:{step_id:string})=>s.step_id)},null,2));
  for(let i=0;i<scene.steps.length;i++){
    const step=scene.steps[i];await page.getByLabel('Jump to instruction').selectOption(String(i));
    await expect(page.locator('.source-pane')).toContainText(`Main step ${step.main_step_number}`);
    await expect(page.locator('.source-link')).toHaveAttribute('href',`/api/v1/sources/${scene.source_sha256}/pages/${step.source.page_index}`);
    await expect(page.locator('.viewport')).toHaveAttribute('data-step-id',step.step_id);
    const quantities=await page.locator('.parts-table tbody tr td:last-child').allTextContents();
    expect(quantities.reduce((sum,value)=>sum+Number(value.replace('×','')),0)).toBe(step.introduced_instance_ids.length);
    await expect(page.locator('.source-crop canvas')).toHaveAttribute('data-panel',JSON.stringify(step.source));
    await page.locator('.workspace-grid').screenshot({path:`${evidence}/steps/${String(i+1).padStart(2,'0')}-${step.step_id}.png`});
  }
  for(const [action,name] of [['build_subassembly','detached-callout'],['attach_subassembly','attached-callout']] as const){const i=scene.steps.findIndex((s:{action:string})=>s.action===action);if(i>=0){await page.getByLabel('Jump to instruction').selectOption(String(i));const snapshot=await modelCanvas.screenshot(modelOnly);await page.getByRole('button',{name:'Replay',exact:false}).click();await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','playing');await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','idle');expect(snapshot.equals(await modelCanvas.screenshot(modelOnly))).toBe(true);await page.screenshot({path:`${evidence}/${name}-desktop.png`,fullPage:true});}}
  await page.getByRole('button',{name:'Review candidate',exact:true}).click();await expect(page.getByRole('region',{name:'Reconstruction review'})).toBeVisible();await page.screenshot({path:`${evidence}/review-desktop.png`,fullPage:true});
  await page.getByRole('button',{name:'Close review',exact:true}).click();await page.getByLabel('Jump to instruction').selectOption(String(scene.steps.length-1));await page.screenshot({path:`${evidence}/final-candidate-desktop.png`,fullPage:true});
  await page.setViewportSize({width:390,height:844});await expect.poll(async()=>{const view=await page.locator('.viewport').boundingBox();const nav=await page.locator('.step-navigation').boundingBox();return !!view&&!!nav&&view.y+view.height<=nav.y;}).toBe(true);await page.screenshot({path:`${evidence}/candidate-phone.png`,fullPage:true});
  for(const name of ['Guide','Pieces','3D'])await page.getByRole('tab',{name,exact:true}).click();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.reload();await page.getByRole('button',{name:'Find my set'}).click();await page.getByRole('button',{name:'Open tutorial',exact:true}).click();await expect(page.getByLabel('Jump to instruction')).toHaveValue(String(scene.steps.length-1));
  await expect(page.getByText('Loading individual part geometry…')).toBeHidden({timeout:30000});
  const reopenGeometryCounts:number[]=[];
  for(let i=0;i<3;i++){
    await expect(page.locator('.viewport')).toHaveAttribute('data-geometry-count',/^[1-9]/);
    reopenGeometryCounts.push(Number(await page.locator('.viewport').getAttribute('data-geometry-count')));
    await page.getByRole('button',{name:'Back to set',exact:false}).click();await page.getByRole('button',{name:'Open tutorial',exact:true}).click();
    await expect(page.getByText('Loading individual part geometry…')).toBeHidden({timeout:30000});
  }
  const frameTimes=await page.evaluate(()=>new Promise<number[]>(resolve=>{const times:number[]=[];let previous=performance.now();const sample=(t:number)=>{times.push(t-previous);previous=t;if(times.length<90)requestAnimationFrame(sample);else resolve(times);};requestAnimationFrame(sample);}));
  const fps=1000/(frameTimes.slice(1).reduce((a,b)=>a+b,0)/(frameTimes.length-1));
  await writeFile(`${evidence}/performance.json`,JSON.stringify({cachedLoadMs,requestAnimationFrameFps:fps,reopenGeometryCounts,note:'Chromium headless local browser. Frame cadence is not a GPU benchmark; per-renderer resource counts do not measure total GPU memory.',browser:await page.evaluate(()=>navigator.userAgent)},null,2));
  expect(new Set(reopenGeometryCounts).size).toBe(1);expect(runtimeErrors).toEqual([]);
});
