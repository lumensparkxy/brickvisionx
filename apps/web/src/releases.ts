import Ajv2020 from 'ajv/dist/2020';
import schema from '../../../packages/contracts/scene.schema.json';
import type { PartInstance, SceneManifest, StepSnapshot } from './contracts';
import { modelAssetUrl } from './assets';

export const REQUEST_RECORDED = 'This build isn’t ready yet. We’ve added it to our building list. Come back later to see what’s new!';
export interface PortalConfig { mode: 'local' | 'public' | 'preview'; source_images: boolean; requests_enabled: boolean; }
export function parseConfig(value: unknown): PortalConfig {
  const config = value as PortalConfig;
  if (!config || !['local','public','preview'].includes(config.mode) || typeof config.source_images !== 'boolean' || typeof config.requests_enabled !== 'boolean' || config.mode==='public'&&config.source_images) throw new Error('Website settings could not be verified. Please try again.');
  return config;
}
interface Chunk { index:number; path:string; sha256:string; bytes:number; step_ids:string[]; }
interface IndexedStep extends Omit<StepSnapshot,'poses'|'visible_instance_ids'|'active_instance_ids'|'snapshot_loaded'> { chunk_index:number; visible_instance_count:number; active_instance_count:number; }
export type AlphaReleaseMetadata = {
  source_coverage: string; coverage_text: string; uncertainty_notes: string[];
  accuracy: 'unverified'; human_review: 'not_run'; physical_build: 'not_run';
} & ({artifact_kind:'pdf_assisted_alpha_completion';generation_mode:'alpha_fast'}
  | {artifact_kind:'exploration_candidate';generation_mode:'explore'});
