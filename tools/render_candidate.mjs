#!/usr/bin/env node
/** Actual Three.js candidate rendering, with an isolated transport fixture. Not software E2E or publication. */
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir,mkdtemp,rm,stat,realpath} from 'node:fs/promises';
import {resolve,dirname,join,extname} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {chromium} from '@playwright/test';
import {FrontendAssetReadError,readFrontendAsset,serveFrontendAsset} from './render_frontend_asset.mjs';
const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const sha=value=>createHash('sha256').update(value).digest('hex');
// Camera comparison is semantic; only Python canonical bytes define scene hashes.
const orderedJson=value=>JSON.stringify(value,(_,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.entries(item).sort(([a],[b])=>a.localeCompare(b))):item);
const usage='node tools/render_candidate.mjs --scene PATH --geometry-root PATH --output NEW_DIR [--source-views PATH] [--from 1 --to N] [--width 1440 --height 900 --timeout-ms 60000]';
const flags=new Map();
for(let index=2;index<process.argv.length;index+=2){const key=process.argv[index];if(key==='--help'){console.log(usage);process.exit(0);}if(!['--scene','--geometry-root','--output','--source-views','--from','--to','--width','--height','--timeout-ms'].includes(key)||!process.argv[index+1]||flags.has(key))throw new Error(usage);flags.set(key,process.argv[index+1]);}
for(const key of ['--scene','--geometry-root','--output'])if(!flags.has(key))throw new Error(usage);
const integer=(key,fallback,min,max)=>{const value=Number(flags.get(key)??fallback);if(!Number.isInteger(value)||value<min||value>max)throw new Error(`Invalid ${key}`);return value;};
const input=resolve(flags.get('--scene')),geometry=await realpath(resolve(flags.get('--geometry-root'))),output=resolve(flags.get('--output'));
const width=integer('--width',1440,320,3840),height=integer('--height',900,600,2160),timeout=integer('--timeout-ms',60000,1000,300000);
const inputStat=await stat(input);if(!inputStat.isFile()||inputStat.size>256_000_000)throw new Error('Candidate input exceeds256MB bound');
let original=await readFile(input);
if(original.length>256_000_000)throw new Error('Candidate input exceeds256MB bound');
const inputSha=sha(original),inputBytes=original.length;
original=null; // Do not retain another full scene buffer while loading the validated result.
let sourceViewBytes=null,sourceViewPath='';
if(flags.has('--source-views')){sourceViewPath=resolve(flags.get('--source-views'));const info=await stat(sourceViewPath);if(!info.isFile()||info.size>1_000_000)throw new Error('Source camera input exceeds1MB bound');sourceViewBytes=await readFile(sourceViewPath);if(sourceViewBytes.length>1_000_000)throw new Error('Source camera input exceeds1MB bound');}
const sourceViewInputSha=sourceViewBytes?sha(sourceViewBytes):'';
// Python reads the pinned input directly and writes canonical bytes into this
// call's private directory. Only small integrity metadata crosses stdout. This
// preserves signed zero and V1 adaptation without a full-scene pipe round trip.
const normalizationTimeout=60000;
async function normalizeCandidate(){
 const directory=await mkdtemp(join(tmpdir(),'guide2build-candidate-normalize-'));
 const sceneFile=join(directory,'scene.json'),viewsFile=join(directory,'source-views.json');
 const started=performance.now();
 try{
  const normalize=spawnSync(join(ROOT,'.venv/bin/python'),['-c',`
import hashlib,json,os,sys
from pathlib import Path
from guide2build.core.models import SceneManifest
from guide2build.releases.models import SceneV2,adapt_v1,canonical
from guide2build.engine.source_view import SourceCamera

def bounded_read(name,limit):
    path=Path(name)
    if not path.is_file() or path.stat().st_size>limit:
        raise ValueError('Normalization input exceeds its file bound')
    with path.open('rb') as stream:
        data=stream.read(limit+1)
    if len(data)>limit:
        raise ValueError('Normalization input exceeds its file bound')
    return data

def exclusive_write(name,data,limit):
    if len(data)>limit:
        raise ValueError('Normalized result exceeds its file bound')
    with Path(name).open('xb') as stream:
        os.fchmod(stream.fileno(),0o600)
        stream.write(data)
    return hashlib.sha256(data).hexdigest()

input_path,scene_path,views_path,camera_path,input_sha,camera_sha=sys.argv[1:]
source=bounded_read(input_path,256_000_000)
if hashlib.sha256(source).hexdigest()!=input_sha:
    raise ValueError('Candidate input changed during normalization')
raw=json.loads(source)
del source
if camera_path:
    camera_bytes=bounded_read(camera_path,1_000_000)
    if hashlib.sha256(camera_bytes).hexdigest()!=camera_sha:
        raise ValueError('Source cameras changed during normalization')
    views=json.loads(camera_bytes)
else:
    views={}
if not isinstance(views,dict):
    raise ValueError('Source cameras must be keyed by step identity')
views={key:SourceCamera.model_validate(value).model_dump(mode='json') for key,value in views.items()}
if raw.get('schema_version')=='1.0':
    entries=json.loads(Path('config/sets.json').read_text())['sets']
    guide=next(g for s in entries if s['set_number']==raw['set_number'] for g in s['guides'] if g['guide_id']==raw['guide_id'])
    scene=adapt_v1(SceneManifest.model_validate(raw),guide['pdf_url'],guide['expected_page_count'])
else:
    scene=SceneV2.model_validate(raw)
del raw
scene_bytes=canonical(scene)
scene_sha=exclusive_write(scene_path,scene_bytes,256_000_000)
view_bytes=canonical(views)
views_sha=exclusive_write(views_path,view_bytes,2_000_000)
print(json.dumps({'input_sha256':input_sha,'scene_sha256':scene_sha,'scene_bytes':len(scene_bytes),
    'source_views_input_sha256':camera_sha or None,'source_views_sha256':views_sha,
    'source_views_bytes':len(view_bytes)}))
` ,input,sceneFile,viewsFile,sourceViewPath,inputSha,sourceViewInputSha],{cwd:ROOT,encoding:'utf8',env:{...process.env,PYTHONPATH:join(ROOT,'apps/api/src')},stdio:['ignore','pipe','pipe'],maxBuffer:64_000,timeout:normalizationTimeout,killSignal:'SIGKILL'});
  const elapsed=performance.now()-started;
  if(normalize.error||normalize.status!==0){
   const code=normalize.error?.code??'nonzero_exit';
   const cause=code==='ETIMEDOUT'?`timed out after ${normalizationTimeout}ms`:`failed (${code}; exit=${normalize.status}; signal=${normalize.signal??'none'})`;
   const diagnostic=String(normalize.stderr??'').slice(-2000).trim();
   throw new Error(`Candidate normalization ${cause} in ${Math.round(elapsed)}ms${diagnostic?': '+diagnostic:''}`);
  }
  let metadata;
  try{metadata=JSON.parse(normalize.stdout);}catch{throw new Error('Candidate normalization returned invalid integrity metadata');}
  const hex=/^[a-f0-9]{64}$/;
  if(!metadata||typeof metadata!=='object'||Array.isArray(metadata)||metadata.input_sha256!==inputSha||metadata.source_views_input_sha256!==(sourceViewInputSha||null)||!hex.test(metadata.scene_sha256)||!hex.test(metadata.source_views_sha256)||!Number.isInteger(metadata.scene_bytes)||metadata.scene_bytes<1||metadata.scene_bytes>256_000_000||!Number.isInteger(metadata.source_views_bytes)||metadata.source_views_bytes<2||metadata.source_views_bytes>2_000_000)throw new Error('Candidate normalization returned inconsistent integrity metadata');
  const [sceneInfo,viewInfo]=await Promise.all([stat(sceneFile),stat(viewsFile)]);
  if(!sceneInfo.isFile()||sceneInfo.size!==metadata.scene_bytes||!viewInfo.isFile()||viewInfo.size!==metadata.source_views_bytes)throw new Error('Candidate normalization output size differs from metadata');
  const [sceneBytes,viewBytes]=await Promise.all([readFile(sceneFile),readFile(viewsFile)]);
  if(sha(sceneBytes)!==metadata.scene_sha256||sha(viewBytes)!==metadata.source_views_sha256)throw new Error('Candidate normalization output checksum differs from metadata');
  const scene=JSON.parse(sceneBytes),sourceViews=JSON.parse(viewBytes);
  if(scene.schema_version!=='2.0'||!Array.isArray(scene.steps)||!sourceViews||typeof sourceViews!=='object'||Array.isArray(sourceViews))throw new Error('Candidate normalization output has an invalid transport shape');
  return {scene,metadata,sourceViews,stats:{transport:'private_canonical_files',elapsed_ms:elapsed,timeout_ms:normalizationTimeout,stdout_bytes:Buffer.byteLength(normalize.stdout),input_bytes:inputBytes,normalized_scene_bytes:metadata.scene_bytes,normalized_source_views_bytes:metadata.source_views_bytes,temporary_files_removed:true}};
 }finally{
  // This uniquely created directory contains only this invocation's two files.
  // No input, geometry or durable evidence paths are cleanup targets.
  await rm(directory,{recursive:true,force:true});
 }
}
const {scene,metadata:normalized,sourceViews:normalizedViews,stats:normalizationStats}=await normalizeCandidate();
const from=integer('--from',1,1,scene.steps.length),to=integer('--to',scene.steps.length,from,scene.steps.length);
const sourceViews=new Map(Object.entries(normalizedViews));
const renderStepIds=new Set(scene.steps.slice(from-1,to).map(step=>step.step_id));
if([...sourceViews.keys()].some(id=>!renderStepIds.has(id)))throw new Error('Source camera references a step outside the render range');
const provenanceBytes=await readFile(join(geometry,'provenance.json'));if(provenanceBytes.length>32_000_000)throw new Error('Geometry provenance exceeds limit');
const provenance=JSON.parse(provenanceBytes),objects=new Map(),selected=new Set(),visiting=new Set();let geometryBytes=0;
const safePath=/^(?:parts\/(?:s\/)?|p\/(?:8\/|48\/)?)?[a-zA-Z0-9_.-]+\.(?:dat|ldr)$/;
async function geometryFile(path,record){
  if(!safePath.test(path)||path.includes('..'))throw new Error(`Unsafe geometry path: ${path}`);
  const file=await realpath(join(geometry,path));if(!file.startsWith(geometry+'/'))throw new Error('Geometry escapes selected directory');
  const info=await stat(file);if(info.size>1_000_000)throw new Error('Geometry file exceeds1MB bound');
  const bytes=await readFile(file);if(record?.url!=='https://library.ldraw.org/library/official/'+path)throw new Error(`Unexpected individual geometry origin: ${path}`);if(path!=='LDConfig.ldr'){const category=bytes.toString('utf8').match(/^0 !LDRAW_ORG (\S+)/m)?.[1];if(!['Part','Subpart','Primitive','48_Primitive','8_Primitive'].includes(category)||record.classification!==category)throw new Error(`Non-individual or unclassified geometry: ${path}`);if(!/^0 !LICENSE /m.test(bytes.toString('utf8')))throw new Error(`Geometry licence missing: ${path}`);}if(!record||sha(bytes)!==record.sha256)throw new Error(`Geometry checksum mismatch: ${path}`);
  geometryBytes+=bytes.length;if(geometryBytes>256_000_000)throw new Error('Geometry exceeds256MB closure bound');objects.set('/render-geometry/'+path,{bytes,type:'text/plain'});
}
async function closure(path,depth=0){if(depth>40||visiting.has(path))throw new Error('Cyclic/deep geometry closure');if(selected.has(path))return;if(selected.size>=20000)throw new Error('Geometry resource bound');const record=provenance.resources?.[path];if(!record||!Array.isArray(record.dependencies))throw new Error(`Missing geometry provenance: ${path}`);visiting.add(path);await geometryFile(path,record);for(const child of record.dependencies)await closure(child,depth+1);visiting.delete(path);selected.add(path);}
for(const part of scene.instances)await closure(part.geometry_ref);
await geometryFile('LDConfig.ldr',provenance.materials?.['LDConfig.ldr']);
const filtered={resources:Object.fromEntries([...selected].map(p=>[p,provenance.resources[p]])),file_map:Object.fromEntries(Object.entries(provenance.file_map??{}).filter(([,p])=>selected.has(p))),materials:provenance.materials};
const publicProvenance=Buffer.from(JSON.stringify(filtered));objects.set('/render-geometry/provenance.json',{bytes:publicProvenance,type:'application/json'});
const manifest={...scene,reviews:[],step_index:[],chunks:[],asset_base_url:'/render-chunks/',geometry_base_url:'/render-chunks/ldraw/'};delete manifest.steps;
for(let offset=0;offset<scene.steps.length;offset+=8){const index=offset/8,steps=scene.steps.slice(offset,offset+8),path=`chunks/${String(index).padStart(5,'0')}.json`,bytes=Buffer.from(JSON.stringify({steps}));objects.set('/render-chunks/'+path,{bytes,type:'application/json'});manifest.chunks.push({index,path,sha256:sha(bytes),bytes:bytes.length,step_ids:steps.map(s=>s.step_id)});manifest.step_index.push(...steps.map(({poses,visible_instance_ids,active_instance_ids,...s})=>({...s,chunk_index:index,visible_instance_count:visible_instance_ids.length,active_instance_count:active_instance_ids.length})));}
// A private render-session transport ID, deliberately not a publication/approval certificate.
manifest.release_sha256=sha(Buffer.from(JSON.stringify(manifest)));
for(const [path,item] of [...objects])if(path.startsWith('/render-geometry/'))objects.set(path.replace('/render-geometry/','/render-chunks/ldraw/'),item);
const official=scene.sources[0].official_url,guide={guide_id:scene.guide_id,label:'Local candidate render',pdf_url:official,expected_main_steps:null,tutorial_available:true};
const api=new Map([
 ['/api/v1/config',{mode:'preview',source_images:false,requests_enabled:false}],
 [`/api/v1/sets/${scene.set_number}`,{set_number:scene.set_number,name:'Local candidate render',official_page:official,guides:[guide]}],
 [`/api/v1/sets/${scene.set_number}/guides/${scene.guide_id}/release`,manifest],
]);
const dist=await realpath(join(ROOT,'apps/web/dist'));await stat(join(dist,'index.html'));
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.webp':'image/webp','.png':'image/png','.svg':'image/svg+xml','.woff2':'font/woff2'};
const frontendAssetErrors=[];let frontendAssetReadError;
const failFrontendAsset=error=>{if(!frontendAssetReadError){frontendAssetReadError=error;frontendAssetErrors.push(error.diagnostic);}void browser?.close().catch(()=>{});};
const server=createServer(async(req,res)=>{try{
  if(req.method!=='GET'){res.writeHead(405).end();return;}
  const path=new URL(req.url,'http://127.0.0.1').pathname;
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');
  if(api.has(path)){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(api.get(path)));return;}
  if(objects.has(path)){const item=objects.get(path);res.setHeader('Content-Type',item.type);res.end(item.bytes);return;}
  if(path==='/'||path.startsWith('/assets/')||path.startsWith('/images/')||path.startsWith('/fonts/')){const file=await realpath(join(dist,path==='/'?'index.html':path.slice(1)));if(!file.startsWith(dist+'/'))throw new Error('Asset escapes builtfrontend');await serveFrontendAsset(res,file,path,types[extname(file)]??'application/octet-stream',failFrontendAsset);return;}
  res.writeHead(404).end('Not available in candidate renderer');
}catch{res.writeHead(404).end('Not available in candidate renderer');}});
await mkdir(output,{recursive:false}); // Deliberately reject existing evidence directories.
if(sourceViewBytes)await writeFile(join(output,'source-views.json'),sourceViewBytes,{flag:'wx'});
const report={schema_version:'1.0',artifact_kind:'candidate_render_evidence',generated_at:new Date().toISOString(),input_sha256:inputSha,scene_sha256:normalized.scene_sha256,normalization:normalizationStats,set_number:scene.set_number,guide_id:scene.guide_id,revision:scene.revision,source_sha256:scene.source_sha256,input_path:input,geometry_provenance_sha256:sha(provenanceBytes),served_geometry_provenance_sha256:sha(publicProvenance),geometry_resource_count:selected.size,geometry_bytes:geometryBytes,viewer_build_sha256:null,range:{from,to,total_steps:scene.steps.length},viewport:{width,height},steps:[],console_errors:[],frontend_asset_errors:frontendAssetErrors,status:'running',limitations:['Actual existing Three.js viewer with isolated candidate API fixture; not software E2E or publication.','Image correspondence, connector validity, strength, human review and physical construction are not certified.','Frame samples are on-demand draw submissions, not sustained interactive FPS or GPU utilization.'],physical_build:'not_run',human_review:'not_run'};
let browser,cancelled=false;
report.source_views_sha256=sourceViewBytes?sha(sourceViewBytes):null;
report.source_view_count=sourceViews.size;
if(sourceViews.size)report.limitations.push('Requested-camera screenshots preserve the camera record aspect and hide presentation overlays and active bounding boxes; the supplied camera is not certified as source-fitted. Assembly geometry and snapshots are unchanged.');
const cancel=()=>{cancelled=true;void browser?.close();server.close();};
process.once('SIGINT',cancel);process.once('SIGTERM',cancel);
try{
 report.viewer_build_sha256=sha(await readFrontendAsset(join(dist,'index.html'),'/index.html'));
 await new Promise((yes,no)=>{server.once('error',no);server.listen(0,'127.0.0.1',yes);});const origin=`http://127.0.0.1:${server.address().port}`;
 if(cancelled)throw new Error('Rendering cancelled');
 browser=await chromium.launch({headless:true});if(cancelled)throw new Error('Rendering cancelled');const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:1,reducedMotion:'reduce'});const page=await context.newPage();page.setDefaultTimeout(timeout);
 await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort('blockedbyclient'));
 page.on('pageerror',error=>report.console_errors.push(error.message));
 await page.goto(origin+'/?benchmark=1');
 const setSelector=page.getByLabel('Your set number');
 if(await setSelector.evaluate(element=>element.tagName==='SELECT'))await setSelector.selectOption(scene.set_number);
 else await setSelector.fill(scene.set_number);
 await page.getByRole('button',{name:'Find my set',exact:true}).click();await page.getByRole('button',{name:/Open (tutorial|candidate)/,exact:true}).click();
 const loaded=async()=>{const result=await page.waitForFunction(()=>{const failure=[...document.querySelectorAll('[role=alert]')].filter(el=>el.getClientRects().length).map(el=>el.textContent).join(' ');if(failure)return {error:failure};const replay=document.querySelector('button.replay');return replay&&!replay.disabled?{ready:true}:false;},{},{timeout});const state=await result.jsonValue();if(state.error)throw new Error(state.error);};
 await loaded();
 for(let index=from-1;index<to;index++){
  if(cancelled)throw new Error('Rendering cancelled');
  const started=performance.now();await page.getByLabel('Jump to instruction').selectOption(String(index));await page.waitForFunction(expected=>document.querySelector('.viewport')?.dataset.stepId===expected,scene.steps[index].step_id);await page.locator('.viewport canvas').waitFor({state:'visible'});await loaded();await page.getByRole('button',{name:'Reset view',exact:true}).click();
  const sourceCamera=sourceViews.get(scene.steps[index].step_id);
  if(sourceCamera){
   await page.evaluate(({camera,stepId})=>{if(!window.__guide2buildSourceCamera)throw new Error('Built viewer lacks source camera diagnostics');window.__guide2buildSourceCamera.apply(camera,stepId);},{camera:sourceCamera,stepId:scene.steps[index].step_id});
   await page.waitForFunction(()=>document.querySelector('.viewport')?.dataset.cameraMode==='source_orthographic');
  }
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const actualSourceCamera=await page.evaluate(()=>{const data=document.querySelector('.viewport')?.dataset.sourceCameraFrame;return data?JSON.parse(data):null;});
  if(sourceCamera&&orderedJson(actualSourceCamera?.input)!==orderedJson(sourceCamera))throw new Error('Actual source camera does not match requested camera');
  if(!sourceCamera&&actualSourceCamera)throw new Error('Unexpected source camera on default render');
  const file=`step-${String(index+1).padStart(4,'0')}.png`;
  let png;
  if(actualSourceCamera){const box=await page.locator('.viewport canvas').boundingBox();if(!box)throw new Error('Missing source camera canvas');const crop=actualSourceCamera.source_rect;png=await page.screenshot({path:join(output,file),clip:{x:box.x+crop.x,y:box.y+crop.y,width:crop.width,height:crop.height},style:'.model-caption,.camera-controls,.gesture-hint,.placement-note{visibility:hidden!important}',animations:'disabled'});}
  else png=await page.locator('.viewport canvas').screenshot({path:join(output,file),animations:'disabled'});
  const metrics=await page.evaluate(()=>{const audits=window.__guide2buildRendererAudits??[];const audit=audits.at(-1);const viewport=document.querySelector('.viewport');return {hardware:audit?.hardware??null,samples:audit?.samples.filter(s=>s.phase==='viewport'&&s.stepId===viewport?.dataset.stepId).slice(-20)??[],gpu_ms:audit?.gpuMs??[],gpu_discarded:audit?.gpuDiscarded??0,camera_frame:viewport?.dataset.cameraFrame,geometry_count:Number(viewport?.dataset.geometryCount??0),draw_calls:Number(viewport?.dataset.drawCalls??0)};});
  const step=scene.steps[index];report.steps.push({index:index+1,step_id:step.step_id,section_id:step.section_id,main_step_number:step.main_step_number,source:step.source,visible_instance_count:step.visible_instance_ids.length,active_instance_ids:step.active_instance_ids,screenshot:file,png_sha256:sha(png),camera_mode:actualSourceCamera?'source_orthographic':'perspective',source_camera:actualSourceCamera,capture_elapsed_ms:performance.now()-started,...metrics});
  await writeFile(join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
 }
 report.status='rendered';
}catch(error){if(error instanceof FrontendAssetReadError)failFrontendAsset(error);report.status=cancelled?'cancelled':'failed';report.error=String((frontendAssetReadError??error).message??error);process.exitCode=1;}
finally{await browser?.close();await new Promise(resolve=>server.close(resolve));if(frontendAssetReadError&&!cancelled){report.status='failed';report.error=frontendAssetReadError.message;process.exitCode=1;}await writeFile(join(output,'report.json'),JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify({status:report.status,scene_sha256:report.scene_sha256,rendered_steps:report.steps.length,report:join(output,'report.json'),error:report.error??null}));
