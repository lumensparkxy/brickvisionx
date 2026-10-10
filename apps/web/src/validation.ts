import Ajv2020 from 'ajv/dist/2020';
import schema from '../../../packages/contracts/scene.schema.json';
import type { SceneManifest, SourcePanel, SetInfo } from './contracts';
const validate = new Ajv2020({ strict: false, useDefaults: true }).compile<SceneManifest>(schema);
const fail = (message: string): never => { throw new Error(`Invalid scene: ${message}`); };
export function parseScene(value: unknown): SceneManifest {
  // Clone before defaults and freeze after validation: API data never becomes mutable viewer state.
  const scene: unknown = structuredClone(value);
  if (!validate(scene)) fail(validate.errors?.map(e => `${e.instancePath} ${e.message}`).join('; ') ?? 'schema mismatch');
  const result = scene as SceneManifest;
  const ids = new Set(result.instances.map(p => p.instance_id));
  if (ids.size !== result.instances.length) fail('duplicate physical instance');
  const panel = (p: SourcePanel) => {
    const [x0,y0,x1,y1] = p.bbox;
    if (p.source_sha256 !== result.source_sha256 || !(0 <= x0 && x0 < x1 && x1 <= 1 && 0 <= y0 && y0 < y1 && y1 <= 1)) fail('source mismatch or invalid crop');
  };
  result.instances.forEach(p => { panel(p.source); if (p.geometry_ref.split('/').some(s => s === '..' || !s)) fail('unsafe geometry reference'); });
  const introduced = new Set<string>(); const steps = new Set<string>(); let main = 0;
  for (const step of result.steps) {
    panel(step.source);
    if (steps.has(step.step_id) || step.main_step_number < main) fail('duplicate or unordered step');
    main = step.main_step_number; steps.add(step.step_id);
    for (const list of [step.introduced_instance_ids, step.active_instance_ids, step.visible_instance_ids]) {
      if (new Set(list).size !== list.length || list.some(id => !ids.has(id))) fail('invalid instance reference');
    }
    for (const id of step.introduced_instance_ids) { if (introduced.has(id)) fail('instance introduced twice'); introduced.add(id); }
    const visible = new Set(step.visible_instance_ids);
    if (step.visible_instance_ids.some(id => !introduced.has(id)) || [...step.active_instance_ids, ...step.introduced_instance_ids].some(id => !visible.has(id))) fail('visibility mismatch');
    if (Object.keys(step.poses).length !== visible.size || Object.keys(step.poses).some(id => !visible.has(id))) fail('snapshot pose mismatch');
    for (const pose of Object.values(step.poses)) {
      if (![...pose.position_ldu,...pose.quaternion_xyzw].every(Number.isFinite) || Math.abs(Math.hypot(...pose.quaternion_xyzw)-1) > 1e-5) fail('invalid pose');
    }
  }
  if (introduced.size !== ids.size) fail('unintroduced instance');
  if (result.status.endsWith('_reviewed') && !result.reviews.some(r => r.actor_type === (result.status === 'human_reviewed' ? 'human' : 'agent') && r.reviewed_revision === result.revision && r.decision === 'accepted')) fail('missing review evidence');
  const freeze = (v: unknown) => { if (v && typeof v === 'object') { Object.values(v).forEach(freeze); Object.freeze(v); } };
  freeze(result); return result;
}
export function parseSet(value: unknown, publicMode = false): SetInfo {
  const data = value as SetInfo;
  const official = (url: unknown) => { if (typeof url !== 'string') return false; try { const u = new URL(url); return u.protocol === 'https:' && (u.hostname === 'lego.com' || u.hostname.endsWith('.lego.com')); } catch { return false; } };
  const unknown = publicMode && data?.name === null && data?.official_page === null && Array.isArray(data?.guides) && data.guides.length === 0;
  if (!data || typeof data.set_number !== 'string' || !/^\d{4,7}$/.test(data.set_number) || (!unknown && (typeof data.name !== 'string' || !official(data.official_page))) || !Array.isArray(data.guides) || data.guides.some(g => !g || !/^[a-z0-9-]+$/.test(g.guide_id) || typeof g.label !== 'string' || !official(g.pdf_url) || (g.expected_main_steps !== null && (!Number.isInteger(g.expected_main_steps) || g.expected_main_steps < 1)) || (g.tutorial_available !== undefined && typeof g.tutorial_available !== 'boolean'))) throw new Error('The server returned invalid set information.');
  for(const guide of data.guides){
    if((guide.release_kind!==undefined&&guide.release_kind!=='unverified_alpha')
      ||(guide.alpha_available!==undefined&&typeof guide.alpha_available!=='boolean')
      ||(guide.status!==undefined&&!['published','not_ready','alpha_unverified'].includes(guide.status))
      ||(guide.release_kind==='unverified_alpha'&&(guide.tutorial_available!==true||guide.alpha_available!==true||guide.status!=='alpha_unverified'))
      ||(guide.release_kind===undefined&&(guide.alpha_available===true||guide.status==='alpha_unverified')))
      throw new Error('The server returned invalid alpha model information.');
  }
  return {...data,guides:data.guides.map(g=>({...g,tutorial_available:g.tutorial_available ?? false}))};
}
