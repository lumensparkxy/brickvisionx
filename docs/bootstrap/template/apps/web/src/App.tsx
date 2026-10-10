import { lazy, Suspense, useState, type FormEvent } from 'react';
import { request } from './api';
import type { Guide, SceneManifest, SetInfo } from './contracts';
const ViewerWorkspace = lazy(() => import('./components/ViewerWorkspace'));

export default function App() {
  const [setNumber, setSetNumber] = useState('30669');
  const [setInfo, setSetInfo] = useState<SetInfo | null>(null);
  const [guide, setGuide] = useState<Guide | null>(null);
  const [scene, setScene] = useState<SceneManifest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function findSet(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setScene(null); setGuide(null); setSetInfo(null);
    try { setSetInfo(await request<SetInfo>(`/sets/${encodeURIComponent(setNumber.trim())}`)); }
    catch (e) { setError(e instanceof Error ? e.message : 'The set could not be found.'); }
    finally { setBusy(false); }
  }
  async function openGuide(selected: Guide) {
    if (!setInfo) return;
    setGuide(selected); setBusy(true); setError('');
    try { setScene(await request<SceneManifest>(`/sets/${setInfo.set_number}/guides/${selected.guide_id}/scene`)); }
    catch (e) { setError(e instanceof Error ? e.message : 'The tutorial could not be opened.'); }
    finally { setBusy(false); }
  }
  return <>
    <header className="app-header"><a href="/" className="brand">Guide2Build <span>3D</span></a>
      <span className="header-note">Existing guides. A clearer way to build.</span></header>
    <main>
      {scene && guide ? <Suspense fallback={<p role="status">Loading the 3D viewer…</p>}>
        <ViewerWorkspace scene={scene} guide={guide} onClose={() => setScene(null)} />
      </Suspense> : <section className="lookup">
        <h1>Which set are you building?</h1>
        <p className="intro">Enter the set number. Your original instructions stay beside the 3D tutorial.</p>
        <form onSubmit={findSet}>
          <label htmlFor="set-number">Set number</label>
          <div className="search-row"><input id="set-number" inputMode="numeric" pattern="[0-9]{4,7}"
            required value={setNumber} onChange={e => setSetNumber(e.target.value)} aria-describedby="supported" />
            <button type="submit" disabled={busy}>{busy ? 'Please wait…' : 'Find my set'}</button></div>
          <p id="supported" className="muted">Initial source: 30669 · Alternate booklet 02</p>
        </form>
        {setInfo && <section className="set-result" aria-label="Set details">
          <h2>{setInfo.set_number} · {setInfo.name}</h2>
          <p>Select the instruction booklet.</p>
          {setInfo.guides.map(item => <div className="guide-row" key={item.guide_id}>
            <div><strong>{item.label}</strong><p className="muted">Source target: {item.expected_main_steps} main steps</p></div>
            <button disabled={busy} onClick={() => openGuide(item)}>Open tutorial</button>
          </div>)}
          <a href={setInfo.official_page} target="_blank" rel="noreferrer">View official instructions</a>
        </section>}
        {error && <div role="alert" className="notice"><h2>Not ready yet</h2><p>{error}</p>
          {guide && <a href={guide.pdf_url} target="_blank" rel="noreferrer">Open the original booklet</a>}</div>}
        <p className="scaffold-note">Development starter: no completed model is bundled. The reconstruction pipeline is the next implementation milestone.</p>
      </section>}
    </main>
    <footer>Independent prototype. Not affiliated with or endorsed by the LEGO Group.</footer>
  </>;
}
