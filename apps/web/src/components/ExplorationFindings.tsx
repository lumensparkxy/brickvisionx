import { useState } from 'react';
import type { ExplorationStatus } from '../api';
import type { StepSnapshot } from '../contracts';

const labels:Record<string,string>={aabb_overlap_candidate:'Possible overlap',exact_coincident_geometry:'Duplicate placement',symmetric_coincident_geometry:'Duplicate placement',
  near_connector_gap:'Possible seating gap',floating_supported_instance:'Possibly floating piece',
  unsupported_connector_geometry:'Connection not checked',source_view:'Camera alignment',
  no_candidate:'Missing reconstruction',nonrigid_group:'Subassembly shape changed'};

export default function ExplorationFindings({diagnostics,step,onNavigate}:{diagnostics:ExplorationStatus;step:StepSnapshot;onNavigate:(id:string)=>void}) {
  const [all,setAll]=useState(false);
  const current=diagnostics.instructions.filter(i=>i.step_ids.includes(step.step_id));
  const entries=all?diagnostics.instructions:current;
  const count=current.reduce((sum,i)=>sum+i.finding_count,0);
  return <details className="exploration-findings">
    <summary>Improvement findings ({count} for this instruction)</summary>
    <p className="muted">{diagnostics.processed_panels} instructions processed · {diagnostics.reconstructed_panels} reconstructed. Provisional choices remain open to correction.</p>
    <div className="parts-toggle"><button className={!all?'selected':''} aria-pressed={!all} onClick={()=>setAll(false)}>This instruction</button><button className={all?'selected':''} aria-pressed={all} onClick={()=>setAll(true)}>All findings</button></div>
    {entries.map(i=><section key={i.ordinal} aria-label={`Findings for instruction ${i.main_step_number??i.ordinal+1}`}>
      <p><strong>{i.main_step_number===null?'Unnumbered instruction':`Step ${i.main_step_number}`}</strong>{!i.reconstructed&&' · No reconstruction available'} · {i.finding_count} findings</p>
      {i.needs_recheck&&<p className="muted">These findings were recorded before the correction and need a fresh review.</p>}
      {i.findings.length?<ul>{i.findings.map((f,n)=><li key={n}><span className="finding-category">{labels[f.category]??f.category.replaceAll('_',' ')}</span>{f.message}{f.instance_ids.length>0&&<details><summary>Affected pieces ({f.instance_ids.length})</summary><p>{f.instance_ids.join(', ')}</p></details>}</li>)}</ul>:<p>No findings recorded. This does not establish correctness.</p>}
      {i.finding_count>i.findings.length&&<p>Additional findings are retained in the local evaluation report.</p>}
      <div className="finding-actions">{i.step_ids[0]&&i.step_ids[0]!==step.step_id&&<button className="secondary" onClick={()=>onNavigate(i.step_ids[0])}>Inspect step {i.main_step_number??i.ordinal+1}</button>}<a href={`/api/v1/sources/${encodeURIComponent(step.source.source_sha256)}/pages/${i.page_index}`} target="_blank" rel="noreferrer">Source page {i.page_index+1} ↗</a></div>
    </section>)}
    {!entries.length&&<p>No diagnostic record is available for this snapshot.</p>}
  </details>;
}
