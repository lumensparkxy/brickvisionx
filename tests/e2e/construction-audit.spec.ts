import {test,expect,type Page} from '@playwright/test';
import {existsSync,readFileSync} from 'node:fs';
import {mkdir,writeFile} from 'node:fs/promises';

// Opt-in: real privately staged candidates + official source + individual geometry.
// A passing renderer test never establishes complete-booklet or reconstruction correctness.
const enabled=process.env.RUN_CONSTRUCTION_AUDIT==='1';
const caseFile=process.env.CONSTRUCTION_CASES??'var/evidence/ten-set-construction/staged-cases.json';
const cases:Case[]=enabled&&existsSync(caseFile)?JSON.parse(readFileSync(caseFile,'utf8')).cases:[];
const baseURL=process.env.CONSTRUCTION_URL??'http://127.0.0.1:5174';
const evidence=process.env.CONSTRUCTION_EVIDENCE??'var/evidence/ten-set-construction/browser';
const headed=process.env.CONSTRUCTION_HEADED==='1';
test.use({baseURL,headless:!headed,viewport:{width:1440,height:900}});
type Case={set_number:string;guide_id:string;revision:string;steps:number;instances:number;coverage_status:string;covers_full_selected_booklet:boolean};
const summary=(values:number[])=>{const sorted=[...values].sort((a,b)=>a-b);return{samples:values.length,p50:sorted[Math.floor(sorted.length*.5)]??null,p95:sorted[Math.floor(sorted.length*.95)]??null};};
const audits=(page:Page)=>page.evaluate(()=>JSON.parse(JSON.stringify((window as any).__guide2buildRendererAudits??[])));
for(const entry of cases){
 test(`${entry.set_number}/${entry.guide_id}: actual reconstruction candidate renderer`,async({page,browser})=>{
  test.setTimeout(180000);
  const dir=`${evidence}/${entry.set_number}-${entry.guide_id}`;await mkdir(dir,{recursive:true});
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  const set=await (await page.request.get(`/api/v1/sets/${entry.set_number}`)).json();
  const guide=set.guides.find((g:any)=>g.guide_id===entry.guide_id);expect(guide?.tutorial_available).toBe(true);
  const status=await(await page.request.get(`/api/v1/sets/${entry.set_number}/guides/${entry.guide_id}/status`)).json();
  const scene=await(await page.request.get(`/api/v1/reconstructions/${status.latest_candidate_revision}/scene`)).json();
  expect(scene.revision).toBe(entry.revision);
  const cdp=await page.context().newCDPSession(page);await cdp.send('Network.enable');await cdp.send('Network.clearBrowserCache');
  async function open(){
   await page.goto('/?benchmark=1');await page.getByLabel('Your set number').selectOption(entry.set_number);
   const start=await page.evaluate(()=>performance.now());
   await page.getByRole('button',{name:'Find my set',exact:true}).click();
   await page.locator('.guide-row').filter({has:page.getByText(guide.label,{exact:true})}).getByRole('button',{name:'Open tutorial',exact:true}).click();
   await expect(page.getByRole('button',{name:'Play full build',exact:true})).toBeEnabled({timeout:60000});
   await expect.poll(async()=>{const a=(await audits(page)).at(-1);return Boolean(a?.readyAtMs&&a.samples.some((s:any)=>s.phase==='viewport'&&s.atMs>=a.readyAtMs));}).toBe(true);
   await expect(page.locator('.viewport-message.error')).toHaveCount(0);
   return(await page.evaluate(()=>performance.now()))-start;
  }
  const coldMs=await open();const warmMs=await open();
  const checkpoints=[];
  for(let index=0;index<scene.steps.length;index++){
   const step=scene.steps[index];await page.getByLabel('Jump to instruction').selectOption(String(index));
   await expect(page.locator('.viewport')).toHaveAttribute('data-step-id',step.step_id);
   await expect(page.locator('.source-crop canvas')).toHaveAttribute('data-panel',JSON.stringify(step.source));
   await expect.poll(async()=>(await audits(page)).at(-1)?.samples.at(-1)?.stepId).toBe(step.step_id);
   const quantities=await page.locator('.parts-table tbody tr td:last-child').allTextContents();
   expect(quantities.reduce((sum,q)=>sum+Number(q.replace('×','')),0)).toBe(step.introduced_instance_ids.length);
   await page.locator('.workspace-grid').screenshot({path:`${dir}/step-${String(index+1).padStart(3,'0')}.png`});
   checkpoints.push({step_id:step.step_id,main_step:step.main_step_number,instances:step.visible_instance_ids.length});
  }
  await page.getByRole('button',{name:'Replay',exact:true}).click();
  await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','playing');
  await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','idle',{timeout:10000});
  const box=(await page.locator('.viewport canvas').boundingBox())!;
  await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();
  const from=await page.evaluate(()=>performance.now());const wall=Date.now();
  while(Date.now()-wall<3000){const angle=(Date.now()-wall)/400;await page.mouse.move(box.x+box.width*(.5+.12*Math.sin(angle)),box.y+box.height*(.5+.12*Math.cos(angle)));await page.waitForTimeout(16);}
  await page.mouse.up();const until=await page.evaluate(()=>performance.now());const audit=(await audits(page)).at(-1);
  const orbit=audit.samples.filter((s:any)=>s.phase==='viewport'&&s.atMs>=from&&s.atMs<=until);
  const last=audit.samples.filter((s:any)=>s.phase==='viewport').at(-1);
  await page.screenshot({path:`${dir}/final-desktop.png`,fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.getByRole('tab',{name:'3D',exact:true}).click();
  await expect(page.locator('.viewport')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`${dir}/final-phone.png`,fullPage:true});
  await page.getByRole('button',{name:'Back to set lookup',exact:true}).click();
  const disposed=(await audits(page)).find((a:any)=>a.disposedAtMs&&a.identity.revision===entry.revision);
  const report={recorded_at:new Date().toISOString(),case:entry,scene_revision:scene.revision,source_sha256:scene.source_sha256,browser:browser.version(),headed,hardware:audit.hardware,
   scope:'Measured only the actual partial candidate coverage shown; not full-set complexity or assembly correctness.',cold_find_to_usable_ms:coldMs,warm_find_to_usable_ms:warmMs,checkpoints,
   final_main_pass:{draw_calls:last?.calls,triangles:last?.triangles,lines:last?.lines,geometries:last?.geometries,textures:last?.textures},
   orbit:{actual_render_fps:orbit.length*1000/(until-from),duration_ms:until-from,cpu_submit_ms:summary(orbit.map((s:any)=>s.cpuSubmitMs))},gpu_mixed_workload_ms:summary(audit.gpuMs),gpu_discarded:audit.gpuDiscarded,
   disposed_resources:disposed?.disposedResources,errors,raw_audit:audit,limitations:['Local development build and loopback network.','Cold refers to browser HTTP cache; source and part assets are prepared on server.','Phone layout only, not physical-phone GPU.','GPU queries cover mixed rendering, not browser composition.','Main-pass counters exclude shadow passes.','Partial candidate geometry correctness is reviewed separately.']};
  await writeFile(`${dir}/renderer.json`,JSON.stringify(report,null,2));expect(errors).toEqual([]);
 });
}
if(!enabled)test('actual reconstruction candidate audit is opt-in',()=>test.skip(true,'Requires separately staged actual source-derived candidates.'));
