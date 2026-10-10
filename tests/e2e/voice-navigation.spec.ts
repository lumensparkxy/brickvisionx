import {test,expect,type Page} from '@playwright/test';
import fixture from '../fixtures/synthetic.scene.json';
// Offline: the reply endpoint is stubbed, so this checks the app's action plumbing, not Gemini.
const actions: Record<string,{text:string;action:Record<string,unknown>}> = {
  'open synthetic': {text:'Opening the synthetic tutorial.',action:{type:'open_tutorial',set_number:'99999',guide_id:'synthetic'}},
  'step 3': {text:'Going to step 3.',action:{type:'go_to_step',step:3}},
  'back': {text:'Previous step.',action:{type:'previous_step'}},
  'forward': {text:'Next step.',action:{type:'next_step'}},
  'home': {text:'Going home.',action:{type:'go_home'}},
  'booklets': {text:'Showing its booklets.',action:{type:'find_set',set_number:'99999'}},
  'close': {text:'Closing the list.',action:{type:'close_booklet'}},
  'bogus': {text:'Trying something.',action:{type:'delete_everything',set_number:'1'}},
};

async function setup(page: Page) {
  const contexts: unknown[] = [];
  await page.route('**/api/v1/sets/99999',r=>r.fulfill({json:{set_number:'99999',name:'Original synthetic test fixture',official_page:'https://www.lego.com/',guides:[{guide_id:'synthetic',label:'Synthetic test guide',expected_main_steps:3,tutorial_available:true,pdf_url:'https://www.lego.com/example.pdf'}]}}));
  await page.route('**/api/v1/sets/99999/guides/synthetic/scene',r=>r.fulfill({json:fixture}));
  await page.route('**/api/v1/sources/**',r=>r.fulfill({status:404,json:{detail:{message:'Test source intentionally absent'}}}));
  await page.route('**/api/v1/voice/reply',async r=>{
    const body=r.request().postDataJSON();contexts.push(body.context);
    await r.fulfill({json:actions[body.messages.at(-1).text]});
  });
  await page.goto('/');
  return contexts;
}
async function say(page: Page, text: string) {
  const collapsed=page.getByRole('button',{name:'Open build helper'});
  if(await collapsed.isVisible())await collapsed.click();
  const input=page.locator('.voice-command input:visible').last();
  const replied=page.waitForResponse('**/api/v1/voice/reply');
  await input.fill(text);await input.press('Enter');
  // Navigation may unmount the box that showed the reply, so check the response, not the transcript.
  expect((await (await replied).json()).text).toBe(actions[text].text);
}

