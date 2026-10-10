import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
test('studio groups main steps without skipping callouts and keeps phone context visible',async({page})=>{
  test.setTimeout(60000);
  await mkdir('var/evidence/open-studio',{recursive:true});
  await page.setViewportSize({width:1440,height:900});await page.goto('/');
  await page.getByRole('button',{name:'Find my set',exact:true}).click();await page.getByRole('button',{name:'Open tutorial',exact:true}).click();
  await expect(page.getByRole('button',{name:'Play full build',exact:true})).toBeEnabled({timeout:30000});
  await expect(page.locator('.step-timeline button')).toHaveCount(12);
  const selected=page.locator('.step-timeline [aria-current=step]');
  await page.getByRole('button',{name:'Go to main step 3',exact:true}).click();
  await expect(page.getByLabel('Jump to instruction')).toHaveValue('2');
  for(const value of ['2','3','4']) {
    await expect(page.getByLabel('Jump to instruction')).toHaveValue(value);
    await expect(selected).toHaveText('3');
    await expect(page.getByRole('heading',{name:'Step 3 of 12',exact:true})).toBeVisible();
    if(value==='4')await expect(page.getByText('No new pieces.',{exact:false})).toBeVisible();
    await page.getByRole('button',{name:'Next',exact:true}).click();
  }
  await expect(selected).toHaveText('4');await expect(page.getByLabel('Jump to instruction')).toHaveValue('5');
  await page.getByRole('button',{name:'Go to main step 5',exact:true}).focus();await page.keyboard.press('Enter');await expect(page.getByLabel('Jump to instruction')).toHaveValue('8');
  await page.getByRole('button',{name:'Play full build',exact:true}).click();
  await page.getByRole('button',{name:'Go to main step 12',exact:true}).click();
  await expect(page.getByRole('button',{name:'Play full build',exact:true})).toBeVisible();await expect(page.getByLabel('Jump to instruction')).toHaveValue('15');
  await page.screenshot({path:'var/evidence/open-studio/test-desktop.png'});
  for(const width of [1440,900,390]) {
    await page.setViewportSize({width,height:width===390?844:900});
    expect(await page.evaluate(()=>({x:document.documentElement.scrollWidth<=innerWidth,y:document.documentElement.scrollHeight<=innerHeight}))).toEqual({x:true,y:true});
  }
  await page.getByLabel('Jump to instruction').selectOption('3');
  for(const name of ['3D','Guide','Pieces']) {
    await page.getByRole('tab',{name,exact:true}).click();
    await expect(page.getByRole('heading',{name:'Step 3 of 12',exact:true})).toBeVisible();
    await expect(page.locator('.instruction-copy:not([aria-hidden])')).toBeVisible();
    await expect(page.getByLabel('Jump to instruction')).toHaveValue('3');
    await expect(page.getByRole('button',{name:'Next',exact:true})).toBeInViewport();
  }
  await page.getByRole('tab',{name:'3D',exact:true}).click();
  await page.getByRole('tab',{name:'3D',exact:true}).press('ArrowRight');
  await expect(page.getByRole('tab',{name:'Guide',exact:true})).toBeFocused();
  await expect(page.getByRole('tabpanel',{name:'Guide',exact:true})).toBeVisible();
  await page.getByRole('tab',{name:'Guide',exact:true}).press('End');
  await expect(page.getByRole('tab',{name:'Pieces',exact:true})).toBeFocused();
  await page.getByRole('tab',{name:'Pieces',exact:true}).press('Home');
  await expect(page.getByRole('tab',{name:'3D',exact:true})).toBeFocused();
  await page.getByRole('button',{name:'Review candidate',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Review workspace',exact:true});
  await expect(dialog).toBeVisible();
  await expect(page.getByRole('button',{name:'Dismiss review',exact:true})).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  expect(await page.evaluate(()=>!!document.activeElement?.closest('dialog'))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Review candidate',exact:true})).toBeFocused();
  await page.screenshot({path:'var/evidence/open-studio/test-phone.png'});
});
