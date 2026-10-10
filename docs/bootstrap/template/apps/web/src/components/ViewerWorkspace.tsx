import { useEffect, useState } from 'react';
import type { Guide, SceneManifest } from '../contracts';
import { readProgress, saveProgress } from '../state';
import AssemblyViewport from './AssemblyViewport';

export default function ViewerWorkspace({ scene, guide, onClose }: {
  scene: SceneManifest; guide: Guide; onClose: () => void;
}) {
  const [index, setIndex] = useState(() => readProgress(scene));
  const [resetToken, setResetToken] = useState(0);
  const step = scene.steps[index];
  useEffect(() => { saveProgress(scene, index); }, [scene, index]);
  return <section className="workspace">
    <div className="workspace-title"><div><button className="secondary" onClick={onClose}>Back to set</button>
      <h1>{scene.set_number} · {guide.label}</h1></div><span className="review-status">{scene.status.replaceAll('_', ' ')}</span></div>
    <div className="workspace-grid">
      <aside className="source-pane"><h2>Original guide</h2>
        <p>PDF page {step.source.page_index + 1} · Main step {step.main_step_number}</p>
        <iframe title="Original LEGO instruction booklet" src={`${guide.pdf_url}#page=${step.source.page_index + 1}`} />
        <p className="muted">Starter reference view. A locally rendered, synchronised panel replaces this iframe in milestone M3.</p>
        <a href={`${guide.pdf_url}#page=${step.source.page_index + 1}`} target="_blank" rel="noreferrer">Open source page</a>
      </aside>
      <section className="model-pane" aria-label="Interactive 3D assembly">
        <AssemblyViewport scene={scene} step={step} resetToken={resetToken} />
        <button className="secondary" onClick={() => setResetToken(x => x + 1)}>Reset view</button>
        <p className="muted">Drag to rotate · Scroll to zoom · Right-drag to pan</p>
      </section>
      <aside className="step-pane"><h2>Step {step.main_step_number}{step.substep_label ? ` · ${step.substep_label}` : ''}</h2>
        <p>{step.instruction}</p><h3>New pieces</h3>
        {step.introduced_instance_ids.length ? <ul>{step.introduced_instance_ids.map(id => {
          const part = scene.instances.find(p => p.instance_id === id)!;
          return <li key={id}>{part.part_id} · colour {part.color_code}</li>;
        })}</ul> : <p>No new pieces. Use the subassembly you have already built.</p>}
        <p className="muted">Geometry: {scene.geometry_check} · Connections: {scene.connector_check}<br />
          Physical build: {scene.physical_build_check}</p>
      </aside>
    </div>
    <nav className="step-navigation" aria-label="Instruction navigation">
      <button className="secondary" disabled={index === 0} onClick={() => setIndex(i => i - 1)}>Previous</button>
      <span aria-live="polite">Instruction {index + 1} of {scene.steps.length}</span>
      <button disabled={index === scene.steps.length - 1} onClick={() => setIndex(i => i + 1)}>Next</button>
    </nav>
  </section>;
}