test('typed assistant commands navigate screens and tutorial steps',async({page})=>{
  const contexts=await setup(page);
  await expect(page.getByRole('button',{name:'Start voice chat'})).toBeVisible();
  await say(page,'open synthetic');
  await expect(page.getByRole('heading',{name:'Step 1 of 3',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Open build helper'})).toBeVisible();
  await page.getByRole('button',{name:'Open build helper'}).click();
  await page.getByRole('button',{name:'Hide build helper'}).click();
  await expect(page.locator('.voice-command input:visible')).toHaveCount(0);
  await say(page,'step 3');
  await expect(page.locator('.viewport')).toHaveAttribute('data-step-id','s3');
  await say(page,'back');
  await expect(page.getByRole('heading',{name:'Step 2 of 3',exact:true})).toBeVisible();
  await say(page,'forward');
  await expect(page.locator('.viewport')).toHaveAttribute('data-step-id','s3');
  expect(contexts.at(-1)).toMatchObject({screen:'tutorial',set_number:'99999',guide_id:'synthetic',step:{index:2,total:3}});
  await say(page,'home');
  await expect(page.locator('.workspace')).toHaveCount(0);
  await expect(page.getByRole('heading',{name:/Small bricks/})).toBeVisible();
  await say(page,'booklets');
  await expect(page.locator('dialog.booklet-dialog')).toBeVisible();
  await expect(page.locator('dialog.booklet-dialog .voice-dock')).toBeVisible();
  expect(contexts.at(-1)).toMatchObject({screen:'landing'});
  await say(page,'close');
  await expect(page.locator('dialog.booklet-dialog')).toHaveCount(0);
  expect(contexts.at(-1)).toMatchObject({screen:'booklet',set_number:'99999',guides:[{guide_id:'synthetic',tutorial_available:true}]});
  await say(page,'bogus');
  await expect(page.locator('dialog.booklet-dialog')).toHaveCount(0);
  await expect(page.locator('.workspace')).toHaveCount(0);
});

type Control={id:string;label:string;kind:string};
async function clickSetup(page: Page) {
  const contexts: {controls?:Control[]}[] = [];const conversions: unknown[] = [];
  const job={job_id:'voice-job',state:'failed',stage:'downloading',completed_units:0,total_units:null,attempts:1,output_revision:null,source_sha256:null,error:{code:'download_failed',message:'Synthetic failure for the test.'}};
  await page.route('**/api/v1/sets/88888',r=>r.fulfill({json:{set_number:'88888',name:'Synthetic two-booklet fixture',official_page:'https://www.lego.com/',guides:[
    {guide_id:'main',label:'Main build',expected_main_steps:null,tutorial_available:false,pdf_url:'https://www.lego.com/a.pdf'},
    {guide_id:'alt',label:'Alternate build 2',expected_main_steps:null,tutorial_available:false,pdf_url:'https://www.lego.com/b.pdf'}]}}));
  await page.route('**/api/v1/sets/88888/guides/alt/status',r=>r.fulfill({json:{source_available:false,latest_candidate_revision:null,latest_reviewed_revision:null,job:null,coverage:null}}));
  await page.route('**/api/v1/conversions',r=>{conversions.push(r.request().postDataJSON());return r.fulfill({status:202,json:job});});
  await page.route('**/api/v1/jobs/**',r=>r.fulfill({json:job}));
  await page.route('**/api/v1/sets/99999',r=>r.fulfill({json:{set_number:'99999',name:'Original synthetic test fixture',official_page:'https://www.lego.com/',guides:[{guide_id:'synthetic',label:'Synthetic test guide',expected_main_steps:3,tutorial_available:true,pdf_url:'https://www.lego.com/example.pdf'}]}}));
  await page.route('**/api/v1/sets/99999/guides/synthetic/scene',r=>r.fulfill({json:fixture}));
  await page.route('**/api/v1/sources/**',r=>r.fulfill({status:404,json:{detail:{message:'Test source intentionally absent'}}}));
  const targets: Record<string,string> = {'prepare alternate':'Prepare booklet (Alternate build 2)','review':'Review candidate','full parts':'Full parts list'};
  await page.route('**/api/v1/voice/reply',async r=>{
    const body=r.request().postDataJSON();contexts.push(body.context);const text:string=body.messages.at(-1).text;
    if(text==='booklets two')return r.fulfill({json:{text:'Showing the booklets.',action:{type:'find_set',set_number:'88888'}}});
    if(text==='open synthetic')return r.fulfill({json:actions[text]});
    if(text==='stale')return r.fulfill({json:{text:'Pressing it.',action:{type:'click',control_id:'c79'}}});
    const control=(body.context.controls as Control[]).find(item=>item.label===targets[text]);
    return r.fulfill({json:{text:`Pressing ${targets[text]}.`,action:control?{type:'click',control_id:control.id}:{type:'none'}}});
  });
  await page.goto('/');
  return {contexts,conversions};
}
async function type(page: Page, text: string) {
  const collapsed=page.getByRole('button',{name:'Open build helper'});
  if(await collapsed.isVisible())await collapsed.click();
  const input=page.locator('.voice-command input:visible').last();
  await expect(input).toBeEnabled();
  await input.fill(text);await input.press('Enter');
}

test('assistant presses listed on-screen controls, scoped to the open dialog',async({page})=>{
  const {contexts,conversions}=await clickSetup(page);
  const landing=(await (async()=>{await type(page,'booklets two');await expect(page.locator('dialog.booklet-dialog')).toBeVisible();return contexts.at(-1)!;})()).controls!.map(item=>item.label);
  expect(landing).toContain('Find my set');
  expect(landing).not.toContain('Start voice chat');
  expect(landing).not.toContain('Send');
  await type(page,'prepare alternate');
  const labels=contexts.at(-1)!.controls!.map(item=>item.label);
  expect(labels).toEqual(expect.arrayContaining(['Close booklet selection','Prepare booklet (Main build)','Prepare booklet (Alternate build 2)']));
  expect(labels).not.toContain('Find my set');
  expect(labels.some(label=>/voice|build helper|^Send$/i.test(label))).toBe(false);
  await expect.poll(()=>conversions).toEqual([{set_number:'88888',guide_id:'alt',mode:'assisted'}]);
  await expect(page.getByRole('button',{name:'Retry preparation'})).toBeVisible();
  await type(page,'stale');
  await expect(page.locator('dialog.booklet-dialog .voice-copy [role=status]')).toContainText('That button is no longer available');
});

test('assistant presses viewer controls',async({page})=>{
  await clickSetup(page);
  await type(page,'open synthetic');
  await expect(page.getByRole('heading',{name:'Step 1 of 3',exact:true})).toBeVisible();
  await type(page,'full parts');
  await expect(page.getByRole('button',{name:'Full parts list'})).toHaveAttribute('aria-pressed','true');
  await type(page,'review');
  await expect(page.getByRole('dialog',{name:'Review workspace'})).toBeVisible();
});

test('step commands outside a tutorial explain instead of navigating',async({page})=>{
  await setup(page);
  await say(page,'forward');
  await expect(page.locator('.voice-copy [role=status]').first()).toContainText('Open a 3D tutorial first');
});
