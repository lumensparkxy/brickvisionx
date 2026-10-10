import { useEffect, useRef, useState, type FormEvent } from 'react';
import { post, request } from '../api';
import { parseScene } from '../validation';
import type { SceneManifest, StepSnapshot } from '../contracts';
import { findingSteps, findingTitle, groupFindings, type Finding } from '../review';
export default function ReviewPanel({ scene, step, onScene, onNavigate }: {scene: SceneManifest; step: StepSnapshot; onScene: (scene: SceneManifest) => void; onNavigate: (stepId:string) => void}) {
  const requestIdentity = useRef<{body:string;key:string}|null>(null);
  const [items,setItems] = useState<Finding[]>([]); const [error,setError] = useState(''); const [busy,setBusy] = useState(false);
  const [scope,setScope] = useState<'current'|'all'>('current');
  const [loading,setLoading] = useState(true); const [findingsError,setFindingsError] = useState(''); const [reload,setReload] = useState(0);
  const [id,setId] = useState(step.active_instance_ids[0] ?? step.visible_instance_ids[0]);
  const part = scene.instances.find(p => p.instance_id === id)!;
  const [kind,setKind] = useState<'pose'|'mapping'|'group'>('pose'); const [position,setPosition] = useState(''); const [rotation,setRotation] = useState('');
  const [partId,setPartId] = useState(''); const [color,setColor] = useState(''); const [geometry,setGeometry] = useState(''); const [reason,setReason] = useState('');
  const [group,setGroup] = useState(step.assembly_group_id??'');
  const [actorType,setActorType] = useState<'human'|'agent'>('human');
  const [actor,setActor] = useState('local-browser-operator'); const [snap,setSnap] = useState('1');
  const reset = () => { const pose = step.poses[id]; setPosition(pose?.position_ldu.join(', ') ?? ''); setRotation(pose?.quaternion_xyzw.join(', ') ?? ''); setPartId(part.part_id); setColor(part.color_code); setGeometry(part.geometry_ref); setReason(''); setGroup(step.assembly_group_id??''); };
  useEffect(() => { if (!step.visible_instance_ids.includes(id)) setId(step.active_instance_ids[0] ?? step.visible_instance_ids[0]); }, [step,id]);
  useEffect(() => { reset(); }, [id,step.step_id]);
  useEffect(() => {
    let live = true; setLoading(true); setFindingsError(''); setItems([]);
    request<{items:Finding[]}>(`/reconstructions/${encodeURIComponent(scene.revision)}/review-items`).then(data => {
      if (!data || !Array.isArray(data.items) || data.items.some(item => !item || typeof item.item_id !== 'string' || typeof item.kind !== 'string' || typeof item.message !== 'string' || typeof item.status !== 'string' || !Array.isArray(item.instance_ids) || !Array.isArray(item.step_ids) || !item.source || item.source.source_sha256 !== scene.source_sha256 || !Number.isInteger(item.source.page_index) || item.source.page_index < 0)) throw new Error('Invalid review findings received.');
      if(live) setItems(data.items);
    }).catch(e => {if(live)setFindingsError(e.message);}).finally(() => {if(live)setLoading(false);});
    return () => {live=false;};
  }, [scene.revision,reload]);
  const scopedItems = scope === 'all' ? items : items.filter(item => findingSteps(item,scene).some(s => s.step_id === step.step_id) || (!item.step_ids.length && !item.instance_ids.length));
  const groups = groupFindings(scopedItems);
  const inspect = (stepId:string, instanceId?:string) => { if(instanceId) setId(instanceId); onNavigate(stepId); };
  const findingContext = (item:Finding) => {
    const steps = findingSteps(item,scene);
    const pieces = item.instance_ids.map(instanceId => scene.instances.find(part => part.instance_id === instanceId)).filter(part => !!part);
    return <div className="finding-context" key={item.item_id}>
      <p>{pieces.length ? pieces.map(part => `${part.instance_id} · part ${part.part_id} · colour ${part.color_code}`).join('; ') : 'Whole assembly'}</p>
      <div className="finding-actions">{item.kind === 'assembly_review' && !pieces.length ? <span className="muted">Applies across all instructions.</span> : steps.map(s => <button type="button" className="secondary" key={s.step_id} onClick={() => inspect(s.step_id,item.instance_ids.find(id => s.visible_instance_ids.includes(id)))}>
        Inspect step {s.main_step_number}{s.substep_label ? ` · ${s.substep_label}` : ''}
      </button>)}<a href={`/api/v1/sources/${encodeURIComponent(item.source.source_sha256)}/pages/${item.source.page_index}`} target="_blank" rel="noreferrer">Evidence page {item.source.page_index+1} ↗</a></div>
      <small className="muted">Record: {item.item_id}</small>
    </div>;
  };
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      let command: unknown;
      if (kind === 'pose') {
        const p = position.split(',').map(Number); const q = rotation.split(',').map(Number); const grid = Number(snap);
        if (p.length !== 3 || q.length !== 4 || ![...p,...q].every(Number.isFinite) || Math.abs(Math.hypot(...q)-1)>1e-5) throw new Error('Use three finite coordinates and a unit quaternion [x, y, z, w].');
        command = {type:'pose',step_id:step.step_id,instance_id:id,pose:{position_ldu:p.map(n=>Math.round(n/grid)*grid),quaternion_xyzw:q}};
      } else if(kind==='group') command={type:'group',step_id:step.step_id,assembly_group_id:group};
      else command = {type:'mapping',instance_id:id,part_id:partId,color_code:color,geometry_ref:geometry};
      const body = {expected_revision:scene.revision,actor_id:actor,actor_type:actorType,reason,source:step.source,command};
      const serialized = JSON.stringify(body);
      if (requestIdentity.current?.body !== serialized) requestIdentity.current = {body:serialized,key:crypto.randomUUID()};
      const result = await post<{scene:unknown}>(`/reconstructions/${encodeURIComponent(scene.revision)}/corrections`, body,requestIdentity.current.key);
      onScene(parseScene(result.scene));
    } catch(e) {setError(e instanceof Error?e.message:'Correction failed.');} finally {setBusy(false);}
  }
  return <section className="review-panel" aria-label="Reconstruction review"><h2>Review candidate</h2>
    <p>Check uncertain parts and placements against the official guide. This optional reviewer tool helps correct the 3D reconstruction; it is not a building step.</p>
    <p className="muted">A correction saves a new revision and preserves the original. Saving does not certify the assembly or record human acceptance.</p>
    <div className="review-toolbar"><label>Show findings<select value={scope} onChange={e=>setScope(e.target.value as 'current'|'all')}><option value="current">Current instruction</option><option value="all">All instructions</option></select></label>
      {!loading && !findingsError && <p role="status">{scopedItems.length} of {items.length} findings · {groups.length} grouped topics</p>}</div>
    {loading ? <p role="status">Loading review findings…</p> : findingsError ? <div role="alert" className="notice">Could not load review findings: {findingsError} <button type="button" className="secondary" onClick={()=>setReload(n=>n+1)}>Retry findings</button></div> : groups.length ?
      <ul className="finding-groups">{groups.map(group => <li className="finding-card" key={group.key}>
        <div className="finding-heading"><h3>{findingTitle[group.kind] ?? group.kind.replaceAll('_',' ')}</h3><span className="pill">{group.status.replaceAll('_',' ')}</span></div>
        <p>{group.message}</p>
        {group.items.length > 1 ? <details><summary>Affected pieces and instructions ({group.items.length} findings)</summary>{group.items.map(findingContext)}</details> : group.items[0].instance_ids.length > 1 ? <details><summary>Affected pieces and instructions ({group.items[0].instance_ids.length} pieces)</summary>{findingContext(group.items[0])}</details> : findingContext(group.items[0])}
      </li>)}</ul> : <p className="muted">{items.length ? 'No recorded findings for this instruction. Select All instructions to see the remaining checks.' : 'No recorded findings for this revision.'} This does not establish that the assembly is verified.</p>}
    <details className="advanced-corrections"><summary>Advanced corrections</summary><p>Edit part identity, position or subassembly association only when the source evidence supports the change.</p>
    <form onSubmit={save} className="review-form"><label htmlFor="review-instance">Physical instance<select id="review-instance" value={id} onChange={e=>setId(e.target.value)}>{step.visible_instance_ids.map(value=><option key={value}>{value}</option>)}</select></label>
      <label>Correction type<select value={kind} onChange={e=>setKind(e.target.value as 'pose'|'mapping'|'group')}><option value="pose">Pose at this instruction</option><option value="mapping">Part and colour mapping</option><option value="group">Subassembly group association</option></select></label>
      {kind==='pose'?<><label>Translation [x, y, z] in LDU<input value={position} onChange={e=>setPosition(e.target.value)} required/></label><label>Snap translation<select value={snap} onChange={e=>setSnap(e.target.value)}><option value="1">1 LDU</option><option value="8">8 LDU · plate height</option><option value="20">20 LDU · stud pitch</option><option value="0.001">0.001 LDU</option></select></label><label>Rotation quaternion [x, y, z, w]<input value={rotation} onChange={e=>setRotation(e.target.value)} required/></label></>:kind==='group'?<label>Assembly group ID<input value={group} onChange={e=>setGroup(e.target.value)} required/></label>:<><label>Part ID<input value={partId} onChange={e=>setPartId(e.target.value)} required/></label><label>Colour code<input value={color} onChange={e=>setColor(e.target.value)} required/></label><label>Local geometry reference<input value={geometry} onChange={e=>setGeometry(e.target.value)} pattern="(parts|p)/.+\.dat" required/></label></>}
      <label>Correction actor<select value={actorType} onChange={e=>setActorType(e.target.value as 'human'|'agent')}><option value="human">Locally declared human operator</option><option value="agent">Automated agent</option></select></label><label>Reviewer name<input value={actor} onChange={e=>setActor(e.target.value)} required/></label><label className="full-row">Reason and source evidence<textarea value={reason} onChange={e=>setReason(e.target.value)} required placeholder="Describe what the visible source panel establishes."/></label>
      <p className="muted full-row">Actor: {actorType==='human'?'locally declared human operator':'automated agent'} · Source: page {step.source.page_index+1}, step {step.main_step_number} · Mapping origin: {part.origin.replaceAll('_',' ')}. Automated agents must use the agent correction API.</p>
      <div className="button-row full-row"><button disabled={busy}>Save revision and revalidate</button><button className="secondary" type="button" onClick={reset}>Undo unsaved changes</button></div>
    </form></details>{error&&<p role="alert" className="notice">{error}</p>}
    <p className="muted">Structural checks run on save. Geometry, connector and physical checks are invalidated and remain not run until separately executed.</p>
    <details><summary>Review history ({scene.reviews.length})</summary>{scene.reviews.map((review,i)=><p key={i}>{review.actor_type} · {review.actor_id} · {review.decision} · {review.reviewed_revision}</p>)}</details>
  </section>;
}