interface Release { scene:SceneManifest; chunks:Chunk[]; stepIndex:IndexedStep[]; assetBase:string; introducedAt:Record<string,number>; release_kind?:'unverified_alpha'; alpha?:AlphaReleaseMetadata; }
const error = (message:string):never => {throw new Error(`Invalid tutorial release: ${message}`);};
const hash = (value:unknown):value is string => typeof value==='string' && /^[a-f0-9]{64}$/.test(value);
const official = (value:unknown) => {try {const url=new URL(String(value));return url.protocol==='https:'&&(url.hostname==='lego.com'||url.hostname.endsWith('.lego.com'));}catch{return false;}};
export function assetBase(value:unknown):string {
  if(typeof value!=='string'||!value.endsWith('/')||value.includes('\\')||value.includes('..'))return error('unsafe asset base');
  const url=new URL(value,location.origin);
  if(url.username||url.password||url.search||url.hash||!(url.origin===location.origin||url.protocol==='https:'&&url.hostname==='storage.googleapis.com'))return error('untrusted asset origin');
  return url.href;
}
function freeze<T>(value:T):T {if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
const ajv=new Ajv2020({strict:false});
const validatePart=ajv.compile<PartInstance>({$defs:schema.$defs,...schema.$defs.PartInstance});
const validateStep=ajv.compile<StepSnapshot>({$defs:schema.$defs,...schema.$defs.StepSnapshot});
const group=(step:Pick<StepSnapshot,'section_id'|'main_step_number'|'printed_step_number'|'step_id'>)=>`${step.section_id??''}:${step.printed_step_number===null?step.step_id:step.main_step_number}`;
const adapted=(step:Record<string,unknown>,ordinal:number) => ({...step,printed_step_number:step.main_step_number,main_step_number:step.main_step_number===null?ordinal+1:step.main_step_number});
function releaseMetadata(data:Record<string,any>):Pick<Release,'release_kind'|'alpha'> {
  if(data.release_kind===undefined){if(data.alpha!==undefined)error('alpha metadata without release kind');return {};}
  if(data.release_kind!=='unverified_alpha')error('release kind');
  const alpha=data.alpha as AlphaReleaseMetadata;
  const text=(value:unknown,max:number):value is string=>typeof value==='string'&&value.trim().length>0&&value.length<=max;
  if(!alpha||!((alpha.artifact_kind==='pdf_assisted_alpha_completion'&&alpha.generation_mode==='alpha_fast')
      ||(alpha.artifact_kind==='exploration_candidate'&&alpha.generation_mode==='explore'))
      ||alpha.accuracy!=='unverified'||alpha.human_review!=='not_run'||alpha.physical_build!=='not_run'
      ||!text(alpha.source_coverage,120)||!alpha.source_coverage.includes('unverified')||alpha.source_coverage.includes('independently_verified')
      ||!text(alpha.coverage_text,1000)||!alpha.coverage_text.startsWith('Reported coverage (unverified): ')
      ||!Array.isArray(alpha.uncertainty_notes)||alpha.uncertainty_notes.length<1||alpha.uncertainty_notes.length>100
      ||alpha.uncertainty_notes.some(note=>!text(note,2000))
      ||alpha.uncertainty_notes.reduce((total,note)=>total+new TextEncoder().encode(note).byteLength,0)>40000)error('alpha metadata');
  if(data.status!=='needs_review'||['geometry_check','connector_check','physical_build_check'].some(key=>data[key]!=='not_run'))error('alpha check metadata');
  return {release_kind:'unverified_alpha',alpha};
}
export function parseRelease(value:unknown):Release {
  // Keep transport input separate from the immutable metadata and snapshot state.
  const data=structuredClone(value) as Record<string,any>;
  if(!data||data.schema_version!=='2.0'||!/^\d{4,7}$/.test(data.set_number)||!/^[a-z0-9-]+$/.test(data.guide_id)||typeof data.revision!=='string'||!hash(data.source_sha256)||!hash(data.release_sha256)||data.coordinate_system!=='right_handed_y_up_ldu')error('identity');
  if(!['candidate','needs_review','agent_reviewed','human_reviewed'].includes(data.status)||['geometry_check','connector_check','physical_build_check'].some(key=>!['pass','fail','not_run'].includes(data[key])))error('check metadata');
  const metadata=releaseMetadata(data);
  const base=assetBase(data.asset_base_url); const geometry=assetBase(data.geometry_base_url);
  if(!geometry.startsWith(base))error('geometry outside release');
  if(!Array.isArray(data.sources)||!data.sources.length||data.sources.some((s:any)=>!hash(s.source_sha256)||typeof s.guide_id!=='string'||!official(s.official_url)||!Number.isInteger(s.page_count)||s.page_count<1))error('official source metadata');
  const sources=new Map<string,number>(data.sources.map((s:any)=>[s.source_sha256,s.page_count]));
  if(!sources.has(data.source_sha256)||sources.size!==data.sources.length)error('source identity');
  if(!Array.isArray(data.sections)||!data.sections.length)error('sections');
  const sections=new Map<string,string>();
  for(const section of data.sections){if(typeof section.section_id!=='string'||!section.section_id||sections.has(section.section_id)||!sources.has(section.source_sha256)||typeof section.label!=='string')error('section identity');sections.set(section.section_id,section.source_sha256);}
  const panel=(p:any)=>{if(!p||!sources.has(p.source_sha256)||!Number.isInteger(p.page_index)||p.page_index<0||p.page_index>=sources.get(p.source_sha256)!||!Array.isArray(p.bbox)||p.bbox.length!==4||!p.bbox.every(Number.isFinite)||!(0<=p.bbox[0]&&p.bbox[0]<p.bbox[2]&&p.bbox[2]<=1&&0<=p.bbox[1]&&p.bbox[1]<p.bbox[3]&&p.bbox[3]<=1))error('source panel');};
  if(!Array.isArray(data.instances)||!data.instances.length)error('parts');
  const ids=new Set<string>();for(const part of data.instances){if(!validatePart(part)||ids.has(part.instance_id)||part.geometry_ref.split('/').some((s:string)=>s==='..'||!s))error('part identity');panel(part.source);ids.add(part.instance_id);}
  if(!Array.isArray(data.chunks)||!data.chunks.length||!Array.isArray(data.step_index)||!data.step_index.length)error('empty chunks');
  const chunks:Chunk[]=data.chunks;
  chunks.forEach((chunk,index)=>{if(chunk.index!==index||!/^chunks\/[a-zA-Z0-9._-]+\.json$/.test(chunk.path)||!hash(chunk.sha256)||!Number.isInteger(chunk.bytes)||chunk.bytes<1||chunk.bytes>32*1024*1024||!Array.isArray(chunk.step_ids)||!chunk.step_ids.length)error('chunk metadata');});
  const introducedAt:Record<string,number>=Object.create(null);
  const introduced=new Set<string>(),stepIds=new Set<string>(),closedSections=new Set<string>();let priorSection='',priorMain=0,priorOrder=-1;const sectionOrder=[...sections.keys()];
  const stepIndex:IndexedStep[]=data.step_index.map((raw:any,index:number)=>{
    if(!raw||typeof raw!=='object')error('step index');
    if('poses' in raw||'visible_instance_ids' in raw||'active_instance_ids' in raw||'snapshot_loaded' in raw)error('noncompact step index');
    const step=adapted(raw,index) as unknown as IndexedStep; panel(step.source);
    if(typeof step.section_id!=='string'||sections.get(step.section_id)!==step.source.source_sha256||stepIds.has(step.step_id)||typeof step.step_id!=='string'||!step.step_id||typeof step.instruction!=='string'||!(step.substep_label===null||typeof step.substep_label==='string')||!['add_parts','build_subassembly','attach_subassembly','inspect'].includes(step.action)||!(step.assembly_group_id===null||typeof step.assembly_group_id==='string')||!Number.isInteger(step.chunk_index)||!chunks[step.chunk_index]?.step_ids.includes(step.step_id)||!(raw.main_step_number===null||Number.isInteger(raw.main_step_number)&&raw.main_step_number>0))error('step index');
    if(priorSection!==step.section_id){const order=sectionOrder.indexOf(step.section_id!);if(order<priorOrder||closedSections.has(step.section_id!))error('section order');priorOrder=order;if(priorSection)closedSections.add(priorSection);priorSection=step.section_id!;priorMain=0;}
    if(raw.main_step_number!==null){if(raw.main_step_number<priorMain)error('printed step order');priorMain=raw.main_step_number;}
    const list=step.introduced_instance_ids;if(!Array.isArray(list)||new Set(list).size!==list.length||list.some(id=>!ids.has(id)))error('instance references');
    for(const id of list){if(introduced.has(id))error('duplicate introduction');introduced.add(id);introducedAt[id]=index;}
    if(!Number.isInteger(step.visible_instance_count)||step.visible_instance_count<list.length||step.visible_instance_count>introduced.size||!Number.isInteger(step.active_instance_count)||step.active_instance_count<0||step.active_instance_count>step.visible_instance_count)error('snapshot counts');
    stepIds.add(step.step_id);return step;
  });
  if(introduced.size!==ids.size||chunks.flatMap(c=>c.step_ids).join('\0')!==stepIndex.map(s=>s.step_id).join('\0'))error('coverage');
  // Empty poses are transport placeholders only. The workspace never renders an unloaded snapshot.
  const scene:SceneManifest={schema_version:'1.0',set_number:data.set_number,guide_id:data.guide_id,revision:data.revision,source_sha256:data.source_sha256,coordinate_system:data.coordinate_system,status:data.status,geometry_check:data.geometry_check,connector_check:data.connector_check,physical_build_check:data.physical_build_check,instances:data.instances,reviews:[],sources:data.sources,geometry_base_url:geometry,steps:stepIndex.map(({chunk_index,visible_instance_count,active_instance_count,...step})=>({...step,visible_instance_ids:[],active_instance_ids:[],poses:{},snapshot_loaded:false}))};
  return freeze({scene,chunks,stepIndex,assetBase:base,introducedAt,...metadata});
}
const canonical=(value:any):string=>JSON.stringify(value&&typeof value==='object'?Array.isArray(value)?value.map(v=>JSON.parse(canonical(v))):Object.fromEntries(Object.keys(value).sort().map(k=>[k,JSON.parse(canonical(value[k]))])):value);
export class ReleaseLoader {
  readonly release:Release; private cache=new Map<number,Promise<StepSnapshot[]>>();
  constructor(value:unknown){this.release=parseRelease(value);}
  private load(index:number):Promise<StepSnapshot[]> {
    const existing=this.cache.get(index);if(existing)return existing;
    const chunk=this.release.chunks[index];
    const task=(async()=>{
      const response=await fetch(modelAssetUrl(new URL(chunk.path,this.release.assetBase)),{credentials:'omit'});
      if(!response.ok)throw new Error('This instruction could not be loaded. Please retry.');
      const length=response.headers.get('content-length');if(length&&Number(length)>chunk.bytes)error('chunk size mismatch');
      const reader=response.body?.getReader();if(!reader)error('empty chunk response');
      const bytes=new Uint8Array(chunk.bytes);let size=0;
      while(true){const packet=await reader!.read();if(packet.done)break;if(size+packet.value.length>bytes.length){await reader!.cancel();error('chunk size mismatch');}bytes.set(packet.value,size);size+=packet.value.length;}
      if(size!==chunk.bytes)error('chunk size mismatch');
      const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
      if(digest!==chunk.sha256)error('chunk checksum mismatch');
      const body=JSON.parse(new TextDecoder().decode(bytes));if(!Array.isArray(body.steps)||body.steps.length!==chunk.step_ids.length)error('chunk steps');
      return freeze(body.steps.map((raw:any,offset:number)=>{
        const stepIndex=this.release.stepIndex.findIndex(s=>s.step_id===chunk.step_ids[offset]);
        const step=adapted(raw,stepIndex) as unknown as StepSnapshot;
        const {section_id,printed_step_number,...v1}=step;
        if(!validateStep(v1))error('snapshot shape');
        const {poses,visible_instance_ids,active_instance_ids,...labels}=step;const {chunk_index,...expected}=this.release.stepIndex[stepIndex];
        const metadata={...labels,visible_instance_count:visible_instance_ids.length,active_instance_count:active_instance_ids.length};
        if(canonical(metadata)!==canonical(expected))error('snapshot differs from index');
        const visible=new Set(visible_instance_ids),active=new Set(active_instance_ids);
        if(visible.size!==visible_instance_ids.length||active.size!==active_instance_ids.length||visible_instance_ids.some(id=>!Object.hasOwn(this.release.introducedAt,id)||this.release.introducedAt[id]>stepIndex)||[...active_instance_ids,...step.introduced_instance_ids].some(id=>!visible.has(id)))error('snapshot visibility');
        if(Object.keys(poses).length!==visible.size||Object.keys(poses).some(id=>!visible.has(id)))error('snapshot poses');
        for(const pose of Object.values(poses))if(![...pose.position_ldu,...pose.quaternion_xyzw].every(Number.isFinite)||Math.abs(Math.hypot(...pose.quaternion_xyzw)-1)>1e-5)error('rotation');
        return {...step,snapshot_loaded:true};
      }));
    })();this.cache.set(index,task);task.catch(()=>this.cache.delete(index));return task;
  }
  async window(index:number):Promise<SceneManifest>{
    const metadata=this.release.stepIndex;const chunk=metadata[index].chunk_index;
    const needed=new Set([chunk]);for(const neighbour of [index-1,index+1])if(metadata[neighbour])needed.add(metadata[neighbour].chunk_index);
    // Keep all callout siblings available for one stable camera framing across Part / Attach.
    metadata.forEach(s=>{if(group(s)===group(metadata[index]))needed.add(s.chunk_index);});
    const loaded=(await Promise.all([...needed].map(i=>this.load(i)))).flat();
    for(const key of this.cache.keys())if(!needed.has(key))this.cache.delete(key);
    const byId=new Map(loaded.map(s=>[s.step_id,s]));
    return freeze({...this.release.scene,steps:this.release.scene.steps.map(s=>byId.get(s.step_id)??s)});
  }
}
