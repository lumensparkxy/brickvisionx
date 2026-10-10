import { lazy, Suspense, useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, parseEnginePreviews, parseGuideStatus, parseJob, post, previewCoverageText, previewForGuide, request, withPreviewAvailability, type ConversionJob, type EnginePreview } from './api';
import { parseScene, parseSet } from './validation';
import { parseConfig, ReleaseLoader, REQUEST_RECORDED, type PortalConfig } from './releases';
import { readProgress } from './state';
import type { Guide, SceneManifest, SetInfo } from './contracts';
import LandingPage from './components/LandingPage';
import BookletDialog from './components/BookletDialog';
const ViewerWorkspace = lazy(() => import('./components/ViewerWorkspace'));
const terminal = new Set(['ready', 'needs_review', 'failed', 'cancelled']);
export default function App() {
  const [config,setConfig] = useState<PortalConfig | null>(null);
  const [configError,setConfigError] = useState('');
  const [configAttempt,setConfigAttempt] = useState(0);
  const [release,setRelease] = useState<ReleaseLoader | null>(null);
  const [requested,setRequested] = useState(false);
  const publicMode = config?.mode !== 'local';
  const previewMode = config?.mode === 'preview';
  const [enginePreviews,setEnginePreviews] = useState<EnginePreview[]>([]);
  const [viewerPreview,setViewerPreview] = useState<EnginePreview | null>(null);
  useEffect(()=>{
    if(!previewMode||!config?.source_images)return;
    let stopped=false;let timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{try{const values=parseEnginePreviews(await request('/engine-preview'));if(!stopped){setEnginePreviews(values);setSetInfo(info=>info?withPreviewAvailability(info,values):info);}}catch{/* Isolated render transport has no persistent engine job. */}finally{if(!stopped)timer=setTimeout(poll,3000);}};
    void poll();return()=>{stopped=true;clearTimeout(timer);};
  },[previewMode,config?.source_images]);
  useEffect(()=>{let stopped=false;setConfigError('');request('/config').then(parseConfig).then(value=>{if(!stopped)setConfig(value);}).catch(e=>{if(!stopped)setConfigError(e instanceof Error?e.message:'Website settings unavailable.');});return()=>{stopped=true;};},[configAttempt]);
  const [setNumber, setSetNumber] = useState('30669');
  const [bookletOpen,setBookletOpen] = useState(false);
  const [setInfo, setSetInfo] = useState<SetInfo | null>(null);
  const [guide, setGuide] = useState<Guide | null>(null);
  const [scene, setScene] = useState<SceneManifest | null>(null);
  const [job, setJob] = useState<ConversionJob | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [notice, setNotice] = useState(''); const operation = useRef(0); const conversionKeys = useRef<Record<string,string>>({});
  const returnToLookup = useRef(false);
  const focusPreparation = useRef(false);
  const resultHeading = useRef<HTMLHeadingElement>(null); const errorHeading = useRef<HTMLHeadingElement>(null); const preparationHeading = useRef<HTMLHeadingElement>(null); const focusResult = useRef(false);
  const base = setInfo && guide ? `/sets/${setInfo.set_number}/guides/${guide.guide_id}` : '';
  useEffect(()=>{if(!bookletOpen&&!busy&&returnToLookup.current){document.getElementById('find-set')?.focus();returnToLookup.current=false;}},[bookletOpen,busy]);
  useEffect(()=>{
    if(scene){window.scrollTo(0,0);focusResult.current=false;return;}
    if(!busy&&focusResult.current){const target=error?errorHeading.current:resultHeading.current;if(target){target.focus();focusResult.current=false;}}
  },[scene,busy,setInfo,error]);
  useEffect(()=>{
    if (!busy && guide && focusPreparation.current) {
      preparationHeading.current?.focus(); preparationHeading.current?.scrollIntoView({block:'start'});
      focusPreparation.current=false;
    }
  },[busy,guide]);
  useEffect(() => {
    if (!job || terminal.has(job.state)) return;
    let stopped = false; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { const result = parseJob(await request(`/jobs/${job.job_id}`)); if (!stopped) { setJob(result); if (!terminal.has(result.state)) timer = setTimeout(poll, 1200); } }
      catch (e) { if (!stopped) { setError(e instanceof Error ? e.message : 'Processing status unavailable.'); timer = setTimeout(poll, 4000); } }
    };
    timer = setTimeout(poll, 500); return () => { stopped = true; clearTimeout(timer); };
  }, [job?.job_id, job?.state]);
  async function findSet(event: FormEvent) { event.preventDefault(); await lookupSet(setNumber); }
  async function lookupSet(value:string, tryExample=false) {
    if(!config)return;
    const op = ++operation.current; focusResult.current=true;setRelease(null);setRequested(false);
    setBookletOpen(false); setError(''); setNotice(''); setScene(null); setGuide(null); setSetInfo(null); setJob(null); setViewerPreview(null);
    if (!/^\d{4,7}$/.test(value.trim())) { setError('Enter a set number containing 4–7 digits.'); return; }
    setBusy(true);
    try {
      const result = parseSet(await request(`/sets/${encodeURIComponent(value.trim())}`),publicMode);
      if (op === operation.current) {
        setSetInfo(result); setBookletOpen(true);
        if(publicMode&&!result.guides.some(item=>item.tutorial_available))await requestSet(result.set_number,op);
        if(tryExample&&!publicMode){const example=result.guides.find(item=>item.guide_id==='alt-02');if(!example)throw new Error('The supported alternate booklet is not available. Choose an available booklet below.');await openGuide(example,result);}
      }
    }
    catch (e) { if(op===operation.current)setError(e instanceof Error ? e.message : 'The set could not be found.'); }
    finally { if(op===operation.current)setBusy(false); }
  }
  async function requestSet(number:string,op=operation.current) {
    if(!config?.requests_enabled) return;
    setError('');
    try {
      const result=await post<{set_number:string;status:string}>('/requests',{set_number:number});
      if(result.set_number!==number||result.status!=='requested')throw new Error('Your request could not be confirmed. Please try again.');
      if(op===operation.current){setRequested(true);setNotice(REQUEST_RECORDED);}
    } catch(e){if(op===operation.current)setError(e instanceof Error?e.message:'Your request could not be saved. Please try again.');}
  }
  async function loadRevision(revision: string) { const op=operation.current;try{const candidate=parseScene(await request(`/reconstructions/${encodeURIComponent(revision)}/scene`));if(op===operation.current){setScene(candidate);setNotice('Loaded a cached reconstruction revision.');}}catch(e){if(op===operation.current)throw e;} }
  async function openPreparation(selected: Guide) {
    if (!setInfo) return;
    const op = operation.current;
    focusPreparation.current=true;
    setGuide(selected); setJob(null); setError(''); setNotice(''); setBusy(true);
    try {
      const status = parseGuideStatus(await request(`/sets/${setInfo.set_number}/guides/${selected.guide_id}/status`));
      if (op !== operation.current) return;
      if (status.job) setJob(parseJob(status.job));
      else await prepare('assisted', selected);
    } catch (e) { if(op === operation.current) setError(e instanceof Error ? e.message : 'Booklet preparation could not be opened.'); }
    finally { if(op === operation.current) setBusy(false); }
  }
  async function openGuide(selected: Guide, selectedSet: SetInfo | null = setInfo) {
    if (!selectedSet) return; const op=operation.current; focusResult.current=true; setGuide(selected); setBusy(true); setError(''); setNotice(''); setJob(null);
    const path = `/sets/${selectedSet.set_number}/guides/${selected.guide_id}`;
    try {
      if(publicMode){
        const loader=new ReleaseLoader(await request(`${path}/release`));
        if(loader.release.scene.set_number!==selectedSet.set_number||loader.release.scene.guide_id!==selected.guide_id)throw new Error('The published tutorial identity does not match this booklet.');
        if(!previewMode&&selected.release_kind!==loader.release.release_kind)throw new Error('The published model status does not match this booklet. Please find the set again.');
        const candidate=await loader.window(readProgress(loader.release.scene));
        let metadata=previewForGuide(enginePreviews,candidate.set_number,candidate.guide_id,candidate.revision)??null;
        if(previewMode){try{const values=parseEnginePreviews(await request(`/engine-preview?set_number=${encodeURIComponent(candidate.set_number)}&guide_id=${encodeURIComponent(candidate.guide_id)}`));metadata=previewForGuide(values,candidate.set_number,candidate.guide_id,candidate.revision)??metadata;}catch{/* The immutable scene can still open if job polling is temporarily unavailable. */}}
        if(op===operation.current){setRelease(loader);setScene(candidate);setViewerPreview(metadata);}
        return;
      }
      const candidate=parseScene(await request(`${path}/scene`));if(op===operation.current){setScene(candidate);setNotice('Loaded a cached reconstruction revision.');} }
    catch (e) {
      if(op!==operation.current)return;
      setError(e instanceof Error ? e.message : 'The tutorial could not be opened.');
      if (!publicMode && e instanceof ApiError && e.status === 409) {
        try { const status = parseGuideStatus(await request(`${path}/status`)); if(op!==operation.current)return; if (status.job) setJob(parseJob(status.job)); if (status.latest_candidate_revision) { await loadRevision(status.latest_candidate_revision); if(op===operation.current)setError(''); } else if (!selected.tutorial_available) { setError(''); setNotice('No 3D reconstruction is available for this booklet yet.'); } }
        catch { /* Original not-ready error remains actionable; preparation is available below. */ }
      }
    } finally { if(op===operation.current)setBusy(false); }
  }
  async function prepare(mode: 'assisted' | 'automated', selected: Guide | null = guide) {
    if (!setInfo || !selected) return; const op=operation.current; setBusy(true); setError('');
    const identity = `${setInfo.set_number}:${selected.guide_id}:${mode}`;
    const idempotencyKey = conversionKeys.current[identity] ??= crypto.randomUUID();
    try { const result=parseJob(await post('/conversions', { set_number: setInfo.set_number, guide_id: selected.guide_id, mode }, idempotencyKey));delete conversionKeys.current[identity];if(op===operation.current){setJob(result);setNotice('Preparation is recorded locally. You can reopen this booklet to resume.');} }
    catch (e) { if(op===operation.current)setError(e instanceof Error ? e.message : 'Preparation failed.'); } finally { if(op===operation.current)setBusy(false); }
  }
  async function jobAction(action: 'cancel' | 'retry') {
    if (!job) return; const op=operation.current; setBusy(true); setError('');
    try { const result=parseJob(await post(`/jobs/${job.job_id}/${action}`));if(op===operation.current)setJob(result); }
    catch (e) { if(op===operation.current)setError(e instanceof Error ? e.message : 'Job action failed.'); } finally { if(op===operation.current)setBusy(false); }
  }
  const closeBooklet=()=>{++operation.current;returnToLookup.current=true;setBusy(false);setBookletOpen(false);setJob(null);setError('');focusResult.current=false;};
  const enginePreview=scene?previewForGuide(enginePreviews,scene.set_number,scene.guide_id,scene.revision)
    ?? (viewerPreview?.revision===scene.revision&&viewerPreview.set_number===scene.set_number&&viewerPreview.guide_id===scene.guide_id?viewerPreview:null)
    :setInfo&&guide?previewForGuide(enginePreviews,setInfo.set_number,guide.guide_id):null;
  const visiblePreviews=setInfo?enginePreviews.filter(value=>value.set_number===setInfo.set_number):enginePreviews.length===1?enginePreviews:[];
  const alphaAvailable=setInfo?.guides.some(item=>item.release_kind==='unverified_alpha')??false;
  const reviewedAvailable=setInfo?.guides.some(item=>item.tutorial_available&&item.release_kind!=='unverified_alpha')??false;
  const previewNotice=previewMode&&setInfo&&<aside className="notice" aria-label="Engine candidate preview"><strong>{enginePreviews.some(value=>value.execution_policy==='explore')?'Exploration candidates · provisional':enginePreviews.some(value=>value.generation_mode==='alpha_fast'||value.image_quality?.profile==='alpha')?'Alpha samples · unverified':'Local engine candidate preview · unpublished'}</strong>{visiblePreviews.map(value=><div key={value.job_id}><p><strong>{value.set_number} / {value.guide_id}</strong> · {value.state} · Stage: {value.stage}</p><p>{previewCoverageText(value)}</p>{value.generation_mode==='alpha_fast'?<p>Approximate alpha model. Colours and placements are unverified; visible gaps or overlaps may remain. Camera alignment has not been checked.</p>:value.image_quality?.profile==='alpha'&&<p>Relaxed image alignment: up to {value.image_quality.max_rms_pixels} px RMS. {value.image_quality.relaxed_steps.length} instructions exceed the strict alignment limit.</p>}{value.uncertainty_notes&&value.uncertainty_notes.length>0&&<ul>{value.uncertainty_notes.map((note,i)=><li key={i}>{note}</li>)}</ul>}{value.repair&&<p>Instruction {value.repair.panel} · Placement attempt {value.repair.attempt} of {value.repair.limit}. Accepted instructions are preserved during repair.</p>}{value.error&&<p role="status">{value.error.code}: {value.error.message}</p>}{value.candidate_message&&<p>{value.candidate_message}</p>}</div>)}<p>Human acceptance and physical testing have not been recorded.</p></aside>;
  return <>{scene && guide ? <main className="studio-main"><Suspense fallback={<p role="status">Loading the 3D viewer…</p>}>
      <ViewerWorkspace key={scene.revision} publicMode={publicMode} releaseAlpha={release?.release.alpha} previewMode={previewMode} previewExperiment={enginePreview?.experiment_revision??undefined} previewJobId={enginePreview?.job_id} previewQuality={enginePreview?.image_quality} previewGenerationMode={enginePreview?.generation_mode} previewArtifactKind={enginePreview?.artifact_kind} exploration={enginePreview?.exploration} previewUncertaintyNotes={enginePreview?.uncertainty_notes} previewCoverage={enginePreview?previewCoverageText(enginePreview):undefined} previewSourceCoverage={typeof enginePreview?.source_coverage==='string'?enginePreview.source_coverage:undefined} sourceImages={config?.source_images??false} releaseLoader={release??undefined} scene={scene} guide={guide} onScene={setScene} onClose={() => {focusResult.current=true;setBookletOpen(true);setScene(null);}} />
    </Suspense></main> : <LandingPage setNumber={setNumber} onSetNumber={setSetNumber} onFind={findSet} onTry={()=>{setSetNumber('30669');void lookupSet('30669',true);}} busy={busy||!config} publicMode={publicMode} previewMode={previewMode}>
      {configError&&<div role="alert" className="notice"><p>{configError}</p><button onClick={()=>setConfigAttempt(n=>n+1)}>Retry website connection</button></div>}
      {!setInfo&&error&&<div className="landing-workflow"><div role="alert" className="notice"><h2 ref={errorHeading} tabIndex={-1}>Set lookup</h2><p>{error}</p></div></div>}
      {setInfo&&bookletOpen&&<BookletDialog onClose={closeBooklet}>
      {setInfo && <section className="set-result" aria-label="Set details"><div className="booklet-heading"><span className="eyebrow">LET’S BUILD SOMETHING</span><h2 id="booklet-title" ref={resultHeading} tabIndex={-1}>{setInfo.set_number}{setInfo.name?` · ${setInfo.name}`:''}</h2><p>{previewMode?(visiblePreviews.some(value=>value.execution_policy==='explore')?'Choose a local exploration candidate to inspect in 3D.':'Choose a local alpha sample to inspect in 3D.'):publicMode?(alphaAvailable?(reviewedAvailable?'Choose a tutorial or unverified alpha model.':'Choose an alpha model to explore in 3D. Accuracy is unverified.'):reviewedAvailable?'Choose a ready tutorial and let’s build!':'We’re making room for more builds.'):'Official source found. Choose your booklet to get started.'}</p></div><div className="booklet-options">
        {setInfo.guides.map(item => {const metadata=previewForGuide(enginePreviews,setInfo.set_number,item.guide_id);const releasedAlpha=item.release_kind==='unverified_alpha';return <div className="guide-row" key={item.guide_id}><div><span className="booklet-tag">{releasedAlpha?'ALPHA MODEL · UNVERIFIED':item.tutorial_available ? (previewMode?'ENGINE CANDIDATE AVAILABLE':publicMode?'READY TO BUILD':'3D CANDIDATE AVAILABLE') : (previewMode?'NO ENGINE CANDIDATE YET':publicMode?'NOT READY YET':'OFFICIAL SOURCE · NO 3D TUTORIAL YET')}</span><strong>{item.label}</strong><p className="muted">{item.expected_main_steps == null ? 'Official booklet' : `Booklet: ${item.expected_main_steps} main steps`}</p>{previewMode&&metadata&&<p className="muted">{previewCoverageText(metadata)}{metadata.generation_mode==='alpha_fast'&&<><br/>Alpha sample · unverified</>}{metadata.error?.message&&<><br/>{metadata.error.message}</>}</p>}</div>{(!publicMode||item.tutorial_available)&&<button disabled={busy} onClick={() => item.tutorial_available ? openGuide(item) : openPreparation(item)}>{previewMode&&metadata?.execution_policy==='explore'&&item.tutorial_available?'Open candidate':releasedAlpha?'Open alpha model':item.tutorial_available ? 'Open tutorial' : 'Prepare booklet'}</button>}</div>;})}
        {setInfo.official_page&&<a href={setInfo.official_page} target="_blank" rel="noreferrer">View official instructions ↗</a>}</div></section>}
      {previewNotice&&<details className="booklet-sample-details"><summary>Sample accuracy and review details</summary>{previewNotice}</details>}
      {publicMode&&!previewMode&&alphaAvailable&&<details className="booklet-sample-details"><summary>Alpha accuracy and review details</summary><p>Alpha models are approximate reconstructions from official booklets. Part choices, colours and placements remain unverified.</p><p>Human review: not run · Physical build: not run</p><p>Open a model to see its source, revision, reported coverage and uncertainty notes.</p></details>}
      {publicMode&&notice&&<p className="notice" role="status">{notice}</p>}
      {publicMode&&config?.requests_enabled&&!requested&&setInfo.guides.some(item=>!item.tutorial_available)&&<button disabled={busy} onClick={()=>requestSet(setInfo.set_number)}>Request this set</button>}
      {publicMode&&config?.requests_enabled&&!requested&&setInfo.guides.length===0&&<button disabled={busy} onClick={()=>requestSet(setInfo.set_number)}>Try saving my request again</button>}
      {error && <div role="alert" className="notice"><h2 ref={errorHeading} tabIndex={-1}>{publicMode?'Let’s try again':guide ? 'Preparation needs attention' : 'Set lookup'}</h2><p>{error}</p></div>}
      {!publicMode&&guide && <section className="preparation" aria-label="Booklet preparation"><h2 ref={preparationHeading} tabIndex={-1}>{guide.label}</h2>
        <p>Preparation downloads and renders this official booklet. A 3D tutorial needs a separate reconstruction and review.</p>
        {notice && <p className="muted">{notice}</p>}
        {job && <div className="job-state" role="status"><strong>{job.state === 'needs_review' && !job.output_revision ? 'Booklet prepared' : job.state.replaceAll('_', ' ')}</strong><p>Stage: {job.stage.replaceAll('_', ' ')}</p>
          {job.total_units != null && job.total_units > 0 && <><progress aria-label="Booklet preparation progress" value={job.completed_units} max={job.total_units}/><p>{job.completed_units} of {job.total_units} {job.stage === 'rendering' ? 'pages rendered' : ['validating','needs_review','ready'].includes(job.stage) ? 'pages prepared' : 'units'}</p></>}
          {job.error && !(typeof job.error === 'object' && job.error.code === 'assisted_reference_unavailable') && <p>{typeof job.error === 'string' ? job.error : job.error.message ?? job.error.code}</p>}
          {job.state === 'needs_review' && <p>{job.output_revision ? 'Unresolved part identities and placements require evidence-backed review.' : 'The official pages are prepared. No 3D reconstruction is available for this booklet yet.'}</p>}
          <div className="button-row">{!terminal.has(job.state) && <button className="secondary" disabled={busy} onClick={() => jobAction('cancel')}>Cancel preparation</button>}
          {['failed','cancelled'].includes(job.state) && <button disabled={busy} onClick={() => jobAction('retry')}>Retry preparation</button>}
          {job.output_revision && <button onClick={() => loadRevision(job.output_revision!).catch(e => setError(e.message))}>Open candidate for review</button>}</div>
        </div>}
        {(!job || ['failed','cancelled'].includes(job.state)) && <div className="button-row"><button disabled={busy} onClick={() => prepare('assisted')}>Prepare official booklet</button><button className="secondary" disabled={busy} onClick={() => prepare('automated')}>Try automatic conversion</button></div>}
        <p><a href={guide.pdf_url} target="_blank" rel="noreferrer">Open the original booklet ↗</a></p>
        {base && <button className="secondary" disabled={busy} onClick={() => openGuide(guide)}>Check for a reconstruction</button>}
      </section>}
      </BookletDialog>}
    </LandingPage>}</>;
}
