import {test,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
const evidence='var/evidence/theme-consistency';
test('booklet popup traps focus, closes with Escape and fits narrow phones',async({page})=>{
  await mkdir(evidence,{recursive:true});await page.goto('/');
  for(const width of [1440,390,320]){
    await page.setViewportSize({width,height:844});
    await page.getByRole('button',{name:'Find my set',exact:true}).click();
    const dialog=page.getByRole('dialog',{name:'30669 · Iconic Red Plane'});
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('heading')).toBeFocused();
    for(let i=0;i<6;i++){await page.keyboard.press('Tab');expect(await dialog.evaluate(el=>el.contains(document.activeElement))).toBe(true);}
    await expect(dialog.getByRole('button',{name:'Open tutorial'})).toBeInViewport();
    expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
    await page.screenshot({path:`${evidence}/dialog-${width}.png`});
    await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);
    await expect(page.getByRole('button',{name:'Find my set',exact:true})).toBeFocused();
    expect(await page.evaluate(()=>document.body.style.overflow)).toBe('');
  }
});

test('Part 1, Part 2 and Attach keep controls and panels fixed at every breakpoint',async({page})=>{
  test.setTimeout(60000);await mkdir(evidence,{recursive:true});await page.goto('/');
  const response=page.waitForResponse(r=>/\/api\/v1\/(?:reconstructions\/[^/]+|sets\/30669\/guides\/alt-02)\/scene$/.test(r.url())&&r.status()===200);
  await page.getByRole('button',{name:'Try the plane tutorial'}).click();
  await expect(page.getByRole('button',{name:'Replay',exact:true})).toBeEnabled({timeout:30000});
  const reference=await (await response).json();
  const measurements=[];
  for(const width of [1440,900,390,320]){
    await page.setViewportSize({width,height:900});
    for(const index of [2,5]){
      await page.getByLabel('Jump to instruction').selectOption(String(index));
      // The baseline belongs to the newly selected main-step crop, not the previous page/load placeholder.
      await expect.poll(async()=>JSON.parse(await page.locator('.source-crop canvas').getAttribute('data-panel')??'null')).toEqual(reference.steps[index].source);
      const rects=()=>page.evaluate(()=>Object.fromEntries(['.substep-navigation','.source-pane','.model-pane','.previous-button','.next-button'].map(selector=>{const r=document.querySelector(selector)!.getBoundingClientRect();return[selector,{x:r.x,y:r.y,width:r.width,height:r.height}];})));
      const initial=await rects();
      for(const name of ['Part 2','Attach','Part 1']){
        await page.getByRole('button',{name,exact:true}).click();
        expect(await rects()).toEqual(initial);
        await expect(page.getByRole('button',{name:'Attach',exact:true})).toBeInViewport();
        // Text and the substep buttons must be readable without an internal scroll.
        expect(await page.locator('.instruction-context').evaluate(el=>el.scrollHeight<=el.clientHeight+1)).toBe(true);
      }
      measurements.push({width,index,rects:initial});
    }
    await page.screenshot({path:`${evidence}/tutorial-${width}.png`});
  }
  await writeFile(`${evidence}/stable-substeps.json`,JSON.stringify(measurements,null,2));
});

test('closing a pending tutorial restores lookup and ignores its late response',async({page})=>{
  let release!:()=>void;
  const waiting=new Promise<void>(resolve=>{release=resolve;});
  let requested!:()=>void;
  const started=new Promise<void>(resolve=>{requested=resolve;});
  await page.route('**/api/v1/sets/30669/guides/alt-02/scene',async route=>{
    requested();await waiting;await route.fulfill({status:409,json:{detail:{code:'not_ready',message:'Old delayed request'}}});
  });
  await page.goto('/');await page.getByRole('button',{name:'Find my set',exact:true}).click();
  await page.getByRole('button',{name:'Open tutorial',exact:true}).click();await started;
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'Find my set',exact:true})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Find my set',exact:true})).toBeFocused();
  await page.route('**/api/v1/sets/60400',r=>r.fulfill({status:503,json:{detail:{code:'source_unavailable',message:'The official source is temporarily unavailable.'}}}));
  await page.getByLabel('Your set number').selectOption('60400');
  await page.getByRole('button',{name:'Find my set',exact:true}).click();
  const response=page.waitForResponse('**/api/v1/sets/30669/guides/alt-02/scene');release();await response;
  await expect(page.getByRole('alert')).toContainText('temporarily unavailable');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
