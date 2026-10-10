// Exclude floating UI from pixel comparisons: these checks measure the 3D renderer.
const modelOnly = {style: '.camera-controls,.model-caption,.gesture-hint,.placement-note {visibility:hidden!important}'};
import {test,expect,type Page} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
const evidence='var/evidence/placement';
async function redPosition(page:Page,name:string){
  const bytes=await page.screenshot({...modelOnly,clip:(await page.locator('.viewport canvas').boundingBox())!,path:`${evidence}/${name}.png`});
  return page.evaluate(async base64=>{
    const image=new Image();image.src=`data:image/png;base64,${base64}`;await image.decode();
    const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
    const ctx=canvas.getContext('2d')!;ctx.drawImage(image,0,0);const {data}=ctx.getImageData(0,0,canvas.width,canvas.height);
    let count=0,sumY=0;for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++){
      const i=(y*canvas.width+x)*4;if(data[i]>70&&data[i]>data[i+1]*1.6&&data[i]>data[i+2]*1.6){count++;sumY+=y;}
    }return{count,y:sumY/count};
  },bytes.toString('base64'));
}
test('instruction 9 red plates approach from underneath, and all steps have an explicit motion outcome',async({page})=>{
  test.setTimeout(60000);await mkdir(evidence,{recursive:true});await page.setViewportSize({width:1440,height:1100});
  await page.clock.install({time:new Date('2026-10-03T10:00:00Z')});
  await page.goto('/');await page.getByRole('button',{name:'Find my set',exact:true}).click();await page.getByRole('button',{name:'Open tutorial',exact:true}).click();
  await expect(page.getByRole('button',{name:'Play full build',exact:true})).toBeEnabled({timeout:30000});
  await page.getByLabel('Jump to instruction').selectOption('8');
  await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','idle');
  // Freeze real rendered motion at a known frame; screenshot latency must not consume the replay.
  await page.clock.pauseAt(new Date('2026-10-03T11:00:00Z'));
  const final=await redPosition(page,'instruction-9-final');
  await page.getByRole('button',{name:'Replay',exact:true}).click();
  await page.clock.runFor(100);
  const moving=await redPosition(page,'instruction-9-underneath');
  await expect(page.locator('.viewport')).toHaveAttribute('data-placement-mode','translate');
  await expect(page.locator('.viewport')).toHaveAttribute('data-placement-reason','below');
  expect(moving.count).toBeGreaterThan(100);expect(moving.y).toBeGreaterThan(final.y+8);
  await page.clock.resume();
  await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','idle');
  const settled=await redPosition(page,'instruction-9-settled');expect(settled).toEqual(final);
  const outcomes=[];
  for(let index=0;index<16;index++){
    await page.getByLabel('Jump to instruction').selectOption(String(index));
    await page.getByRole('button',{name:'Replay',exact:true}).click();
    await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','playing');
    const mode=await page.locator('.viewport').getAttribute('data-placement-mode');const reason=await page.locator('.viewport').getAttribute('data-placement-reason');
    expect(['translate','preview']).toContain(mode);
    if([4,7,8].includes(index))expect(['below','blocked_approach']).toContain(await page.locator('.viewport').getAttribute('data-approach-reason'));
    outcomes.push({instruction:index+1,mode,reason});
    await expect(page.locator('.viewport')).toHaveAttribute('data-animation-state','idle');
  }
  await writeFile(`${evidence}/audit.json`,JSON.stringify({final,moving,settled,outcomes},null,2));
});
