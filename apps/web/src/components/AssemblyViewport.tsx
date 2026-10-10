import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { LDrawLoader } from 'three/addons/loaders/LDrawLoader.js';
import { LDrawConditionalLineMaterial } from 'three/addons/materials/LDrawConditionalLineMaterial.js';
import { approachFor, checkedApproach, replayPlan, type ReplayPlan } from '../placement';
import { createSourceCamera, inspectSourceCamera, moveCamera, stopCameraMotion, type CameraAction } from '../camera';
import type { SceneManifest, StepSnapshot } from '../contracts';
import { modelAssetUrl } from '../assets';
// Explicit developer opt-in. No frame sampling or GPU queries run in the normal product path.
interface RenderSample {
  atMs: number; phase: 'viewport' | 'thumbnail'; stepId: string; cpuSubmitMs: number;
  calls: number; triangles: number; lines: number; geometries: number; textures: number;
}
interface RendererAudit {
  identity: { set: string; guide: string; revision: string }; startedAtMs: number; readyAtMs: number | null;
  disposedAtMs: number | null; samples: RenderSample[]; gpuMs: number[]; gpuDiscarded: number;
  hardware: Record<string, unknown>; phases: Record<string, number>; disposedResources: Record<string, number> | null;
}
function rendererAudit(renderer: THREE.WebGLRenderer, manifest: SceneManifest) {
  if (new URLSearchParams(location.search).get('benchmark') !== '1') return null;
  const gl = renderer.getContext() as WebGL2RenderingContext;
  const debug = gl.getExtension('WEBGL_debug_renderer_info');
  const timer = gl.getExtension('EXT_disjoint_timer_query_webgl2') as {TIME_ELAPSED_EXT:number; GPU_DISJOINT_EXT:number} | null;
  const audit: RendererAudit = {
    identity: {set:manifest.set_number,guide:manifest.guide_id,revision:manifest.revision},
    startedAtMs:performance.now(), readyAtMs:null, disposedAtMs:null, samples:[], gpuMs:[], gpuDiscarded:0,
    phases:{}, disposedResources:null,
    hardware:{vendor:gl.getParameter(gl.VENDOR),renderer:gl.getParameter(gl.RENDERER),
      unmaskedVendor:debug ? gl.getParameter(debug.UNMASKED_VENDOR_WEBGL) : null,
      unmaskedRenderer:debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : null,
      version:gl.getParameter(gl.VERSION),maxTextureSize:gl.getParameter(gl.MAX_TEXTURE_SIZE),
      gpuTimerSupported:Boolean(timer),pixelRatio:renderer.getPixelRatio(),
      userAgent:navigator.userAgent,hardwareConcurrency:navigator.hardwareConcurrency,
      limits:'Resource counts are not VRAM bytes. CPU submission excludes GPU completion. Timer queries are asynchronous and sampled every tenth render.'},
  };
  const scope = window as typeof window & {__guide2buildRendererAudits?:RendererAudit[]};
  const audits = scope.__guide2buildRendererAudits ??= []; audits.push(audit); if(audits.length>32)audits.shift();
  const pending:WebGLQuery[]=[]; let renderCount=0;
  const poll = () => {
    if(!timer)return;
    if(gl.getParameter(timer.GPU_DISJOINT_EXT)) {
      audit.gpuDiscarded+=pending.length+audit.gpuMs.length; audit.gpuMs=[];
      for(const query of pending)gl.deleteQuery(query); pending.length=0; return;
    }
    while(pending.length && gl.getQueryParameter(pending[0],gl.QUERY_RESULT_AVAILABLE)) {
      const query=pending.shift()!; audit.gpuMs.push(gl.getQueryParameter(query,gl.QUERY_RESULT)/1e6);gl.deleteQuery(query);
      if(audit.gpuMs.length>2000)audit.gpuMs.shift();
    }
  };
  return {audit,poll,render(world:THREE.Scene,camera:THREE.Camera,phase:RenderSample['phase'],stepId:string) {
    poll(); const query=timer && ++renderCount%10===0 && pending.length<8 ? gl.createQuery() : null;
    if(query)gl.beginQuery(timer!.TIME_ELAPSED_EXT,query);
    const start=performance.now(); renderer.render(world,camera); const end=performance.now();
    if(query){gl.endQuery(timer!.TIME_ELAPSED_EXT);pending.push(query);}
    audit.samples.push({atMs:start,phase,stepId,cpuSubmitMs:end-start,
      calls:renderer.info.render.calls,triangles:renderer.info.render.triangles,lines:renderer.info.render.lines,
      geometries:renderer.info.memory.geometries,textures:renderer.info.memory.textures});
    if(audit.samples.length>15000)audit.samples.shift();
  },dispose() {
    for(const query of pending)gl.deleteQuery(query);pending.length=0;
    audit.disposedAtMs=performance.now();audit.disposedResources={geometries:renderer.info.memory.geometries,textures:renderer.info.memory.textures};
  }};
}
export interface CameraCommand { action: CameraAction | 'up' | 'down' | 'fly' | 'reassemble'; token: number; degrees?: number; }
/** Window event with the stunt phase ('takeoff' | 'dive' | 'impact' | 'settled'), for sound effects. */
export const STUNT_EVENT = 'brickvision:stunt';
export default function AssemblyViewport({ scene: manifest, step, previous, replayToken, command, onThumbnails, onColorNames, fullBuild, paused, onAnimationComplete, onReadyChange }: {
  scene: SceneManifest; step: StepSnapshot; previous?: StepSnapshot; replayToken: number; command: CameraCommand; onThumbnails: (images: Record<string,string>) => void;
  onColorNames?: (names: Record<string,string>) => void;
  fullBuild: boolean; paused: boolean; onAnimationComplete: () => void; onReadyChange: (ready:boolean) => void;
}) {
  const manifestRef=useRef(manifest);manifestRef.current=manifest;
  const geometryBase=manifest.geometry_base_url??'/assets-local/ldraw/';
  const frameKey=(snapshot:StepSnapshot)=>`${snapshot.section_id??''}:${snapshot.printed_step_number===null?snapshot.step_id:snapshot.main_step_number}`;
  const host = useRef<HTMLDivElement>(null); const stepRef = useRef(step);
  const applyStep = useRef<((animate?: boolean) => void) | null>(null);
  const cameraCommand = useRef<((action: CameraCommand['action'], degrees?: number) => void) | null>(null);
  const playbackRef = useRef({fullBuild,paused,onAnimationComplete});
  useEffect(()=>{playbackRef.current={fullBuild,paused,onAnimationComplete};});
  const [placementNote,setPlacementNote] = useState('');
  const [error, setError] = useState(''); const [loading, setLoading] = useState(true);
  useEffect(()=>{onReadyChange(!loading&&!error);},[loading,error,onReadyChange]);
  useEffect(()=>{ if(fullBuild) cameraCommand.current?.('reset'); else applyStep.current?.(false); },[fullBuild]);
  useEffect(() => {
    const changedStep = stepRef.current.step_id !== step.step_id;
    const changedMainStep = frameKey(stepRef.current) !== frameKey(step);
    stepRef.current = step;
    if(!changedStep)return; // Loading adjacent chunks must not cancel this step's animation.
    applyStep.current?.(false);
    if(!playbackRef.current.fullBuild) {
      if(changedMainStep)cameraCommand.current?.('reset');
      applyStep.current?.(true);
    }
  }, [step, previous]);
  useEffect(() => { if (replayToken) applyStep.current?.(true); }, [replayToken]);
  useEffect(() => { cameraCommand.current?.(command.action, command.degrees); }, [command]);
  useEffect(() => {
    if (!host.current) return;
    let cancelled = false; let frame = 0; let dirty = true; let viewportVisible = true;
    let tween: { elapsed: number; duration: number; from: Map<string, THREE.Vector3>; plan: ReplayPlan } | null = null;
    setError(''); setLoading(true); const element = host.current;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true }); }
    catch { setError('WebGL is unavailable. Open the original guide or try a supported browser.'); setLoading(false); return; }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); const benchmark=rendererAudit(renderer,manifest); renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    // Orbiting does not change world-space shadows; refresh them only when parts or lights move.
    renderer.shadowMap.autoUpdate = false; element.appendChild(renderer.domElement);
    renderer.domElement.setAttribute('aria-label', 'Assembly: drag to rotate, scroll to zoom, right-drag to pan');
    const world = new THREE.Scene(); world.background = new THREE.Color('#edf2f7');
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 20000);
    let sourceView: ReturnType<typeof createSourceCamera> | null = null;
    let sourceViewStepId: string | null = null;
    const clearSourceView = () => { sourceView = null; sourceViewStepId = null; dirty = true; delete element.dataset.sourceCameraFrame; };
    const controls = new OrbitControls(camera, renderer.domElement); controls.enableDamping = true;
    const invalidate = () => { dirty = true; };
    controls.addEventListener('change',invalidate);
    document.addEventListener('visibilitychange',invalidate);
    world.add(new THREE.HemisphereLight(0xffffff, 0x8292a6, 1.8));
    const light = new THREE.DirectionalLight(0xffffff, 2.3); light.position.set(-400,800,-300); light.castShadow = true;
    light.shadow.mapSize.set(512,512); light.shadow.normalBias = .6; light.shadow.bias = -.0001;
    world.add(light,light.target);
    const fill = new THREE.DirectionalLight(0xe4ecff,.7); fill.position.set(400,250,450); world.add(fill);
    const assembly = new THREE.Group(); world.add(assembly);
    const groups = new Map<string, THREE.Group>(); const outlines = new Map<string, THREE.BoxHelper>();
    // Deliberate benchmark opt-in only. This control changes the render camera,
    // never assembly poses, persisted progress, or normal tutorial defaults.
    const diagnosticScope = window as typeof window & {__guide2buildSourceCamera?:{apply:(value:unknown,stepId:string)=>unknown;clear:()=>void}};
    const sourceCameraControl = {
      apply(value: unknown, stepId: string) {
        if (cancelled || stepId !== stepRef.current.step_id || tween || groups.size !== manifest.instances.length) throw new Error('Source camera requires the loaded immutable snapshot');
        const box = new THREE.Box3(); for (const group of groups.values()) if(group.visible) box.expandByObject(group);
        const {width,height} = renderer.domElement.getBoundingClientRect();
        const candidate = createSourceCamera(value,width,height);
        const target = new THREE.Vector3().fromArray(candidate.spec.target_ldu);
        const depth = box.isEmpty() ? 100 : box.getCenter(new THREE.Vector3()).distanceTo(target)+box.getSize(new THREE.Vector3()).length();
        sourceView = createSourceCamera(candidate.spec,width,height,Math.max(100,depth)); sourceViewStepId = stepId; dirty = true;
        return inspectSourceCamera(sourceView);
      }, clear:clearSourceView,
    };
    if (benchmark) diagnosticScope.__guide2buildSourceCamera = sourceCameraControl;
    const emphasis = new Map<string, THREE.Group>();
    const mainStepFrames = new Map<string,{bounds:THREE.Box3; parts:THREE.Box3[]}>();
    const cache = new Map<string, Promise<THREE.Group>>(); const geometries = new Set<THREE.BufferGeometry>(); const materials = new Set<THREE.Material>();
    const register = (object: THREE.Object3D) => object.traverse(child => { if (child instanceof THREE.Mesh || child instanceof THREE.LineSegments) { geometries.add(child.geometry); (Array.isArray(child.material) ? child.material : [child.material]).forEach(m => materials.add(m)); } });
    // Replay emphasis reuses each actual part surface; it never adds or moves physical instances.
    const emphasisMaterial = new THREE.MeshBasicMaterial({color:0x2184ff,transparent:true,opacity:.2,depthWrite:false,polygonOffset:true,polygonOffsetFactor:-1,polygonOffsetUnits:-1});
    materials.add(emphasisMaterial);
    // A presentation-only shadow receiver; it never participates in assembly bounds or snapshots.
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(1,1),new THREE.ShadowMaterial({opacity:.05,depthWrite:false}));
    floor.rotation.x = -Math.PI/2; floor.receiveShadow = true; floor.visible = false; world.add(floor); register(floor);
    const updateStage = (box: THREE.Box3) => {
      dirty = true;
      floor.visible = !box.isEmpty(); if (box.isEmpty()) return;
      const center = box.getCenter(new THREE.Vector3()); const span = Math.max(60,box.getSize(new THREE.Vector3()).length());
      floor.position.set(center.x,box.min.y-1,center.z); floor.scale.setScalar(span*5);
      light.position.copy(center).add(new THREE.Vector3(-span*.45,span*3,-span*.3)); light.target.position.copy(center);
      Object.assign(light.shadow.camera,{left:-span,right:span,top:span,bottom:-span,near:1,far:span*6}); light.shadow.camera.updateProjectionMatrix();
      renderer.shadowMap.needsUpdate = true;
    };
    const manager = new THREE.LoadingManager(); const failures = new Set<string>();
    let resources: Record<string, {dependencies: string[]}> = {}; let fileMap: Record<string, string> = {};
    manager.setURLModifier(url => {
      const root = geometryBase;
      if (!url.startsWith(root) || url.includes('..') || url.includes('\\')) throw new Error('Unsafe part dependency');
      const ref = url.slice(root.length); if (ref === 'LDConfig.ldr') return modelAssetUrl(url).href;
      const bare = ref.replace(/^(parts|p)\//, '');
      const resolved = resources[ref] ? ref : resources[bare] ? bare : fileMap[ref] ?? fileMap[bare];
      if (!resolved || !resources[resolved] || resolved.includes('..')) throw new Error(`Unregistered part dependency: ${ref}`);
      return modelAssetUrl(root + resolved).href;
    });
    manager.onError = url => { failures.add(url); };
    const loader = new LDrawLoader(manager); loader.setConditionalLineMaterial(LDrawConditionalLineMaterial); loader.setPartsLibraryPath(geometryBase);
    applyStep.current = (animate = false) => {
      resetStunt();
      if (sourceViewStepId !== stepRef.current.step_id) clearSourceView();
      mainStepFrames.clear();
      for(const snapshot of manifestRef.current.steps) {
        if(frameKey(snapshot)!==frameKey(stepRef.current))continue;
        const bounds=new THREE.Box3();const parts:THREE.Box3[]=[];
        for(const id of snapshot.visible_instance_ids){const part=groups.get(id);const pose=snapshot.poses[id];if(!part||!pose)continue;const oldPosition=part.position.clone(),oldRotation=part.quaternion.clone();part.position.fromArray(pose.position_ldu);part.quaternion.fromArray(pose.quaternion_xyzw);const box=new THREE.Box3().setFromObject(part);bounds.union(box);parts.push(box);part.position.copy(oldPosition);part.quaternion.copy(oldRotation);}
        const key=frameKey(snapshot);const frame=mainStepFrames.get(key)??{bounds:new THREE.Box3(),parts:[]};frame.bounds.union(bounds);frame.parts.push(...parts);mainStepFrames.set(key,frame);
      }
      tween = null; setPlacementNote(''); const current = stepRef.current; const visible = new Set(current.visible_instance_ids); const active = new Set(current.active_instance_ids);
      // Active IDs can include supporting pieces. Additions fly in only new pieces;
      // an attachment moves the existing subassembly using the same physical IDs.
      const movingIds = new Set(current.action==='attach_subassembly'?current.active_instance_ids:current.introduced_instance_ids);
      const showActiveOutlines = current.action !== 'inspect' || current.introduced_instance_ids.length > 0;
      delete element.dataset.placementMode; delete element.dataset.placementReason; delete element.dataset.approachReason; delete element.dataset.animationInstanceIds;
      const from = new Map<string, THREE.Vector3>();
      for (const [id, group] of groups) {
        group.visible = visible.has(id); const pose = current.poses[id];
        if (pose) {
          group.position.fromArray(pose.position_ldu); group.quaternion.fromArray(pose.quaternion_xyzw);
          if (animate && showActiveOutlines && group.visible && movingIds.has(id) && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
            from.set(id,group.position.clone());
          }
        }
        const outline = outlines.get(id); if (outline) { outline.visible = showActiveOutlines && group.visible && active.has(id); (outline.material as THREE.Material).opacity=1; (outline.material as THREE.Material).transparent=false; outline.update(); }
        const overlay = emphasis.get(id); if (overlay) overlay.visible = false;
      }
      const stageBounds = new THREE.Box3(); for (const group of groups.values()) if (group.visible) stageBounds.expandByObject(group);
      updateStage(mainStepFrames.get(frameKey(current))?.bounds ?? stageBounds);
      if (from.size) {
        const moving=[...from.keys()].map(id=>new THREE.Box3().setFromObject(groups.get(id)!));
        const obstacles=[...groups].filter(([id,group])=>group.visible&&!from.has(id)).map(([,group])=>new THREE.Box3().setFromObject(group));
        const approach=checkedApproach(approachFor(manifest,current),moving,obstacles);
        const viewHeight=2*camera.position.distanceTo(controls.target)*Math.tan(THREE.MathUtils.degToRad(camera.fov/2));
        const plan=replayPlan(approach,camera.quaternion,viewHeight);
        if(plan.mode!=='highlight') for(const [id,start] of from) {
          start.add(plan.offset); groups.get(id)!.position.copy(start); outlines.get(id)?.update();
        }
        if(plan.mode==='highlight') for(const id of from.keys()) emphasis.get(id)!.visible = true;
        setPlacementNote(plan.mode==='preview' ? 'Fly-in preview · follow the guide for attachment.' : plan.reason==='below'?'Attach from underneath.':'Attach from above.');
        tween={elapsed:0,duration:playbackRef.current.fullBuild?1800:1000,from,plan};
        element.dataset.placementMode=plan.mode; element.dataset.placementReason=plan.reason; element.dataset.approachReason=approach.reason;
        element.dataset.animationInstanceIds=JSON.stringify([...from.keys()]);
        renderer.shadowMap.needsUpdate=true;
      }
      if(animate && !tween) { if(showActiveOutlines&&movingIds.size)setPlacementNote('Motion off · pieces shown in place.'); playbackRef.current.onAnimationComplete(); }
      element.dataset.animationState=tween?(playbackRef.current.paused?'paused':'playing'):'idle';
    };
    let buildBounds: THREE.Box3 | null = null;
    let orbitFrame = 0;
    let viewTouched = false; // The user or the agent moved the camera since the last fit.
    // Showpiece only ("make it fly and explode"): a presentation animation over the visible pieces. It never changes
    // scene data; any step change or "reassemble" puts every piece back on its recorded pose.
    let stunt: ((seconds: number) => void) | null = null;
    let exploded: { group: THREE.Group; home: THREE.Vector3; homeQ: THREE.Quaternion }[] | null = null;
    const STAGE = new THREE.Color('#edf2f7'), FLASH = new THREE.Color('#fff3c4'), UP = new THREE.Vector3(0,1,0);
    const fireball = new THREE.Mesh(new THREE.SphereGeometry(1,20,14), new THREE.MeshBasicMaterial({color:0xff9a1f,transparent:true,opacity:0,depthWrite:false}));
    fireball.visible = false; world.add(fireball); register(fireball);
    const resetStunt = () => {
      if (!stunt && !exploded) return;
      stunt = null; exploded = null; controls.autoRotate = false; fireball.visible = false;
      assembly.position.set(0,0,0); assembly.quaternion.identity(); (world.background as THREE.Color).copy(STAGE); dirty = true;
    };
    let backedOff = 1; // Distance factor added for narrower layouts since then.
    controls.addEventListener('start', () => { viewTouched = true; });
    const fit = () => {
      cancelAnimationFrame(orbitFrame); viewTouched = false; backedOff = 1;
      stopCameraMotion(camera, controls);
      const siblingFrame = mainStepFrames.get(frameKey(stepRef.current));
      const frameBounds = playbackRef.current.fullBuild && buildBounds ? buildBounds : siblingFrame?.bounds;
      const box = frameBounds ? frameBounds.clone() : new THREE.Box3(); if(!frameBounds) for (const group of groups.values()) if (group.visible) box.expandByObject(group);
      const center = box.isEmpty() ? new THREE.Vector3() : box.getCenter(new THREE.Vector3());
      const radius = box.isEmpty() ? 100 : Math.max(40, box.getSize(new THREE.Vector3()).length());
      const direction = new THREE.Vector3(-.8,.93,-.48).normalize();
      camera.position.copy(center).add(direction); camera.lookAt(center);
      const inverseRotation = camera.quaternion.clone().invert();
      const tanVertical = Math.tan(THREE.MathUtils.degToRad(camera.fov/2)); const tanHorizontal = tanVertical*camera.aspect;
      let distance = radius;
      // Individual part bounds avoid framing the large empty corners around a diagonal assembly.
      // Playback retains the complete sequence bounds, including callouts and approach motion.
      const fitBoxes = playbackRef.current.fullBuild && buildBounds ? [box] : siblingFrame?.parts ?? [...groups.values()].filter(group=>group.visible).map(group=>new THREE.Box3().setFromObject(group));
      for (const partBox of fitBoxes) if (!partBox.isEmpty()) for (const x of [partBox.min.x,partBox.max.x]) for (const y of [partBox.min.y,partBox.max.y]) for (const z of [partBox.min.z,partBox.max.z]) {
        const corner = new THREE.Vector3(x,y,z).sub(center).applyQuaternion(inverseRotation);
        distance = Math.max(distance,corner.z+1.46*Math.max(Math.abs(corner.x)/tanHorizontal,Math.abs(corner.y)/tanVertical));
      }
      controls.minDistance = radius * .6; controls.maxDistance = Math.max(radius*6,distance*3);
      camera.position.copy(center).addScaledVector(direction,distance); controls.target.copy(center); controls.update();
      updateStage(box);
    };
    // Chat/voice commands orbit by an angle with easing; toolbar buttons keep their fixed nudge.
    const orbit = (radians: number, vertical: boolean) => {
      cancelAnimationFrame(orbitFrame); stopCameraMotion(camera, controls); // Drop drag inertia, or the turn overshoots.
      const started = performance.now(), duration = Math.min(3200, Math.max(600, Math.abs(radians) * 800)); let applied = 0;
      const tick = (now: number) => {
        if (cancelled) return;
        const t = Math.min(1, (now - started) / duration), eased = t < .5 ? 2*t*t : 1 - Math.pow(-2*t + 2, 2) / 2;
        const delta = eased * radians - applied; applied += delta;
        const offset = camera.position.clone().sub(controls.target);
        offset.applyAxisAngle(vertical ? new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0) : camera.up, delta);
        camera.position.copy(controls.target).add(offset); controls.update(); dirty = true;
        if (t < 1) orbitFrame = requestAnimationFrame(tick);
      };
      orbitFrame = requestAnimationFrame(tick);
    };
    const announce = (phase: string) => window.dispatchEvent(new CustomEvent<string>(STUNT_EVENT, {detail: phase}));
    const ease = (t: number) => t < .5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2;
    const flyAndExplode = () => {
      applyStep.current?.(false); // Start from the real poses of the current step (this also ends any earlier stunt).
      const flyers = [...groups.values()].filter(group => group.visible).map(group => ({group, home: group.position.clone(), homeQ: group.quaternion.clone(),
        velocity: new THREE.Vector3(), axis: new THREE.Vector3(), spin: 0, from: new THREE.Vector3(), fromQ: new THREE.Quaternion(), target: new THREE.Vector3()}));
      if (!flyers.length) return;
      cancelAnimationFrame(orbitFrame); stopCameraMotion(camera, controls); viewTouched = true; setPlacementNote('');
      outlines.forEach(outline => { outline.visible = false; }); emphasis.forEach(overlay => { overlay.visible = false; });
      const box = new THREE.Box3(); flyers.forEach(flyer => box.expandByObject(flyer.group));
      const center = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
      const ground = box.min.y, span = Math.max(size.x, size.z, 60);
      // Which way is forward? Use the pieces the booklet calls the nose and the tail; fall back to the long axis.
      const centroid = (pattern: RegExp) => {
        const points = manifestRef.current.steps.filter(item => pattern.test(item.instruction)).flatMap(item => item.introduced_instance_ids)
          .map(id => groups.get(id)).filter((group): group is THREE.Group => !!group?.visible).map(group => group.position);
        return points.length ? points.reduce((sum, point) => sum.add(point), new THREE.Vector3()).divideScalar(points.length) : null;
      };
      const nose = centroid(/\bnose\b/i), tail = centroid(/\btail/i);
      const forward = nose && tail ? nose.clone().sub(tail) : nose ? nose.clone().sub(center) : new THREE.Vector3(size.x >= size.z ? 1 : 0, 0, size.x >= size.z ? 0 : 1);
      forward.y = 0; if (forward.lengthSq() < 1e-6) forward.set(1,0,0); forward.normalize();
      const left = new THREE.Vector3().crossVectors(UP, forward).normalize();
      const radius = span * 1.2, height = span * .8, circle = center.clone().addScaledVector(left, radius);
      const reach = (extent: number) => extent / (Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * Math.min(1, camera.aspect));
      const view = camera.position.clone().sub(controls.target).normalize(); view.y = Math.max(view.y, .5); view.normalize();
      const cameraFrom = camera.position.clone(), targetFrom = controls.target.clone();
      const flightTarget = circle.clone().addScaledVector(UP, height * .45), flightCamera = flightTarget.clone().addScaledVector(view, reach(radius + span * .75) * 1.05);
      const lift = span * .35, explodedTarget = center.clone().addScaledVector(UP, lift + size.y);
      let widest = span;
      for (const flyer of flyers) {
        const offset = flyer.home.clone().sub(center);
        flyer.target.set(center.x + offset.x * 2.3, center.y + lift + (flyer.home.y - ground) * 3.4, center.z + offset.z * 2.3);
        widest = Math.max(widest, flyer.target.distanceTo(explodedTarget) + 40);
      }
      const explodedCamera = explodedTarget.clone().addScaledVector(view, reach(widest) * 1.15);
      const crash = center.clone().addScaledVector(forward, span * .9); crash.y = ground + size.y * .45;
      const impact = crash.clone().addScaledVector(forward, span * .3); impact.y = ground;
      controls.maxDistance = Math.max(controls.maxDistance, reach(radius + span) * 3, reach(widest) * 3);
      const pose = (position: THREE.Vector3, yaw: number, pitch: number, roll: number) => {
        const q = new THREE.Quaternion().setFromAxisAngle(UP, yaw).multiply(new THREE.Quaternion().setFromAxisAngle(left, pitch)).multiply(new THREE.Quaternion().setFromAxisAngle(forward, roll));
        assembly.quaternion.copy(q); assembly.position.copy(position).sub(center.clone().applyQuaternion(q));
      };
      const FLY = 4.6, DIVE = 1, BURST = 1.3, SETTLE = 1.8; let time = 0, burst = false, settling = false;
      const jitter = new THREE.Vector3(), burstCamera = new THREE.Vector3(), burstTarget = new THREE.Vector3();
      announce('takeoff');
      stunt = seconds => {
        time += seconds; camera.position.sub(jitter); jitter.set(0,0,0);
        if (time < FLY) {
          const u = time / FLY, angle = Math.PI * 2 * ease(u), climb = ease(Math.min(1, u / .3));
          const position = circle.clone().addScaledVector(left, -Math.cos(angle) * radius).addScaledVector(forward, Math.sin(angle) * radius).addScaledVector(UP, height * climb);
          pose(position, angle, -.3 * Math.sin(Math.PI * Math.min(1, u / .3)), -.5 * Math.sin(Math.PI * u));
          const k = ease(Math.min(1, time / .9)); camera.position.lerpVectors(cameraFrom, flightCamera, k); controls.target.lerpVectors(targetFrom, flightTarget, k);
        } else if (time < FLY + DIVE) {
          if (!settling) { settling = true; announce('dive'); }
          const k = Math.pow((time - FLY) / DIVE, 2);
          pose(center.clone().addScaledVector(UP, height).lerp(crash, k), 0, k * 1.05, Math.sin(k * 9) * .12);
          controls.target.lerpVectors(flightTarget, impact, k * .6);
        } else if (!burst) {
          burst = true; settling = false; announce('impact');
          // The rigid plane becomes loose pieces, each starting exactly where the crash left it.
          const q = assembly.quaternion.clone(), shift = assembly.position.clone();
          for (const flyer of flyers) {
            flyer.group.position.applyQuaternion(q).add(shift); flyer.group.quaternion.premultiply(q);
            const away = flyer.group.position.clone().sub(impact); away.y = 0; if (away.lengthSq() < 1) away.set(Math.random() - .5, 0, Math.random() - .5); away.normalize();
            flyer.velocity.copy(away).multiplyScalar(span * (1.2 + Math.random() * 1.8)).addScaledVector(UP, span * (2.4 + Math.random() * 2.2));
            flyer.axis.set(Math.random() - .5, Math.random() - .5, Math.random() - .5).normalize(); flyer.spin = 4 + Math.random() * 8;
          }
          assembly.position.set(0,0,0); assembly.quaternion.identity();
          fireball.position.copy(impact); fireball.visible = true; burstCamera.copy(camera.position); burstTarget.copy(controls.target);
        } else if (time < FLY + DIVE + BURST) {
          const t = (time - FLY - DIVE) / BURST, gravity = span * 9;
          for (const flyer of flyers) {
            flyer.velocity.y -= gravity * seconds; flyer.group.position.addScaledVector(flyer.velocity, seconds);
            if (flyer.group.position.y < ground + 6) { flyer.group.position.y = ground + 6; flyer.velocity.y *= -.4; flyer.velocity.x *= .6; flyer.velocity.z *= .6; flyer.spin *= .6; }
            flyer.group.quaternion.premultiply(new THREE.Quaternion().setFromAxisAngle(flyer.axis, flyer.spin * seconds));
          }
          fireball.scale.setScalar(span * (.3 + 1.6 * Math.sqrt(t))); (fireball.material as THREE.MeshBasicMaterial).opacity = Math.max(0, .85 * (1 - t * 1.6));
          (world.background as THREE.Color).lerpColors(FLASH, STAGE, Math.min(1, t * 2.5));
          if (t < .45) { jitter.set(Math.random() - .5, Math.random() - .5, Math.random() - .5).multiplyScalar(span * .12 * (1 - t / .45)); camera.position.add(jitter); }
        } else if (time < FLY + DIVE + BURST + SETTLE) {
          if (!settling) { settling = true; fireball.visible = false; (world.background as THREE.Color).copy(STAGE); for (const flyer of flyers) { flyer.from.copy(flyer.group.position); flyer.fromQ.copy(flyer.group.quaternion); } }
          const k = ease((time - FLY - DIVE - BURST) / SETTLE);
          for (const flyer of flyers) { flyer.group.position.lerpVectors(flyer.from, flyer.target, k); flyer.group.quaternion.slerpQuaternions(flyer.fromQ, flyer.homeQ, k); }
          camera.position.lerpVectors(burstCamera, explodedCamera, k); controls.target.lerpVectors(burstTarget, explodedTarget, k);
        } else {
          for (const flyer of flyers) { flyer.group.position.copy(flyer.target); flyer.group.quaternion.copy(flyer.homeQ); }
          stunt = null; exploded = flyers; controls.autoRotate = true; controls.autoRotateSpeed = 1.6; announce('settled');
        }
      };
    };
    const reassemble = () => {
      const pieces = exploded; if (!pieces) { applyStep.current?.(false); return; }
      controls.autoRotate = false; const starts = pieces.map(piece => ({position: piece.group.position.clone(), q: piece.group.quaternion.clone()})); let time = 0;
      stunt = seconds => {
        time += seconds; const k = ease(Math.min(1, time / 1.4));
        pieces.forEach((piece, i) => { piece.group.position.lerpVectors(starts[i].position, piece.home, k); piece.group.quaternion.slerpQuaternions(starts[i].q, piece.homeQ, k); });
        if (k === 1) { applyStep.current?.(false); fit(); }
      };
    };
    cameraCommand.current = (action, degrees) => {
      clearSourceView();
      if (action === 'fly') { flyAndExplode(); return; }
      if (action === 'reassemble') { reassemble(); return; }
      if (action === 'reset') { fit(); return; }
      viewTouched = true;
      if (action === 'up' || action === 'down') orbit(THREE.MathUtils.degToRad(degrees ?? 45) * (action === 'up' ? -1 : 1), true);
      else if (degrees !== undefined && (action === 'left' || action === 'right')) orbit(THREE.MathUtils.degToRad(degrees) * (action === 'left' ? -1 : 1), false);
      else moveCamera(camera, controls, action);
    };
    const resize = new ResizeObserver(() => { const {width,height} = element.getBoundingClientRect(); viewportVisible = width >= 1 && height >= 1; if (!viewportVisible) return; const previousAspect = camera.aspect; camera.aspect = width/height; camera.updateProjectionMatrix(); renderer.setSize(width,height);
      // A layout change (such as the chat panel opening) must not throw away a view the user chose: keep the angle, only adjust the distance.
      if (!viewTouched) fit(); else {
        // Back off when the canvas gets narrower so the model stays in frame; when it widens again undo only that back-off, never zoom past the user's view.
        const ratio = previousAspect/camera.aspect, factor = ratio > 1 ? Math.min(ratio, 2) : 1/Math.min(backedOff, 1/ratio);
        backedOff *= factor; cancelAnimationFrame(orbitFrame);
        const offset = camera.position.clone().sub(controls.target).multiplyScalar(factor); camera.position.copy(controls.target).add(offset); controls.update(); dirty = true;
      } if(sourceView) sourceCameraControl.apply(sourceView.spec,stepRef.current.step_id); }); resize.observe(element);
    let lastFrame=performance.now();
    const draw = () => {
      const now=performance.now();const delta=now-lastFrame;lastFrame=now;
      if (stunt && !document.hidden) { dirty = true; renderer.shadowMap.needsUpdate = true; stunt(Math.min(delta, 50) / 1000); }
      if (tween && !playbackRef.current.paused) {
        dirty = true;
        if (tween.plan.mode !== 'highlight') renderer.shadowMap.needsUpdate = true;
        tween.elapsed+=delta;
        const progress = Math.min(1,tween.elapsed/tween.duration); const t = 1-Math.pow(1-progress,3);
        emphasisMaterial.opacity = .08+.28*Math.pow(Math.sin(progress*Math.PI*2),2);
        for (const [id, start] of tween.from) {
          const group=groups.get(id)!;const pose=stepRef.current.poses[id];if(!pose)continue;
          if(tween.plan.mode!=='highlight') group.position.lerpVectors(start,new THREE.Vector3().fromArray(pose.position_ldu),t);
          const outline=outlines.get(id); if(outline){
            const material=outline.material as THREE.Material;
            material.transparent=true;
            material.opacity=tween.plan.mode==='highlight'?.2+.8*Math.pow(Math.cos(progress*Math.PI*2),2):1;
            outline.update();
          }
        }
        if (progress === 1) { const wasHighlight = tween.plan.mode==='highlight'; tween = null; applyStep.current?.(false); if(wasHighlight && !playbackRef.current.fullBuild) setPlacementNote('Replay complete · highlighted pieces are shown in place.'); playbackRef.current.onAnimationComplete(); }
      }
      // Continue ticking damping/playback, but leave an unchanged canvas alone.
      // The change listener also catches toolbar commands that update controls before this tick.
      controls.update();
      if (dirty && viewportVisible && !document.hidden) {
        const drawingCamera = sourceView?.camera ?? camera;
        const visibleOutlines = sourceView ? [...outlines.values()].filter(outline=>outline.visible) : [];
        for(const outline of visibleOutlines) outline.visible = false;
        if(benchmark)benchmark.render(world,drawingCamera,'viewport',stepRef.current.step_id);else renderer.render(world,drawingCamera); dirty = false;
        for(const outline of visibleOutlines) outline.visible = true;
        // Recorded from the actual camera for regression checks of sibling-step framing.
        element.dataset.cameraFrame = [...drawingCamera.position.toArray(),...(sourceView?.spec.target_ldu ?? controls.target.toArray()),camera.aspect].map(value=>value.toFixed(6)).join(',');
        element.dataset.cameraMode = sourceView ? 'source_orthographic' : 'perspective';
        if(sourceView) element.dataset.sourceCameraFrame = JSON.stringify(inspectSourceCamera(sourceView));
      }
      benchmark?.poll();
      const animationState = tween ? (playbackRef.current.paused?'paused':'playing') : 'idle';
      if (element.dataset.animationState !== animationState) element.dataset.animationState = animationState;
      const geometryCount = String(renderer.info.memory.geometries); const drawCalls = String(renderer.info.render.calls);
      if (element.dataset.geometryCount !== geometryCount) element.dataset.geometryCount = geometryCount;
      if (element.dataset.drawCalls !== drawCalls) element.dataset.drawCalls = drawCalls;
      frame = requestAnimationFrame(draw);
    }; fit(); draw();
    const onLost = (event: Event) => { event.preventDefault(); setError('The 3D graphics context was lost. Reopen the tutorial to restore the viewer.'); }; renderer.domElement.addEventListener('webglcontextlost',onLost);
    (async () => {
      if(benchmark)benchmark.audit.phases.assetLoadingStartMs=performance.now();
      const provenanceResponse = await fetch(modelAssetUrl(geometryBase+'provenance.json'));
      if (!provenanceResponse.ok) throw new Error('Individual-part provenance catalogue is unavailable.');
      const provenance = await provenanceResponse.json();
      if (!provenance || typeof provenance.resources !== 'object') throw new Error('Invalid part provenance catalogue.');
      resources = provenance.resources; fileMap = provenance.file_map ?? {};
      for (const path of Object.keys(resources)) {
        const bare = path.replace(/^(parts|p)\//, ''); if (!fileMap[bare]) fileMap[bare] = path;
      }
      const visited = new Set<string>();
      const verifyDependencies = (path: string, depth = 0) => {
        if (depth > 40) throw new Error('Part dependency depth exceeded.');
        if (visited.has(path)) return; visited.add(path);
        if (!resources[path] || !Array.isArray(resources[path].dependencies)) throw new Error(`Unregistered part: ${path}`);
        for (const dependency of resources[path].dependencies) verifyDependencies(dependency, depth+1);
      };
      manifest.instances.forEach(part => verifyDependencies(part.geometry_ref));
      await loader.preloadMaterials(geometryBase+'LDConfig.ldr');
      loader.materials.forEach(material => materials.add(material));
      if (cancelled) { materials.forEach(material => material.dispose()); return; }
      for (const part of manifest.instances) if (!loader.getMaterial(part.color_code)) throw new Error(`Part ${part.part_id}: unknown LDraw colour ${part.color_code}.`);
      const colorNames: Record<string,string> = {};
      for (const part of manifest.instances) {
        const name = loader.getMaterial(part.color_code)?.name;
        if (name) colorNames[part.color_code] = name.replaceAll('_',' ');
      }
      onColorNames?.(colorNames);
      for (const part of manifest.instances) {
        if (cancelled) return; const key = `${part.geometry_ref}:${part.color_code}`;
        if (!cache.has(key)) {
          const reference = `0 Individual part\n1 ${part.color_code} 0 0 0 1 0 0 0 1 0 0 0 1 ${part.geometry_ref}\n`;
          cache.set(key,new Promise<THREE.Group>((resolve,reject) => loader.parse(reference,resolve,reject)));
        }
        let original: THREE.Group;
        try { original = await cache.get(key)!; } catch { throw new Error(`Part ${part.part_id} (${part.geometry_ref}) could not be loaded.`); }
        register(original);
        if (cancelled) { geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose()); return; }
        if (failures.size) throw new Error(`Part ${part.part_id}: missing geometry dependency. ${[...failures].join(', ')}`);
        const instance = new THREE.Group(); const geometry = original.clone(true); geometry.rotation.x = Math.PI; // One proper LDraw → canonical conversion.
        geometry.traverse(child => {
          if (child instanceof THREE.Mesh) {
            const surface = Array.isArray(child.material) ? child.material : [child.material];
            child.castShadow = surface.every(material => !material.transparent || material.opacity >= 1);
            child.receiveShadow = true;
          } else if (child instanceof THREE.LineSegments) {
            // Retain LDraw's authored edges, lightly drawn over the shaded plastic.
            // Active blue outlines are separate objects and remain fully opaque.
            for (const material of Array.isArray(child.material) ? child.material : [child.material]) {
              material.opacity = Math.min(material.opacity,.24); material.transparent = true; material.depthWrite = false;
            }
          }
        });
        instance.add(geometry); instance.visible = false; assembly.add(instance); groups.set(part.instance_id,instance);
        const overlay = geometry.clone(true); overlay.visible = false;
        overlay.traverse(child => { if(child instanceof THREE.Mesh) {child.material = emphasisMaterial; child.castShadow = false; child.receiveShadow = false;} else if(child instanceof THREE.LineSegments) child.visible = false; });
        instance.add(overlay); emphasis.set(part.instance_id,overlay);
        const outline = new THREE.BoxHelper(instance,0x0875e1); outline.visible = false; world.add(outline); outlines.set(part.instance_id,outline); register(outline);
      }
      if(benchmark)benchmark.audit.phases.geometryLoadedMs=performance.now();
      const thumbnails: Record<string,string> = {};
      renderer.setSize(80,80,false); camera.aspect = 1; camera.updateProjectionMatrix();
      for (const part of manifest.instances) {
        const key = `${part.part_id}:${part.color_code}`; if (thumbnails[key]) continue;
        for (const [id, group] of groups) { group.visible = id === part.instance_id; group.position.set(0,0,0); group.quaternion.identity(); }
        fit(); if(benchmark)benchmark.render(world,camera,'thumbnail',stepRef.current.step_id);else renderer.render(world,camera); thumbnails[key] = renderer.domElement.toDataURL('image/png');
      }
      if(benchmark)benchmark.audit.phases.thumbnailsFinishedMs=performance.now();
      onThumbnails(thumbnails);
      const {width,height} = element.getBoundingClientRect(); renderer.setSize(Math.max(width,1),Math.max(height,1)); camera.aspect=Math.max(width,1)/Math.max(height,1); camera.updateProjectionMatrix();
      // One framing for the whole playback, including detached callouts and entry motion.
      buildBounds=new THREE.Box3();
      const siblingCounts = new Map<string,number>(); for(const snapshot of manifestRef.current.steps) siblingCounts.set(frameKey(snapshot),(siblingCounts.get(frameKey(snapshot))??0)+1);
      for(const snapshot of manifestRef.current.steps) for(const id of snapshot.visible_instance_ids) {
        const group=groups.get(id)!;const pose=snapshot.poses[id];if(!pose)continue;
        group.position.fromArray(pose.position_ldu);group.quaternion.fromArray(pose.quaternion_xyzw);
        const partBounds = new THREE.Box3().setFromObject(group); buildBounds.union(partBounds);
        if(siblingCounts.get(frameKey(snapshot))! > 1) {
          if(!mainStepFrames.has(frameKey(snapshot))) mainStepFrames.set(frameKey(snapshot),{bounds:new THREE.Box3(),parts:[]});
          const frame = mainStepFrames.get(frameKey(snapshot))!; frame.bounds.union(partBounds); frame.parts.push(partBounds);
        }
      }
      if(!buildBounds.isEmpty()){buildBounds.max.y+=60;buildBounds.min.y-=60;}
      applyStep.current?.(); fit();
      if(!playbackRef.current.fullBuild)applyStep.current?.(true);
      if (!cancelled) { if(benchmark)benchmark.audit.readyAtMs=performance.now(); setLoading(false); }
    })().catch(e => { if (!cancelled) { assembly.visible = false; floor.visible = false; outlines.forEach(o => o.visible = false); dirty = true; setError(`Required geometry unavailable. ${e instanceof Error ? e.message : 'Asset error'}`); setLoading(false); } });
    return () => { cancelled = true; if(diagnosticScope.__guide2buildSourceCamera === sourceCameraControl) delete diagnosticScope.__guide2buildSourceCamera; cancelAnimationFrame(frame); resize.disconnect(); controls.removeEventListener('change',invalidate); document.removeEventListener('visibilitychange',invalidate); controls.dispose(); renderer.domElement.removeEventListener('webglcontextlost',onLost); geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose()); light.shadow.dispose(); benchmark?.dispose(); renderer.dispose();
      // Disposal frees Three.js resources; release the browser context as well
      // when closing a tutorial or replacing a chunk's viewport.
      renderer.forceContextLoss(); renderer.domElement.remove(); applyStep.current = null; cameraCommand.current = null; };
  }, [manifest.revision, geometryBase]);
  return <div className="viewport-wrap"><div className="viewport" ref={host} data-step-id={step.step_id}/>{placementNote && <p className="placement-note" role="status">{placementNote}</p>}{loading && <p role="status" className="viewport-message">Loading individual part geometry…</p>}{error && <p role="alert" className="viewport-message error">{error}</p>}</div>;
}
