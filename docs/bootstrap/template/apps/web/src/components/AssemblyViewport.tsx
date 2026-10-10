import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { LDrawLoader } from 'three/addons/loaders/LDrawLoader.js';
import type { SceneManifest, StepSnapshot } from '../contracts';

// Real .dat geometry only. No generic brick fallback and no completed-model loading.
export default function AssemblyViewport({ scene: manifest, step, resetToken }: {
  scene: SceneManifest; step: StepSnapshot; resetToken: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const stepRef = useRef(step);
  const applyStep = useRef<(() => void) | null>(null);
  const reset = useRef<(() => void) | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => { stepRef.current = step; applyStep.current?.(); }, [step]);
  useEffect(() => { reset.current?.(); }, [resetToken]);
  useEffect(() => {
    if (!host.current) return;
    let cancelled = false;
    let frame = 0;
    setError(''); setLoading(true);
    const element = host.current;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false }); }
    catch { setError('WebGL is unavailable. Open the original guide or try a supported browser.'); setLoading(false); return; }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    element.appendChild(renderer.domElement);
    const world = new THREE.Scene(); world.background = new THREE.Color('#f1f5fa');
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 20000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    world.add(new THREE.HemisphereLight(0xffffff, 0x64748b, 2));
    const light = new THREE.DirectionalLight(0xffffff, 2.5); light.position.set(400, 800, 500); world.add(light);
    const assembly = new THREE.Group(); world.add(assembly);
    const groups = new Map<string, THREE.Group>();
    const cache = new Map<string, Promise<THREE.Group>>();
    const loader = new LDrawLoader();
    loader.setPartsLibraryPath('/assets-local/ldraw/');
    const geometries = new Set<THREE.BufferGeometry>();
    const materials = new Set<THREE.Material>();
    const register = (object: THREE.Object3D) => object.traverse(child => {
      if (child instanceof THREE.Mesh || child instanceof THREE.LineSegments) {
        geometries.add(child.geometry);
        (Array.isArray(child.material) ? child.material : [child.material]).forEach(m => materials.add(m));
      }
    });
    applyStep.current = () => {
      const current = stepRef.current;
      const visible = new Set(current.visible_instance_ids);
      for (const [id, group] of groups) {
        group.visible = visible.has(id);
        const pose = current.poses[id];
        if (pose) { group.position.fromArray(pose.position_ldu); group.quaternion.fromArray(pose.quaternion_xyzw); }
      }
    };
    reset.current = () => {
      const box = new THREE.Box3().setFromObject(assembly);
      const center = box.isEmpty() ? new THREE.Vector3() : box.getCenter(new THREE.Vector3());
      const radius = box.isEmpty() ? 100 : Math.max(40, box.getSize(new THREE.Vector3()).length());
      camera.position.copy(center).add(new THREE.Vector3(radius, radius * 0.8, radius));
      controls.target.copy(center); controls.update();
    };
    const resize = new ResizeObserver(() => {
      const { width, height } = element.getBoundingClientRect();
      camera.aspect = Math.max(width, 1) / Math.max(height, 1); camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    });
    resize.observe(element);
    const draw = () => { controls.update(); renderer.render(world, camera); frame = requestAnimationFrame(draw); };
    reset.current(); draw();
    (async () => {
      await loader.preloadMaterials('/assets-local/ldraw/LDConfig.ldr');
      for (const part of manifest.instances) {
        if (cancelled) return;
        const key = `${part.geometry_ref}:${part.color_code}`;
        if (!cache.has(key)) {
          // One generated reference to an individual part, not a retrieved completed assembly.
          const reference = `0 Guide2Build individual part\n1 ${part.color_code} 0 0 0 1 0 0 0 1 0 0 0 1 ${part.geometry_ref}\n`;
          cache.set(key, new Promise<THREE.Group>((resolve, reject) => loader.parse(reference, resolve, reject)));
        }
        const original = await cache.get(key)!;
        register(original);
        if (cancelled) { geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose()); return; }
        const instance = new THREE.Group();
        const geometry = original.clone(true);
        // Convert raw LDraw (-Y up) into canonical Y-up with a proper rotation, once only.
        geometry.rotation.x = Math.PI;
        instance.add(geometry); assembly.add(instance); groups.set(part.instance_id, instance);
      }
      applyStep.current?.(); reset.current?.();
      if (!cancelled) setLoading(false);
    })().catch(e => {
      if (!cancelled) { setError(`Could not load the required part geometry: ${e instanceof Error ? e.message : 'asset error'}`); setLoading(false); }
    });
    return () => {
      cancelled = true; cancelAnimationFrame(frame); resize.disconnect(); controls.dispose();
      geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose()); renderer.dispose();
      renderer.domElement.remove(); applyStep.current = null; reset.current = null;
    };
  }, [manifest]);
  return <div className="viewport-wrap"><div className="viewport" ref={host} />
    {loading && <p role="status" className="viewport-message">Loading individual part geometry…</p>}
    {error && <p role="alert" className="viewport-message error">{error}</p>}
  </div>;
}
