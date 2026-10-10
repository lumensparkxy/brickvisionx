import { MathUtils, Matrix4, OrthographicCamera, PerspectiveCamera, Vector3 } from 'three';
import type { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export type CameraAction = 'reset' | 'left' | 'right' | 'in' | 'out' | 'pan-left' | 'pan-right';

export interface SourceCameraSpec {
  projection: 'orthographic'; right: [number,number,number]; up: [number,number,number];
  target_ldu: [number,number,number]; vertical_span_ldu: number; image_size: [number,number];
}

/** A private render diagnostic, never an alternate assembly/snapshot contract. */
export function validateSourceCamera(value: unknown): SourceCameraSpec {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid source camera');
  const item = value as Record<string, unknown>;
  const keys = ['projection','right','up','target_ldu','vertical_span_ldu','image_size'];
  if (Object.keys(item).length !== keys.length || Object.keys(item).some(key => !keys.includes(key)) || item.projection !== 'orthographic') throw new Error('Invalid source camera fields');
  for (const key of ['right','up','target_ldu']) {
    const vector = item[key];
    if (!Array.isArray(vector) || vector.length !== 3 || vector.some(v => typeof v !== 'number' || !Number.isFinite(v) || Math.abs(v) > 1_000_000)) throw new Error('Invalid source camera vector');
  }
  if (typeof item.vertical_span_ldu !== 'number' || !Number.isFinite(item.vertical_span_ldu) || item.vertical_span_ldu < .001 || item.vertical_span_ldu > 10_000_000) throw new Error('Invalid source camera span');
  if (!Array.isArray(item.image_size) || item.image_size.length !== 2 || item.image_size.some(v => !Number.isInteger(v) || v < 64 || v > 16_384)) throw new Error('Invalid source camera image dimensions');
  const right = new Vector3().fromArray(item.right as number[]), up = new Vector3().fromArray(item.up as number[]);
  if (Math.abs(right.lengthSq()-1) > 1e-6 || Math.abs(up.lengthSq()-1) > 1e-6 || Math.abs(right.dot(up)) > 1e-6) throw new Error('Source camera axes must be orthonormal');
  return {projection:'orthographic', right:right.toArray(), up:up.toArray(), target_ldu:[...(item.target_ldu as [number,number,number])], vertical_span_ldu:item.vertical_span_ldu, image_size:[...(item.image_size as [number,number])]};
}

/** Fit the whole official page into the canvas; the central rect has its exact aspect. */
export function createSourceCamera(input: unknown, width: number, height: number, depthExtentLdu = 10_000) {
  const spec = validateSourceCamera(input);
  if (![width,height,depthExtentLdu].every(v => Number.isFinite(v) && v > 0) || width > 16_384 || height > 16_384 || depthExtentLdu > 10_000_000) throw new Error('Invalid source camera viewport bounds');
  const aspect = width/height, sourceAspect = spec.image_size[0]/spec.image_size[1];
  const vertical = spec.vertical_span_ldu*Math.max(1,sourceAspect/aspect), horizontal = vertical*aspect;
  const distance = Math.max(100, depthExtentLdu*2+100);
  const camera = new OrthographicCamera(-horizontal/2,horizontal/2,vertical/2,-vertical/2,.1,distance*2);
  const right = new Vector3().fromArray(spec.right), up = new Vector3().fromArray(spec.up), back = new Vector3().crossVectors(right,up).normalize();
  camera.position.fromArray(spec.target_ldu).addScaledVector(back,distance);
  camera.up.copy(up); camera.quaternion.setFromRotationMatrix(new Matrix4().makeBasis(right,up,back));
  camera.updateProjectionMatrix(); camera.updateMatrixWorld(true);
  const cropWidth = Math.min(width,height*sourceAspect), cropHeight = Math.min(height,width/sourceAspect);
  const sourceRect = {x:(width-cropWidth)/2,y:(height-cropHeight)/2,width:cropWidth,height:cropHeight};
  return {camera,spec,sourceRect,viewport:{width,height}};
}

/** Read actual camera matrices, not caller-supplied claims, for the screenshot receipt. */
export function inspectSourceCamera(view: ReturnType<typeof createSourceCamera>) {
  const {camera,spec,sourceRect,viewport} = view;
  camera.updateMatrixWorld(true);
  return {mode:'source_orthographic', input:spec, source_rect:sourceRect, viewport,
    position_ldu:camera.position.toArray(), quaternion_xyzw:camera.quaternion.toArray(),
    frustum:{left:camera.left,right:camera.right,top:camera.top,bottom:camera.bottom,near:camera.near,far:camera.far,zoom:camera.zoom},
    projection_matrix:camera.projectionMatrix.toArray(), matrix_world_inverse:camera.matrixWorldInverse.toArray()};
}

/** Discard drag inertia at the currently displayed view before an explicit button action. */
export function stopCameraMotion(camera: PerspectiveCamera, controls: OrbitControls) {
  const position = camera.position.clone();
  const target = controls.target.clone();
  const damping = controls.enableDamping;
  controls.enableDamping = false;
  controls.update(); // Public API clears pending rotation and pan deltas without damping.
  camera.position.copy(position);
  controls.target.copy(target);
  controls.update();
  controls.enableDamping = damping;
}

export function moveCamera(camera: PerspectiveCamera, controls: OrbitControls, action: Exclude<CameraAction, 'reset'>) {
  stopCameraMotion(camera, controls);
  // Capture the offset BEFORE modifying camera.position (Vector3 methods mutate their receiver).
  const offset = camera.position.clone().sub(controls.target);
  if (action === 'in' || action === 'out') {
    const distance = MathUtils.clamp(offset.length() * (action === 'in' ? .8 : 1.25), controls.minDistance, controls.maxDistance);
    camera.position.copy(controls.target).add(offset.setLength(distance));
  } else if (action === 'left' || action === 'right') {
    offset.applyAxisAngle(camera.up, action === 'left' ? -.3 : .3);
    camera.position.copy(controls.target).add(offset);
  } else {
    // Move the camera by 10% of the visible width, independent of model size and zoom.
    const width = 2 * offset.length() * Math.tan(MathUtils.degToRad(camera.fov / 2)) * camera.aspect;
    camera.updateMatrixWorld();
    const pan = new Vector3().setFromMatrixColumn(camera.matrixWorld, 0)
      .multiplyScalar(width * (action === 'pan-left' ? -.1 : .1));
    camera.position.add(pan);
    controls.target.add(pan);
  }
  controls.update();
}
