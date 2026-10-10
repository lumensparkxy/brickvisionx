import {test,expect} from '@playwright/test';
// Network fixtures exercise the prepared-pages UI only; the PNG is a 1x1 placeholder, not an official page.
const HASH='a'.repeat(64);
const PNG=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=','base64');

test('prepared booklet shows its official pages with page navigation',async({page})=>{
  const requested:number[]=[];
  const job={job_id:'pages-job',state:'needs_review',stage:'needs_review',completed_units:3,total_units:3,attempts:1,output_revision:null,source_sha256:HASH,
    error:{code:'assisted_reference_unavailable',message:'Official pages are ready. Source-backed part mappings and placements need authoring and review.'}};
  await page.route('**/api/v1/sets/77777',r=>r.fulfill({json:{set_number:'77777',name:'Synthetic pages fixture',official_page:'https://www.lego.com/',
    guides:[{guide_id:'main',label:'Main build',expected_main_steps:null,tutorial_available:false,pdf_url:'https://www.lego.com/main.pdf'}]}}));
  await page.route('**/api/v1/sets/77777/guides/main/status',r=>r.fulfill({json:{source_available:true,latest_candidate_revision:null,latest_reviewed_revision:null,job,coverage:null}}));
  await page.route(`**/api/v1/sources/${HASH}/pages/*`,r=>{
    const index=Number(r.request().url().split('/').pop());requested.push(index);
    return index===2?r.fulfill({status:404,json:{detail:{code:'page_not_found',message:'Rendered source page not available'}}})
      :r.fulfill({status:200,contentType:'image/png',body:PNG});
  });
  await page.goto('/');
  const field=page.getByLabel('Your set number');
  await field.evaluate(element=>{const option=document.createElement('option');option.value='77777';option.textContent='77777 - Synthetic pages fixture';(element as HTMLSelectElement).add(option);});
  await field.selectOption('77777');
  await page.getByRole('button',{name:'Find my set'}).click();
  await page.getByRole('button',{name:'Prepare booklet'}).click();

  const viewer=page.getByRole('region',{name:'Main build official pages'});
  await expect(viewer).toBeVisible();
  await expect(page.getByText('The official pages are prepared. No 3D reconstruction is available for this booklet yet.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Try automatic conversion'})).toHaveCount(0);
  await expect(viewer.getByText('Page 1 of 3')).toBeVisible();
  await expect(viewer.getByRole('img',{name:'Official booklet page 1'})).toHaveAttribute('src',`/api/v1/sources/${HASH}/pages/0`);
  await expect(viewer.getByRole('button',{name:'Previous page'})).toBeDisabled();

  await viewer.getByRole('button',{name:'Next page'}).click();
  await expect(viewer.getByText('Page 2 of 3')).toBeVisible();
  await expect(viewer.getByRole('img',{name:'Official booklet page 2'})).toHaveAttribute('src',`/api/v1/sources/${HASH}/pages/1`);
  await expect(viewer.getByRole('link',{name:'Open full-size page 2 ↗'})).toHaveAttribute('href',`/api/v1/sources/${HASH}/pages/1`);

  await viewer.getByRole('button',{name:'Next page'}).click();
  await expect(viewer.getByRole('alert')).toContainText('This page could not be loaded');
  await expect(viewer.getByRole('button',{name:'Next page'})).toBeDisabled();
  await viewer.getByRole('button',{name:'Previous page'}).click();
  await expect(viewer.getByRole('img',{name:'Official booklet page 2'})).toBeVisible();
  expect(requested).toEqual(expect.arrayContaining([0,1,2]));
});
