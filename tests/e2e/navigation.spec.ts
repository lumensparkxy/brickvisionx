import {test,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
const evidence='var/evidence/navigation-position';
test('instruction 11 to 12 keeps navigation controls in place',async({page})=>{
  test.setTimeout(60000);
  await mkdir(evidence,{recursive:true});await page.setViewportSize({width:1440,height:1100});
  await page.goto('/');await page.getByRole('button',{name:'Find my set',exact:true}).click();await page.getByRole('button',{name:'Open tutorial',exact:true}).click();
  await expect(page.locator('.viewport canvas')).toBeVisible();await expect(page.getByText('Loading individual part geometry…')).toBeHidden({timeout:30000});
  await page.getByLabel('Jump to instruction').selectOption('10');
  await page.getByRole('button',{name:'Next',exact:true}).scrollIntoViewIfNeeded();
  const positions=()=>page.evaluate(()=>{
    const rect=(selector:string)=>{const r=document.querySelector(selector)!.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height};};
    return{previous:rect('.previous-button'),next:rect('.next-button'),viewport:rect('.viewport'),scroll:scrollY};
  });
  const before=await positions();await page.screenshot({path:`${evidence}/instruction-11.png`,fullPage:true});
  await page.getByRole('button',{name:'Next',exact:true}).click();await expect(page.getByLabel('Jump to instruction')).toHaveValue('11');
  const after=await positions();await page.screenshot({path:`${evidence}/instruction-12.png`,fullPage:true});
  await writeFile(`${evidence}/positions.json`,JSON.stringify({before,after},null,2));
  expect(after.next).toEqual(before.next);expect(after.previous).toEqual(before.previous);
  await page.getByRole('button',{name:'Previous',exact:true}).click();await expect(page.getByLabel('Jump to instruction')).toHaveValue('10');
  expect((await positions()).next).toEqual(before.next);
  for(const width of [1440,900,390]) {
    await page.setViewportSize({width,height:1100});
    await page.getByRole('button',{name:'Next',exact:true}).scrollIntoViewIfNeeded();
    const fixed=await positions();
    for(let index=0;index<16;index++) {
      // Programmatic select via the UI; measure document coordinates to ignore the seek control's auto-scroll.
      await page.getByLabel('Jump to instruction').selectOption(String(index));
      const current=await positions();
      expect(current.next!.y+current.scroll).toBeCloseTo(fixed.next!.y+fixed.scroll,3);
      expect(current.previous!.y+current.scroll).toBeCloseTo(fixed.previous!.y+fixed.scroll,3);
    }
    if(width===390)for(const name of ['Pieces','Guide','3D']) {
      await page.getByRole('tab',{name,exact:true}).click();const current=await positions();
      expect(current.next!.y+current.scroll).toBeCloseTo(fixed.next!.y+fixed.scroll,3);
    }
    await page.screenshot({path:`${evidence}/stable-${width}.png`,fullPage:true});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }

});
