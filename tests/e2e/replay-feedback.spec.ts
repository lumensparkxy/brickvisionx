import {test,expect,type Page} from '@playwright/test';
import {mkdir} from 'node:fs/promises';

const evidence='var/evidence/replay-feedback';
const modelOnly={style:'.camera-controls,.model-caption,.gesture-hint,.placement-note {visibility:hidden!important}'};
async function bluePixels(page:Page,png:Buffer){
  return page.evaluate(async base64=>{
    const image=new Image();image.src=`data:image/png;base64,${base64}`;await image.decode();
    const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
    const context=canvas.getContext('2d')!;context.drawImage(image,0,0);
    const {data}=context.getImageData(0,0,canvas.width,canvas.height);let count=0;
    for(let i=0;i<data.length;i+=4)if(data[i+2]>data[i]*1.15&&data[i+2]>data[i+1]*1.03)count++;
    return count;
  },png.toString('base64'));
}
async function open(page:Page){
  await page.goto('/');await page.getByRole('button',{name:'Find my set',exact:true}).click();
  await page.getByRole('button',{name:'Open tutorial',exact:true}).click();
  await expect(page.getByRole('button',{name:'Play full build',exact:true})).toBeEnabled({timeout:30000});
  await page.getByLabel('Jump to instruction').selectOption('2');
}
test('Step 3 replay is visible without invented movement, and substeps retain camera framing',async({page})=>{
  test.setTimeout(120000);await mkdir(evidence,{recursive:true});await page.setViewportSize({width:1440,height:1000});
  await page.clock.install({time:new Date('2026-10-03T10:00:00Z')});await open(page);
  const viewport=page.locator('.viewport');const canvas=page.locator('.viewport canvas');
  await page.clock.pauseAt(new Date('2026-10-03T11:00:00Z'));
  const framing=await viewport.getAttribute('data-camera-frame');expect(framing).toBeTruthy();
  const substeps=page.getByRole('navigation',{name:'Step 3 substeps'});
  for(const [label,reason] of [['Part 1','starting_pieces'],['Attach','blocked_approach']]){
    await substeps.getByRole('button',{name:label,exact:true}).click();await page.clock.runFor(32);
    await expect(viewport).toHaveAttribute('data-camera-frame',framing!);
    const baseline=await canvas.screenshot({...modelOnly,path:`${evidence}/${label.replace(' ','-')}-before.png`});
    const baselineBlue=await bluePixels(page,baseline);
    await page.getByRole('button',{name:'Replay',exact:true}).click();await page.clock.runFor(450);
    await expect(viewport).toHaveAttribute('data-placement-mode','highlight');
    await expect(viewport).toHaveAttribute('data-placement-reason',reason);
    await expect(viewport).toHaveAttribute('data-animation-state','playing');
    await expect(page.locator('.placement-note')).toContainText('Replay');
    const pulse=await canvas.screenshot({...modelOnly,path:`${evidence}/${label.replace(' ','-')}-pulse.png`});
    expect(await bluePixels(page,pulse)).toBeGreaterThan(baselineBlue+250);
    await page.clock.runFor(900);
    expect(await bluePixels(page,await canvas.screenshot(modelOnly))).toBeGreaterThan(baselineBlue+250);
    await page.clock.runFor(550);await expect(viewport).toHaveAttribute('data-animation-state','idle');
    expect((await canvas.screenshot(modelOnly)).equals(baseline)).toBe(true);
    await expect(viewport).toHaveAttribute('data-camera-frame',framing!);
  }
  await substeps.getByRole('button',{name:'Part 2',exact:true}).click();await page.clock.runFor(32);
  await expect(viewport).toHaveAttribute('data-camera-frame',framing!);
  await page.getByRole('button',{name:'Replay',exact:true}).click();await page.clock.runFor(100);
  await expect(viewport).toHaveAttribute('data-placement-mode','translate');
  await page.clock.runFor(800);await expect(viewport).toHaveAttribute('data-animation-state','idle');
  await page.getByRole('button',{name:'Rotate left',exact:true}).click();await page.clock.runFor(32);
  const rotated=await viewport.getAttribute('data-camera-frame');expect(rotated).not.toBe(framing);
  await substeps.getByRole('button',{name:'Attach',exact:true}).click();await page.clock.runFor(32);
  await expect(viewport).toHaveAttribute('data-camera-frame',rotated!);
  await page.getByRole('button',{name:'Reset view',exact:true}).click();await page.clock.runFor(32);
  await expect(viewport).toHaveAttribute('data-camera-frame',framing!);
});

test('Step 3 replay respects reduced motion and still explains the result',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});await open(page);
  const canvas=page.locator('.viewport canvas');const before=await canvas.screenshot(modelOnly);
  await page.getByRole('button',{name:'Replay',exact:true}).click();
  await expect(page.locator('.placement-note')).toContainText('Motion is off');
  await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','idle');
  expect((await canvas.screenshot(modelOnly)).equals(before)).toBe(true);
});
