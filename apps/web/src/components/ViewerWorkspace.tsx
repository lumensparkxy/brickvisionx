import { useEffect, useRef, useState } from 'react';
import IconChevronLeft from '@tabler/icons-react/dist/esm/icons/IconChevronLeft.mjs';
import IconChevronRight from '@tabler/icons-react/dist/esm/icons/IconChevronRight.mjs';
import IconRotate from '@tabler/icons-react/dist/esm/icons/IconRotate.mjs';
import IconRotateClockwise from '@tabler/icons-react/dist/esm/icons/IconRotateClockwise.mjs';
import IconPlus from '@tabler/icons-react/dist/esm/icons/IconPlus.mjs';
import IconMinus from '@tabler/icons-react/dist/esm/icons/IconMinus.mjs';
import IconArrowsMoveHorizontal from '@tabler/icons-react/dist/esm/icons/IconArrowsMoveHorizontal.mjs';
import IconFocus2 from '@tabler/icons-react/dist/esm/icons/IconFocus2.mjs';
import IconPlayerPlay from '@tabler/icons-react/dist/esm/icons/IconPlayerPlay.mjs';
import IconPlayerPause from '@tabler/icons-react/dist/esm/icons/IconPlayerPause.mjs';
import IconPlayerStop from '@tabler/icons-react/dist/esm/icons/IconPlayerStop.mjs';
import IconCube from '@tabler/icons-react/dist/esm/icons/IconCube.mjs';
import IconX from '@tabler/icons-react/dist/esm/icons/IconX.mjs';
import IconInfoCircle from '@tabler/icons-react/dist/esm/icons/IconInfoCircle.mjs';
import IconBook2 from '@tabler/icons-react/dist/esm/icons/IconBook2.mjs';
import type { Guide, SceneManifest } from '../contracts';
import type { AlphaReleaseMetadata, ReleaseLoader } from '../releases';
import type { ImageQuality, ExplorationStatus } from '../api';
import ExplorationFindings from './ExplorationFindings';
import { partsList, readProgress, saveProgress } from '../state';
import AssemblyViewport, { type CameraCommand } from './AssemblyViewport';
import SourcePanel from './SourcePanel';
import ReviewPanel from './ReviewPanel';
export default function ViewerWorkspace({ scene: initialScene, guide, onClose, onScene, publicMode=false, releaseAlpha, previewMode=false, previewExperiment, previewJobId, previewQuality, previewGenerationMode, previewArtifactKind, previewUncertaintyNotes, previewCoverage, previewSourceCoverage, exploration, sourceImages=!publicMode, releaseLoader }: {publicMode?:boolean; releaseAlpha?:AlphaReleaseMetadata; previewMode?:boolean; previewExperiment?:string; previewJobId?:string; previewQuality?:ImageQuality; previewGenerationMode?:'standard'|'alpha_fast'; previewArtifactKind?:string; previewUncertaintyNotes?:string[]; previewCoverage?:string; previewSourceCoverage?:string; exploration?:ExplorationStatus|null; sourceImages?:boolean; releaseLoader?:ReleaseLoader; scene: SceneManifest; guide: Guide; onClose: () => void; onScene: (scene: SceneManifest) => void}) {
  const [scene,setLoadedScene] = useState(initialScene);
  const [chunkError,setChunkError] = useState('');
  const [chunkRetry,setChunkRetry] = useState(0);
  const [thumbnails,setThumbnails] = useState<Record<string,string>>({});
  const [colorNames,setColorNames] = useState<Record<string,string>>({});
  const [index,setIndex] = useState(()=>readProgress(scene)); const [replay,setReplay] = useState(0);
  useEffect(()=>{if(!releaseLoader){setLoadedScene(initialScene);return;}let stopped=false;setChunkError('');releaseLoader.window(index).then(value=>{if(!stopped){setLoadedScene(value);}}).catch(e=>{if(!stopped)setChunkError(e instanceof Error?e.message:'Instruction unavailable.');});return()=>{stopped=true;};},[initialScene,releaseLoader,index,chunkRetry]);
  const snapshotReady=!releaseLoader||scene.steps[index].snapshot_loaded===true;
  const [playback,setPlayback] = useState<'idle'|'playing'|'paused'>('idle');
  const [animationDone,setAnimationDone] = useState(false); const [ready,setReady] = useState(false);
  const [needsReplay,setNeedsReplay] = useState(false);
  const [buildFinished,setBuildFinished] = useState(false);
  const [command,setCommand] = useState<CameraCommand>({action:'reset',token:0});
  const [tab,setTab] = useState('3D'); const [allParts,setAllParts] = useState(false); const [review,setReview] = useState(false);
  const [overlayReview,setOverlayReview] = useState(()=>matchMedia('(max-width:1200px)').matches);
  const [phone,setPhone] = useState(()=>matchMedia('(max-width:650px)').matches);
  const reviewDialog = useRef<HTMLDialogElement>(null); const reviewButton = useRef<HTMLButtonElement>(null);
  useEffect(()=>{const overlay=matchMedia('(max-width:1200px)');const narrow=matchMedia('(max-width:650px)');const update=()=>{setOverlayReview(overlay.matches);setPhone(narrow.matches);};overlay.addEventListener('change',update);narrow.addEventListener('change',update);return()=>{overlay.removeEventListener('change',update);narrow.removeEventListener('change',update);};},[]);
  useEffect(()=>{if(!review)return;const dialog=reviewDialog.current;if(!dialog)return;if(overlayReview)dialog.showModal();else dialog.show();return()=>{dialog.close();reviewButton.current?.focus();};},[review,overlayReview]);
  const step = scene.steps[index]; const rows = partsList(scene,allParts?undefined:step.introduced_instance_ids);
  const change = (next:number) => {setPlayback('idle');setBuildFinished(false);setIndex(Math.max(0,Math.min(scene.steps.length-1,next)));};
  const startBuild = () => {setReview(false);setTab('3D');setAllParts(false);setBuildFinished(false);setAnimationDone(false);setNeedsReplay(true);setIndex(0);setPlayback('playing');};
  useEffect(()=>{
    if(playback!=='playing'||!animationDone||!ready||!snapshotReady||needsReplay||chunkError)return;
    const timer=window.setTimeout(()=>{
      if(index===scene.steps.length-1){setPlayback('idle');setBuildFinished(true);}
      else {setAnimationDone(false);setNeedsReplay(true);setIndex(i=>i+1);}
    },1000);
    return()=>window.clearTimeout(timer);
  },[playback,animationDone,ready,snapshotReady,needsReplay,chunkError,index,scene.steps.length]);
  // A compact release can temporarily unmount the renderer when changing chunks.
  // Keep playback intent and start this snapshot's replay only after it is ready.
  useEffect(()=>{
    if(playback==='idle'){setNeedsReplay(false);return;}
    if(!ready||!snapshotReady){setAnimationDone(false);setNeedsReplay(true);return;}
    if(needsReplay&&!chunkError){setNeedsReplay(false);setReplay(n=>n+1);}
  },[playback,ready,snapshotReady,needsReplay,chunkError]);
  useEffect(()=>{if(!snapshotReady||chunkError)setReady(false);},[snapshotReady,chunkError]);
  useEffect(()=>{if(chunkError){setPlayback(state=>state==='playing'?'paused':state);setAnimationDone(false);}},[chunkError]);
  useEffect(()=>{
    const pauseHidden=()=>{if(document.hidden)setPlayback(state=>state==='playing'?'paused':state);};
    document.addEventListener('visibilitychange',pauseHidden);return()=>document.removeEventListener('visibilitychange',pauseHidden);
  },[]);
  useEffect(()=>{saveProgress(scene,index);},[scene,index]);
  useEffect(()=>{
    const handler=(event: KeyboardEvent)=>{if(event.target instanceof HTMLElement && (event.target.isContentEditable||['INPUT','SELECT','TEXTAREA','BUTTON'].includes(event.target.tagName)))return;
      if(event.key==='ArrowLeft'){event.preventDefault();setPlayback('idle');setBuildFinished(false);setIndex(i=>Math.max(0,i-1));}if(event.key==='ArrowRight'){event.preventDefault();setPlayback('idle');setBuildFinished(false);setIndex(i=>Math.min(scene.steps.length-1,i+1));}};
    window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);
  },[scene.steps.length]);
  const camera=(action:CameraCommand['action'])=>setCommand(c=>({action,token:c.token+1}));
  const groupKey=(s:typeof step)=>`${s.section_id??''}:${s.printed_step_number===null?s.step_id:s.main_step_number}`;
  const stepLabel=(s:typeof step)=>s.printed_step_number===null?'Unnumbered instruction':`Step ${s.main_step_number}`;
  const mainSteps = new Set(scene.steps.filter(s=>s.printed_step_number!==null&&s.main_step_number!==null).map(groupKey)).size;
  const assisted = scene.instances.some(p=>p.origin==='pdf_assisted_authoring');
  const artifactLabel = exploration||releaseAlpha?.artifact_kind==='exploration_candidate'?'Exploration candidate':releaseAlpha||previewMode&&previewArtifactKind==='pdf_assisted_alpha_completion'?'PDF-assisted alpha completion':previewMode&&previewArtifactKind==='automatic_alpha_with_agent_corrections'?'Alpha model with agent source corrections':assisted?'PDF-assisted reference':'Reconstruction candidate';
  const fastAlpha = previewMode && previewGenerationMode==='alpha_fast';
  const alpha = previewMode && (fastAlpha || previewQuality?.profile==='alpha');
  const selectedSourceCovered = fastAlpha && ['assisted_complete_source_review_alpha_unverified','all_pages_processed_approximate_unverified'].includes(previewSourceCoverage??'');
  // Polling can describe a newer checkpoint while this viewer keeps its prior snapshot.
  const imageChecks = previewQuality?.relaxed_steps.filter(check=>scene.steps.some(s=>s.step_id===check.step_id))??[];
  const mainEntries=scene.steps.filter((s,i)=>scene.steps.findIndex(other=>groupKey(other)===groupKey(s))===i);
  const siblings = scene.steps.map((s,i)=>({step:s,index:i})).filter(s=>groupKey(s.step)===groupKey(step));
  const substepName = (s: typeof step) => s.action==='attach_subassembly'?'Attach':s.substep_label?.replace('callout-','Part ') || 'Build';
  const groupName = step.assembly_group_id?.replaceAll('-',' ').replace(/^./,s=>s.toUpperCase());
  const assemblyOverview = step.action === 'inspect' && step.introduced_instance_ids.length === 0;
  const replayStep = () => {setPlayback('idle');setBuildFinished(false);setReplay(n=>n+1);};
  return <section className="workspace">
    <header className="studio-header">
      <button className="brand studio-brand" onClick={onClose} aria-label="Back to set lookup">Guide2Build <span>3D</span></button>
      <div className="workspace-heading"><h1><span>{scene.set_number}</span><span className="header-divider">/</span>{guide.label}</h1><span className="candidate-status">{exploration?'Exploration · provisional':releaseAlpha?'Alpha model · unverified':alpha?'Alpha sample · unverified':`${previewMode?'Local engine candidate':publicMode?'Published tutorial':assisted?'PDF-assisted':'Candidate'} · ${scene.status.replaceAll('_',' ')}`}</span></div>
      <div className="studio-actions">{!publicMode&&<button ref={reviewButton} className="secondary review-toggle" aria-expanded={review} onClick={()=>{setPlayback(state=>state==='playing'?'paused':state);setReview(v=>!v);}}>{review?'Close review':'Review candidate'}</button>}
      <details className="provenance"><summary aria-label="Source, revision and checks" title="Source, revision and checks"><IconInfoCircle size={21} aria-hidden="true"/><span className="sr-only">Source, revision and checks</span></summary><div className="provenance-content"><h2>Reconstruction details</h2>
        {releaseAlpha&&<><p><strong>Alpha model · unverified</strong><br/>Approximate reconstruction from official instructions. Part choices, colours and placements are unverified; visible gaps or overlaps may remain.</p><p>{releaseAlpha.coverage_text}</p>{releaseAlpha.uncertainty_notes.length>0&&<ul>{releaseAlpha.uncertainty_notes.map((note,i)=><li key={i}>{note}</li>)}</ul>}</>}
        {fastAlpha&&<><p><strong>Alpha sample · unverified</strong><br/>Approximate model from official instructions. Colour, part choice and placement are unverified; visible gaps or overlaps may remain. Camera alignment has not been checked.</p>{previewCoverage&&<p>{previewCoverage}</p>}{previewUncertaintyNotes&&previewUncertaintyNotes.length>0&&<ul>{previewUncertaintyNotes.map((note,i)=><li key={i}>{note}</li>)}</ul>}</>}
        {alpha&&!fastAlpha&&previewQuality&&<><p><strong>Alpha sample · unverified</strong><br/>Image alignment tolerance: {previewQuality.max_rms_pixels} px RMS (strict: {previewQuality.strict_max_rms_pixels} px), {previewQuality.max_point_pixels} px per landmark.</p>{imageChecks.map(check=><p key={check.step_id}>Instruction {scene.steps.find(s=>s.step_id===check.step_id)?.main_step_number??check.step_id}: {check.rms_pixels.toFixed(2)} px RMS, {check.max_error_pixels.toFixed(2)} px worst landmark. Exceeds strict image alignment; needs review.</p>)}</>}
        {exploration&&<p><strong>Complete-booklet exploration</strong><br/>{previewCoverage}<br/>Quality findings guide later repairs. These snapshots remain provisional.<br/>{exploration.model_calls_used} of {exploration.max_model_calls} model calls used across this correction lineage.</p>}
        {previewMode&&<p>Local engine candidate · unpublished<br/>Experiment: {previewExperiment??'Not recorded in this render session'}{previewJobId&&<><br/>Job: {previewJobId}</>}</p>}
        <p><strong>{artifactLabel} · {scene.status.replaceAll('_',' ')}</strong></p>
        <p>{assisted?'Authored from source evidence; not an automatic PDF conversion. ':''}{releaseAlpha?'Human review: not run':`Human acceptance: ${scene.status==='human_reviewed'?'recorded':'not recorded'}`} · Physical build: {scene.physical_build_check.replaceAll('_',' ')}</p>
        <p>Coverage: {releaseAlpha?`${mainSteps} numbered main steps in this alpha model`:selectedSourceCovered ? `${mainSteps} numbered main steps across this candidate` : guide.expected_main_steps == null ? `${mainSteps} main steps in this candidate; full instruction count unverified` : `${mainSteps} of ${guide.expected_main_steps} main steps`} · {scene.steps.length} instructions · {scene.instances.length} {releaseAlpha?'model components':'physical pieces'}</p>
        <p>Revision: {scene.revision}<br/>Source SHA-256: <code>{scene.source_sha256}</code></p><p>Geometry: {scene.geometry_check} · Connections: {scene.connector_check} · Physical build: {scene.physical_build_check}</p>
        {releaseLoader&&<p><a href={new URL('ldraw/NOTICES.txt',releaseLoader.release.assetBase).href} target="_blank" rel="noreferrer">Individual geometry notices ↗</a><br/><a href="https://www.ldraw.org/article/227.html" target="_blank" rel="noreferrer">LDraw licences and usage ↗</a></p>}
        <p>Passing structural checks does not establish physical assembly or strength.</p>
      </div></details></div>
    </header>
    <div className={`workspace-grid${review?' review-open':''}`} data-mobile-tab={tab}>
      <div className="instruction-rail">
        <section className="instruction-context" aria-label="Current instruction">
          <span className="eyebrow">INSTRUCTION {index+1} OF {scene.steps.length}</span>
          <h2>{stepLabel(step)}{!step.section_id&&guide.expected_main_steps != null && <span> of {guide.expected_main_steps}</span>}</h2>
          <div className="instruction-copy-slot"><p className="instruction-copy">{step.instruction}</p>{siblings.length>1&&siblings.map(s=><p key={s.index} className="instruction-copy instruction-copy-sizer" aria-hidden="true">{s.step.instruction}</p>)}</div>
          {groupName&&<p className="group-label">{groupName} · {substepName(step)}</p>}
          {siblings.length>1&&<nav className="substep-navigation" aria-label={`Step ${step.main_step_number} substeps`}>{siblings.map(s=><button key={s.index} aria-current={s.index===index?'step':undefined} onClick={()=>change(s.index)}>{substepName(s.step)}</button>)}</nav>}
        </section>
        <div className="mobile-tabs" role="tablist" aria-label="Workspace panels">{['3D','Guide','Pieces'].map(value=><button id={`tab-${value}`} role="tab" tabIndex={tab===value?0:-1} aria-selected={tab===value} aria-controls={`panel-${value}`} key={value} onKeyDown={event=>{const panels=['3D','Guide','Pieces'];const current=panels.indexOf(value);const next=event.key==='ArrowRight'?(current+1)%3:event.key==='ArrowLeft'?(current+2)%3:event.key==='Home'?0:event.key==='End'?2:-1;if(next>=0){event.preventDefault();setTab(panels[next]);document.getElementById(`tab-${panels[next]}`)?.focus();}}} onClick={()=>setTab(value)}>{value}</button>)}</div>
        <aside id="panel-Guide" role={phone?'tabpanel':undefined} aria-labelledby={phone?'tab-Guide':undefined} className="source-pane" tabIndex={0} aria-label="Official guide panel"><div className="pane-heading"><h2><IconBook2 size={18} aria-hidden="true"/>Original guide</h2><span className="pill">Page {step.source.page_index+1}</span></div><p className="source-step-label">{step.printed_step_number===null?'Unnumbered instruction':`Main step ${step.main_step_number}`}{step.substep_label?` · ${substepName(step)}`:''}</p><SourcePanel panel={step.source} officialOnly={!sourceImages} officialUrl={scene.sources?.find(s=>s.source_sha256===step.source.source_sha256)?.official_url??guide.pdf_url} bookletLabel={scene.sources?.find(s=>s.source_sha256===step.source.source_sha256)?.guide_id??guide.label}/></aside>
        <aside id="panel-Pieces" role={phone?'tabpanel':undefined} aria-labelledby={phone?'tab-Pieces':undefined} className="step-pane" tabIndex={0} aria-label="Instruction details and parts">
          <div className="parts-toggle"><button className={!allParts?'selected':''} aria-pressed={!allParts} onClick={()=>setAllParts(false)}>New pieces</button><button className={allParts?'selected':''} aria-pressed={allParts} onClick={()=>setAllParts(true)}>Full parts list</button></div>
          {rows.length?<table className="parts-table"><thead className="sr-only"><tr><th>Part / colour</th><th>Qty</th></tr></thead><tbody>{rows.map(row=><tr key={`${row.partId}:${row.color}`}><td><div className="part-identity">{thumbnails[`${row.partId}:${row.color}`]&&<img src={thumbnails[`${row.partId}:${row.color}`]} alt={`Part ${row.partId}, colour ${row.color}`} width="72" height="72"/>}<span><strong>{row.partId}</strong><small>{colorNames[row.color]||`Colour ${row.color}`}</small></span></div></td><td>×{row.quantity}</td></tr>)}</tbody></table>:<p className="empty-pieces">No new pieces. Use the subassembly you have already built.</p>}
          <details className="physical-pieces"><summary>Active {releaseAlpha?'model components':'physical pieces'} ({step.active_instance_ids.length})</summary><ol>{step.active_instance_ids.map(id=><li key={id}>{id}</li>)}</ol></details>
          {exploration&&<ExplorationFindings diagnostics={exploration} step={step} onNavigate={id=>{const target=scene.steps.findIndex(s=>s.step_id===id);if(target>=0)change(target);}}/>}
          {index===scene.steps.length-1&&<p className="end-note">End of this revision · {exploration?`${exploration.processed_panels} instructions processed, ${exploration.reconstructed_panels} reconstructed. Remaining findings are retained for the next improvement pass.`:releaseAlpha?'Assembly details remain unverified. See the reported coverage in reconstruction details.':selectedSourceCovered ? 'All selected source pages are covered. Assembly details remain unverified.' : guide.expected_main_steps == null ? 'Full booklet coverage has not been verified.' : mainSteps===guide.expected_main_steps?'All expected main-step numbers are represented. Review status still applies.':'This is a partial reconstruction; remaining instructions require review.'}</p>}
        </aside>
      </div>
      <section id="panel-3D" role={phone?'tabpanel':'region'} aria-labelledby={phone?'tab-3D':undefined} className="model-pane" aria-label="Interactive 3D assembly"><div className="model-caption"><span><IconCube size={23} aria-hidden="true"/>{step.action==='build_subassembly'?'Build detached subassembly':step.action==='attach_subassembly'?'Attach the same subassembly':'3D assembly'}</span><span className="active-legend">{assemblyOverview?'Assembly overview':'Active pieces outlined'}</span></div>
        {chunkError?<div role="alert" className="viewport-message error"><p>{chunkError}</p><button onClick={()=>setChunkRetry(n=>n+1)}>Retry instruction</button></div>:!snapshotReady?<p role="status" className="viewport-message">Loading this instruction…</p>:<AssemblyViewport scene={scene} step={step} previous={scene.steps[index-1]} replayToken={replay} command={command} onThumbnails={setThumbnails} onColorNames={setColorNames} fullBuild={playback!=='idle'} paused={playback==='paused'} onAnimationComplete={()=>setAnimationDone(true)} onReadyChange={setReady}/>}
        <div className="camera-controls" role="group" aria-label="Camera controls"><div className="camera-pair"><button onClick={()=>camera('left')} aria-label="Rotate left" title="Rotate left"><IconRotate size={21}/></button><button onClick={()=>camera('right')} aria-label="Rotate right" title="Rotate right"><IconRotateClockwise size={21}/></button><span>Rotate</span></div><button onClick={()=>camera('in')} aria-label="Zoom in" title="Zoom in"><IconPlus size={23}/><span>Zoom in</span></button><button onClick={()=>camera('out')} aria-label="Zoom out" title="Zoom out"><IconMinus size={23}/><span>Zoom out</span></button><button onClick={()=>camera('reset')} aria-label="Reset view" title="Reset view"><IconFocus2 size={23}/><span>Reset view</span></button><div className="camera-pair"><button onClick={()=>camera('pan-left')} aria-label="Pan left" title="Pan left"><IconChevronLeft size={21}/></button><button onClick={()=>camera('pan-right')} aria-label="Pan right" title="Pan right"><IconChevronRight size={21}/></button><span><IconArrowsMoveHorizontal size={14}/> Pan</span></div></div>
        <p className="gesture-hint"><span className="desktop-hint">Drag to rotate · Scroll to zoom · Right-drag to pan</span><span className="touch-hint">Drag to rotate · Pinch to zoom</span></p>
      </section>
      {!publicMode&&review&&<dialog ref={reviewDialog} className="review-drawer" aria-label="Review workspace" onCancel={event=>{event.preventDefault();setReview(false);}}><div className="review-drawer-heading"><h2>Reconstruction review</h2><button className="icon-button" aria-label="Dismiss review" onClick={()=>setReview(false)}><IconX size={20}/></button></div><ReviewPanel scene={scene} step={step} onScene={onScene} onNavigate={stepId=>{const next=scene.steps.findIndex(s=>s.step_id===stepId);if(next>=0){change(next);setTab('3D');if(overlayReview)setReview(false);}}}/></dialog>}
    </div>
    <nav className="step-navigation" aria-label="Instruction navigation">
      <button className="secondary previous-button" disabled={index===0} onClick={()=>change(index-1)}><IconChevronLeft size={20} aria-hidden="true"/><span>Previous</span></button>
      <div className="build-playback" role="region" aria-label="Full build playback">
        {playback==='idle'?<button className="secondary" disabled={!ready||!snapshotReady||Boolean(chunkError)} onClick={startBuild}><IconPlayerPlay size={19} aria-hidden="true"/><span>Play full build</span></button>:<><button className="secondary" disabled={playback==='paused'&&Boolean(chunkError)} onClick={()=>setPlayback(state=>state==='playing'?'paused':'playing')}>{playback==='playing'?<IconPlayerPause size={18} aria-hidden="true"/>:<IconPlayerPlay size={18} aria-hidden="true"/>}<span>{playback==='playing'?'Pause build':'Resume build'}</span></button><button className="icon-button" aria-label="Stop build" title="Stop build" onClick={()=>{setPlayback('idle');setBuildFinished(false);}}><IconPlayerStop size={18}/></button></>}
        <span className="sr-only" role="status">{playback!=='idle'&&chunkError?'Playback paused · retry the unavailable instruction.':playback==='playing'&&(!ready||!snapshotReady)?`Waiting for instruction ${index+1} to load.`:playback==='playing'?`Playing slowly · instruction ${index+1} of ${scene.steps.length}`:playback==='paused'?`Paused · instruction ${index+1} of ${scene.steps.length}`:buildFinished?'Playback complete · all instructions shown':`Watch all ${scene.steps.length} instructions, from the beginning.`}</span>
      </div>
      <div className="instruction-progress"><div className="step-timeline" aria-label="Main steps">{mainEntries.map(entry=><button key={groupKey(entry)} className={groupKey(entry)===groupKey(step)?'current':''} aria-current={groupKey(entry)===groupKey(step)?'step':undefined} aria-label={`Go to main step ${entry.main_step_number}${entry.section_id?` in ${entry.section_id}`:''}`} onClick={()=>change(scene.steps.findIndex(s=>s.step_id===entry.step_id))}>{entry.printed_step_number===null?'✓':entry.main_step_number}</button>)}</div><div className="seek-row"><button className="replay" disabled={!ready||!snapshotReady||Boolean(chunkError)} onClick={replayStep}><IconRotateClockwise size={16} aria-hidden="true"/>Replay</button><label htmlFor="instruction-seek" className="sr-only">Jump to instruction</label><select id="instruction-seek" value={index} onChange={e=>change(Number(e.target.value))}>{scene.steps.map((s,i)=><option key={s.step_id} value={i}>{i+1}. {s.section_id?`${s.section_id} · `:''}{stepLabel(s)}{s.substep_label?` · ${s.substep_label}`:''}</option>)}</select><span className="sr-only" aria-live="polite">Instruction {index+1} of {scene.steps.length}</span></div></div>
      <button className="next-button" disabled={index===scene.steps.length-1} onClick={()=>change(index+1)}><span>Next</span><IconChevronRight size={20} aria-hidden="true"/></button>
    </nav>
  </section>;
}
