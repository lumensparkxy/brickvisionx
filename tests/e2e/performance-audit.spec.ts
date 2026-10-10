import {test,expect,type Page} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';

// Run explicitly, in isolation: RUN_RENDERER_AUDIT=1 npm run test:e2e -- tests/e2e/performance-audit.spec.ts --workers=1
// This audits the real local PDF-assisted candidate. It is not an automatic reconstruction or a ten-set scaling test.
const evidence=process.env.GUIDE2BUILD_BENCHMARK_EVIDENCE??'var/evidence/ten-set-release/performance';
const enabled=process.env.RUN_RENDERER_AUDIT==='1';
const benchmarkURL=process.env.GUIDE2BUILD_BENCHMARK_URL??'http://127.0.0.1:5173';
test.use({baseURL:benchmarkURL,headless:process.env.GUIDE2BUILD_BENCHMARK_HEADED!=='1'});
type Sample={atMs:number;phase:string;stepId:string;cpuSubmitMs:number;calls:number;triangles:number;lines:number;geometries:number;textures:number};
type Audit={identity:unknown;startedAtMs:number;readyAtMs:number|null;disposedAtMs:number|null;samples:Sample[];gpuMs:number[];gpuDiscarded:number;hardware:Record<string,unknown>;phases:Record<string,number>;disposedResources:Record<string,number>|null};
const quantile=(values:number[],q:number)=>values.length?[...values].sort((a,b)=>a-b)[Math.min(values.length-1,Math.floor(values.length*q))]:null;
const statistics=(values:number[])=>({samples:values.length,p50:quantile(values,.5),p95:quantile(values,.95),max:values.length?Math.max(...values):null});
async function audits(page:Page):Promise<Audit[]>{return page.evaluate(()=>JSON.parse(JSON.stringify((window as any).__guide2buildRendererAudits??[])));}
async function ready(page:Page){
  await expect(page.getByRole('button',{name:'Play full build',exact:true})).toBeEnabled({timeout:45000});
  await expect.poll(async()=>{const audit=(await audits(page)).at(-1);return Boolean(audit?.readyAtMs&&audit.samples.some(s=>s.phase==='viewport'&&s.atMs>=audit.readyAtMs!));}).toBe(true);
}
async function openFromLanding(page:Page){
  const started=await page.evaluate(()=>performance.now());
  await page.getByRole('button',{name:'Find my set',exact:true}).click();
  await page.getByRole('button',{name:'Open tutorial',exact:true}).click();await ready(page);
  return {interactionToUsableMs:(await page.evaluate(()=>performance.now()))-started,audit:(await audits(page)).at(-1)!};
}
for(const profile of [{name:'desktop',width:1440,height:900,deviceScaleFactor:1,isMobile:false,hasTouch:false},{name:'phone-emulation',width:390,height:844,deviceScaleFactor:2,isMobile:true,hasTouch:true}]){
  test(`${profile.name}: real 30669 renderer performance audit`,async({browser})=>{
    test.skip(!enabled,'Opt-in hardware-sensitive audit; run alone with RUN_RENDERER_AUDIT=1.');test.setTimeout(240000);
    await mkdir(evidence,{recursive:true});
    const context=await browser.newContext({viewport:{width:profile.width,height:profile.height},deviceScaleFactor:profile.deviceScaleFactor,isMobile:profile.isMobile,hasTouch:profile.hasTouch});
    const page=await context.newPage();const errors:string[]=[];const failedRequests:string[]=[];
    page.on('pageerror',error=>errors.push(error.message));page.on('requestfailed',request=>failedRequests.push(`${request.url()}: ${request.failure()?.errorText}`));
    const cdp=await context.newCDPSession(page);await cdp.send('Network.enable');await cdp.send('Network.clearBrowserCache');
    await page.goto(`${benchmarkURL}/?benchmark=1`);const cold=await openFromLanding(page);
    const coldResources=await page.evaluate(()=>performance.getEntriesByType('resource').map(e=>{const r=e as PerformanceResourceTiming;return{name:r.name,duration:r.duration,transferSize:r.transferSize,encodedBodySize:r.encodedBodySize};}));
    // Same context and normal HTTP cache, with the server's existing PDF/reconstruction/part cache in both loads.
    await page.reload();const warm=await openFromLanding(page);
    const steps=[];
    for(let index=0;index<16;index++){
      await page.getByLabel('Jump to instruction').selectOption(String(index));
      const viewport=page.locator('.viewport');const stepId=await viewport.getAttribute('data-step-id');
      await expect.poll(async()=>{const a=(await audits(page)).at(-1)!;return a.samples.at(-1)?.stepId;}).toBe(stepId);
      const before=(await audits(page)).at(-1)!.samples.length;
      await page.getByRole('button',{name:'Replay',exact:true}).click();
      await expect(viewport).toHaveAttribute('data-animation-state','playing');
      await expect(viewport).toHaveAttribute('data-animation-state','idle',{timeout:10000});
      const actual=(await audits(page)).at(-1)!.samples.slice(before).filter(s=>s.phase==='viewport');
      expect(actual.length).toBeGreaterThan(1);
      steps.push({index:index+1,stepId,mode:await viewport.getAttribute('data-placement-mode'),reason:await viewport.getAttribute('data-placement-reason'),renderCount:actual.length,cpuSubmitMs:statistics(actual.map(s=>s.cpuSubmitMs)),lastRender:actual.at(-1)});
      if([0,2,4,15].includes(index))await page.screenshot({path:`${evidence}/${profile.name}-instruction-${index+1}.png`,fullPage:true});
    }
    // Measure actual render timestamps while a mouse drag actively orbits. This is neither idle RAF nor physical touch-device FPS.
    const box=(await page.locator('.viewport canvas').boundingBox())!;
    const startOrbit=await page.evaluate(()=>performance.now());
    await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();
    const orbitWallStart=Date.now();let moves=0;
    while(Date.now()-orbitWallStart<4000){const angle=(Date.now()-orbitWallStart)/400;await page.mouse.move(box.x+box.width*(.5+.16*Math.sin(angle)),box.y+box.height*(.5+.12*Math.cos(angle)));moves++;await page.waitForTimeout(16);}
    await page.mouse.up();const endOrbit=await page.evaluate(()=>performance.now());
    const orbit=(await audits(page)).at(-1)!.samples.filter(s=>s.phase==='viewport'&&s.atMs>=startOrbit&&s.atMs<=endOrbit);
    const intervals=orbit.slice(1).map((s,i)=>s.atMs-orbit[i].atMs);
    // Damping is frame-based; a fixed two-second pause is not a stationary camera on slow software renderers.
    const settleStarted=await page.evaluate(()=>performance.now());let stablePolls=0;let previousCount=-1;
    while(stablePolls<2 && (await page.evaluate(()=>performance.now()))-settleStarted<20000){
      await page.waitForTimeout(250);const count=await page.evaluate(()=>(window as any).__guide2buildRendererAudits.at(-1).samples.length);
      stablePolls=count===previousCount?stablePolls+1:0;previousCount=count;
    }
    const dampingSettleMs=(await page.evaluate(()=>performance.now()))-settleStarted;
    const beforeIdle=(await audits(page)).at(-1)!.samples.length;
    const idleStart=await page.evaluate(()=>performance.now());await page.waitForTimeout(1500);
    const idleEnd=await page.evaluate(()=>performance.now());const afterIdle=(await audits(page)).at(-1)!.samples.length;
    const fullAudit=(await audits(page)).at(-1)!;
    const cycles=[];
    for(let i=0;i<5;i++){
      await page.getByRole('button',{name:'Back to set lookup',exact:true}).click();
      const disposed=(await audits(page)).filter(a=>a.readyAtMs&&a.disposedAtMs).at(-1)!;
      expect(disposed.disposedResources).toEqual({geometries:0,textures:0});
      await page.getByRole('button',{name:'Open tutorial',exact:true}).click();await ready(page);
      await page.getByLabel('Jump to instruction').selectOption('15');await page.waitForTimeout(250);
      const audit=(await audits(page)).at(-1)!;
      cycles.push({cycle:i+1,assemblyPreparationMs:audit.readyAtMs!-audit.startedAtMs,firstUsableFrameMs:audit.samples.find(s=>s.phase==='viewport'&&s.atMs>=audit.readyAtMs!)!.atMs-audit.startedAtMs,lastRender:audit.samples.filter(s=>s.phase==='viewport').at(-1),previousDisposedResources:disposed.disposedResources,canvasCount:await page.locator('.viewport canvas').count()});
      expect(cycles.at(-1)!.canvasCount).toBe(1);
    }
    const memoryCounts=cycles.map(c=>[c.lastRender?.geometries,c.lastRender?.textures]);expect(new Set(memoryCounts.map(JSON.stringify)).size).toBe(1);
    await page.getByRole('button',{name:'Back to set lookup',exact:true}).click();
    const report={recordedAt:new Date().toISOString(),profile,headless:process.env.GUIDE2BUILD_BENCHMARK_HEADED!=='1',benchmarkURL,appMode:process.env.GUIDE2BUILD_BENCHMARK_MODE??'development',browserVersion:browser.version(),source:'real local 30669/alt-02 PDF-assisted candidate; existing server-side source, part and reconstruction caches',
      limitations:['Phone is Chromium viewport/DPR/touch emulation on the same host, not phone GPU hardware.','Draw calls, triangles and lines are main-pass-only Three.js counters (shadow pass resets are excluded).','CPU submission is not GPU execution or presentation latency. GPU query samples cover WebGL rendering, not browser composition.','Resource counts and explicit disposal do not measure VRAM bytes or prove absence of all driver/browser leaks.','Orbit rate includes browser scheduling and automation drag cadence; no vsync/presentation guarantee.','Local loopback network; no WAN/CDN/public-hosting latency measured.'],
      cold:{interactionToUsableMs:cold.interactionToUsableMs,assemblyPreparationMs:cold.audit.readyAtMs!-cold.audit.startedAtMs,firstUsableFrameMs:cold.audit.samples.find(s=>s.phase==='viewport'&&s.atMs>=cold.audit.readyAtMs!)!.atMs-cold.audit.startedAtMs,phases:cold.audit.phases},warm:{interactionToUsableMs:warm.interactionToUsableMs,assemblyPreparationMs:warm.audit.readyAtMs!-warm.audit.startedAtMs,firstUsableFrameMs:warm.audit.samples.find(s=>s.phase==='viewport'&&s.atMs>=warm.audit.readyAtMs!)!.atMs-warm.audit.startedAtMs,phases:warm.audit.phases},coldResources,steps,
      orbit:{durationMs:endOrbit-startOrbit,inputMoves:moves,actualRenders:orbit.length,actualRenderFps:orbit.length*1000/(endOrbit-startOrbit),intervalMs:statistics(intervals),cpuSubmitMs:statistics(orbit.map(s=>s.cpuSubmitMs))},
      idle:{dampingSettleMs,cameraSettled:stablePolls>=2,durationMs:idleEnd-idleStart,actualRenders:afterIdle-beforeIdle},gpuTimeMs:{workload:'Mixed initialization, thumbnails, replay and orbit; not orbit-specific',...statistics(fullAudit.gpuMs),discarded:fullAudit.gpuDiscarded,available:fullAudit.hardware.gpuTimerSupported},hardware:fullAudit.hardware,
      cycles,errors,failedRequests,rawAudit:fullAudit,allLifecycles:await audits(page)};
    await writeFile(`${evidence}/${profile.name}.json`,JSON.stringify(report,null,2));
    expect(errors).toEqual([]);expect(failedRequests).toEqual([]);expect(afterIdle-beforeIdle).toBe(0);
    await context.close();
  });
}
