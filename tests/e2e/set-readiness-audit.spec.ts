import {test,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import matrix from '../fixtures/release-sets.json';

// An audit of actual support, not ten successful reconstructions. Keep outcomes explicit.
test('ten real sets: record catalogue and tutorial gates without substituting models',async({page})=>{
  test.setTimeout(120000);
  const dir=process.env.GUIDE2BUILD_AUDIT_DIR??'var/evidence/ten-set-release';await mkdir(dir,{recursive:true});
  await page.setViewportSize({width:1440,height:900});await page.goto('/');
  await expect(page.getByRole('combobox',{name:'Your set number'}).locator('option')).toHaveCount(10);
  const outcomes=[];
  for(const entry of matrix){
    const started=performance.now();const response=await page.request.get(`/api/v1/sets/${entry.set_number}`);
    const result=await response.json();const lookupMs=performance.now()-started;
    if(response.ok())await expect(page.getByRole('combobox',{name:'Your set number'}).locator(`option[value="${entry.set_number}"]`)).toHaveText(`${entry.set_number} - ${result.name}`);
    await page.getByLabel('Your set number').selectOption(entry.set_number);
    await page.getByRole('button',{name:'Find my set',exact:true}).click();
    const outcome:Record<string,unknown>={...entry,lookup_status:response.status(),lookup_ms:lookupMs,rendering:'blocked',correctness:'not_evaluated'};
    if(response.ok()){
      await expect(page.getByRole('dialog')).toBeVisible();
      const guides=[];
      for(const guide of result.guides){
        const path=`/api/v1/sets/${entry.set_number}/guides/${guide.guide_id}`;
        const statusResponse=await page.request.get(`${path}/status`);const status=await statusResponse.json();
        const tutorial=await page.request.get(`${path}/scene`);
        const record:Record<string,unknown>={guide_id:guide.guide_id,status_http:statusResponse.status(),status,accepted_tutorial_http:tutorial.status()};
        if(status.latest_candidate_revision){
          const candidate=await page.request.get(`/api/v1/reconstructions/${encodeURIComponent(status.latest_candidate_revision)}/scene`);const scene=await candidate.json();
          record.candidate={http:candidate.status(),revision:scene.revision,status:scene.status,instances:scene.instances.length,microsteps:scene.steps.length,geometry_check:scene.geometry_check,connector_check:scene.connector_check,physical_build_check:scene.physical_build_check};
          outcome.rendering='candidate_available_separate_renderer_benchmark';outcome.correctness='unaccepted_candidate';
        }
        guides.push(record);
      }
      outcome.guides=guides;
      await page.screenshot({path:`${dir}/lookup-${entry.set_number}.png`});
      await page.getByRole('button',{name:'Close booklet selection'}).click();
    }else{
      outcome.error=result.detail;
      await expect(page.getByRole('alert')).toContainText(result.detail.message);
      await expect(page.locator('.workspace')).toHaveCount(0);
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await page.screenshot({path:`${dir}/lookup-${entry.set_number}.png`,fullPage:true});
    }
    outcomes.push(outcome);
  }
  const health=await (await page.request.get('/api/v1/health')).json();
  // Explicitly probe the provider boundary; this rejects before creating a job or calling inference.
  const auto=await page.request.post('/api/v1/conversions',{headers:{'Idempotency-Key':'ten-set-readiness-provider-boundary'},data:{set_number:'30669',guide_id:'alt-02',mode:'automated'}});
  await writeFile(`${dir}/set-outcomes.json`,JSON.stringify({tested_at:new Date().toISOString(),health,tier_definition:'Our evaluation bands; advertised set count is not the selected booklet BOM.',outcomes,automatic_conversion:{http:auto.status(),response:await auto.json()},note:'A passing test means observed gates were recorded and UI matched API, not that all ten sets render or are correct.'},null,2));
  expect(outcomes).toHaveLength(10);
});
