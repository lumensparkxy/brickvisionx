// Exclude floating UI from pixel comparisons: these checks measure the 3D renderer.
const modelOnly = {style: '.camera-controls,.model-caption,.gesture-hint,.placement-note {visibility:hidden!important}'};
import { test, expect, type Page } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';

const evidence = 'var/evidence/camera-controls';
// Measure the actual rendered silhouette, not merely whether two screenshots differ.
async function silhouette(page: Page, name?: string) {
  const png = await page.locator('.viewport canvas').screenshot(name ? {...modelOnly,path:`${evidence}/${name}.png`} : modelOnly);
  return page.evaluate(async base64 => {
    const image = new Image(); image.src = `data:image/png;base64,${base64}`; await image.decode();
    const canvas = document.createElement('canvas'); canvas.width=image.width; canvas.height=image.height;
    const context=canvas.getContext('2d')!; context.drawImage(image,0,0);
    const {data}=context.getImageData(0,0,canvas.width,canvas.height);
    let count=0,xSum=0,minX=canvas.width,maxX=0,minY=canvas.height,maxY=0;
    for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++){
      const i=(y*canvas.width+x)*4;
      if(Math.abs(data[i]-data[0])+Math.abs(data[i+1]-data[1])+Math.abs(data[i+2]-data[2])>45){
        count++; xSum+=x; minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);
      }
    }
    return {count, x: xSum/count, width:canvas.width,height:canvas.height,minX,maxX,minY,maxY};
  }, png.toString('base64'));
}
function visible(s: Awaited<ReturnType<typeof silhouette>>) {
  expect(s.count).toBeGreaterThan(100);
  expect(s.minX).toBeGreaterThan(0); expect(s.maxX).toBeLessThan(s.width-1);
  expect(s.minY).toBeGreaterThan(0); expect(s.maxY).toBeLessThan(s.height-1);
}
test('camera buttons preserve the model, reverse, and work after drag and scroll', async({page}) => {
  test.setTimeout(180000); // Real geometry plus >80 deliberately sequential toolbar interactions.
  await mkdir(evidence,{recursive:true}); await page.setViewportSize({width:1440,height:1000});
  await page.goto('/'); await page.getByRole('button',{name:'Find my set',exact:true}).click();
  await page.getByRole('button',{name:'Open tutorial',exact:true}).click();
  await expect(page.locator('.viewport canvas')).toBeVisible();
  await page.getByText('Loading individual part geometry…').waitFor({state:'hidden',timeout:30000});
  await page.getByLabel('Jump to instruction').selectOption('15');
  const button=(name:string)=>page.getByRole('button',{name,exact:true});
  const baseline=await silhouette(page,'reset'); visible(baseline);
  const measurements:Record<string,unknown>={baseline};
  for(const name of ['Rotate left','Rotate right','Zoom in','Zoom out','Pan left','Pan right']){
    await button(name).click(); const s=await silhouette(page,name.replaceAll(' ','-')); visible(s); measurements[name]=s;
    if(name==='Zoom in')expect(s.count).toBeGreaterThan(baseline.count*1.3);
    if(name==='Zoom out')expect(s.count).toBeLessThan(baseline.count*.8);
    if(name==='Pan left')expect(s.x-baseline.x).toBeGreaterThan(s.width*.08);
    if(name==='Pan right')expect(baseline.x-s.x).toBeGreaterThan(s.width*.08);
    await button('Reset view').click();
  }
  const original=await page.locator('.viewport canvas').screenshot(modelOnly);
  for(const [a,b] of [['Rotate left','Rotate right'],['Zoom in','Zoom out'],['Pan left','Pan right']]){
    await button(a).click(); await button(b).click();
    expect(original.equals(await page.locator('.viewport canvas').screenshot(modelOnly))).toBe(true);
  }
  for(let i=0;i<24;i++)await button('Rotate left').click(); visible(await silhouette(page,'repeated-rotation'));
  await button('Reset view').click();
  const bounds=(await page.locator('.viewport canvas').boundingBox())!;
  await page.mouse.move(bounds.x+bounds.width/2,bounds.y+bounds.height/2);
  await page.mouse.down(); await page.mouse.move(bounds.x+bounds.width/2+70,bounds.y+bounds.height/2+20,{steps:6}); await page.mouse.up();
  await button('Rotate right').click(); visible(await silhouette(page,'after-drag'));
  const stopped=await page.locator('.viewport canvas').screenshot(modelOnly); await page.waitForTimeout(400);
  expect(stopped.equals(await page.locator('.viewport canvas').screenshot(modelOnly))).toBe(true);
  await page.mouse.move(bounds.x+bounds.width/2,bounds.y+bounds.height/2); await page.mouse.wheel(0,120);
  await button('Zoom in').click(); visible(await silhouette(page,'after-scroll'));
  await button('Pan left').click(); visible(await silhouette(page,'after-scroll-pan'));
  await button('Reset view').click(); expect(original.equals(await page.locator('.viewport canvas').screenshot(modelOnly))).toBe(true);
  // At either zoom limit additional clicks must stop, never cross the target or lose the model.
  for(const name of ['Zoom in','Zoom out']) {
    for(let i=0;i<30;i++)await button(name).click();
    expect((await silhouette(page)).count).toBeGreaterThan(100);
    const limited=await page.locator('.viewport canvas').screenshot(modelOnly); await button(name).click();
    expect(limited.equals(await page.locator('.viewport canvas').screenshot(modelOnly))).toBe(true);
  }
  await button('Reset view').click();
  // Reset must also cancel an in-flight right-drag pan, not drift away afterward.
  await page.mouse.move(bounds.x+bounds.width/2,bounds.y+bounds.height/2);
  await page.mouse.down({button:'right'}); await page.mouse.move(bounds.x+bounds.width/2+50,bounds.y+bounds.height/2,{steps:4}); await page.mouse.up({button:'right'});
  await button('Reset view').click(); await page.waitForTimeout(400);
  expect(original.equals(await page.locator('.viewport canvas').screenshot(modelOnly))).toBe(true);
  await page.screenshot({path:`${evidence}/repaired-toolbar.png`,fullPage:true});
  await writeFile(`${evidence}/measurements.json`,JSON.stringify(measurements,null,2));
});
