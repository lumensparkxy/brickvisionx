import { describe, expect, it } from 'vitest';
import { PerspectiveCamera, Vector3 } from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { createSourceCamera, inspectSourceCamera, moveCamera, validateSourceCamera } from './camera';

function setup() {
  const camera = new PerspectiveCamera(38, 1.5, .1, 20000);
  const controls = new OrbitControls(camera, null);
  controls.target.set(30, 12, -70);
  camera.position.set(-130, 198, -166);
  controls.minDistance = 120; controls.maxDistance = 1200;
  controls.enableDamping = true; controls.update();
  return { camera, controls };
}
const close = (actual: Vector3, expected: Vector3) => expect(actual.distanceTo(expected)).toBeLessThan(1e-8);
describe('camera toolbar', () => {
  it('zooms towards an offset target without jumping into it, and reverses', () => {
    const {camera, controls} = setup(); const original = camera.position.clone();
    const offset = original.clone().sub(controls.target);
    moveCamera(camera, controls, 'in');
    close(camera.position.clone().sub(controls.target), offset.clone().multiplyScalar(.8));
    moveCamera(camera, controls, 'out'); close(camera.position, original);
  });
  it.each(['left', 'right'] as const)('%s rotates repeatedly at constant distance and elevation', action => {
    const {camera, controls} = setup(); const original = camera.position.clone(); const target = controls.target.clone();
    for (let i=0; i<24; i++) {
      moveCamera(camera, controls, action);
      expect(camera.position.distanceTo(target)).toBeCloseTo(original.distanceTo(target), 8);
      expect(camera.position.y).toBeCloseTo(original.y, 8); close(controls.target, target);
    }
    expect(camera.position.distanceTo(original)).toBeGreaterThan(10);
    for (let i=0; i<24; i++) moveCamera(camera, controls, action === 'left' ? 'right' : 'left');
    close(camera.position, original);
  });
  it('clamps repeated zoom in and out to finite useful distances', () => {
    const {camera, controls} = setup();
    for (let i=0; i<100; i++) moveCamera(camera, controls, 'in');
    expect(camera.position.distanceTo(controls.target)).toBeCloseTo(120, 8);
    for (let i=0; i<100; i++) moveCamera(camera, controls, 'out');
    expect(camera.position.distanceTo(controls.target)).toBeCloseTo(1200, 8);
  });
  it('pans along screen horizontal without changing orientation or zoom, and reverses', () => {
    const {camera, controls} = setup(); const original = camera.position.clone(); const target = controls.target.clone();
    const rotation = camera.quaternion.clone(); const right = new Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
    moveCamera(camera, controls, 'pan-left');
    const delta = camera.position.clone().sub(original);
    expect(delta.dot(right)).toBeLessThan(0); close(controls.target.clone().sub(target), delta);
    expect(camera.quaternion.angleTo(rotation)).toBeLessThan(1e-7);
    moveCamera(camera, controls, 'pan-right'); close(camera.position, original); close(controls.target, target);
  });
  it('pans by the same fraction of visible width at different zoom levels', () => {
    const a = setup(), b = setup(); moveCamera(b.camera, b.controls, 'out');
    const startA = a.camera.position.clone(), startB = b.camera.position.clone();
    moveCamera(a.camera, a.controls, 'pan-right'); moveCamera(b.camera, b.controls, 'pan-right');
    expect(b.camera.position.distanceTo(startB) / a.camera.position.distanceTo(startA)).toBeCloseTo(1.25, 8);
  });
});

describe('source orthographic camera', () => {
  const input = {projection:'orthographic',right:[.8,0,.6],up:[.3,Math.sqrt(.75),-.4],target_ldu:[5,5,10],vertical_span_ldu:180,image_size:[1200,900]};
  it.each([[1000,700],[390,700],[1200,900]])('preserves full-page landmark positions in a %sx%s canvas', (width,height) => {
    const before = structuredClone(input), view = createSourceCamera(input,width,height);
    const point = new Vector3(-20,8,40), delta = point.clone().sub(new Vector3().fromArray(input.target_ldu));
    const expectedU = .5+delta.dot(new Vector3().fromArray(input.right))/(180*1200/900);
    const expectedV = .5-delta.dot(new Vector3().fromArray(input.up))/180;
    const ndc = point.clone().project(view.camera), rect = view.sourceRect;
    expect(((ndc.x+1)*width/2-rect.x)/rect.width).toBeCloseTo(expectedU,10);
    expect(((1-ndc.y)*height/2-rect.y)/rect.height).toBeCloseTo(expectedV,10);
    expect(rect.width/rect.height).toBeCloseTo(1200/900,10);
    expect(input).toEqual(before);
    expect(inspectSourceCamera(view).projection_matrix).toEqual(view.camera.projectionMatrix.toArray());
  });
  it('records actual matrices and does not confuse camera movement with world placement', () => {
    const view = createSourceCamera(input,1200,900), before = inspectSourceCamera(view);
    view.camera.position.x += 10;
    const after = inspectSourceCamera(view);
    expect(after.input).toEqual(before.input);
    expect(after.matrix_world_inverse).not.toEqual(before.matrix_world_inverse);
    expect(after.position_ldu[0]-before.position_ldu[0]).toBeCloseTo(10,8);
  });
  it('rejects unknown fields, nonorthonormal axes, invalid dimensions and nonfinite inputs', () => {
    for(const patch of [{extra:true},{right:[2,0,0]},{up:[.8,0,.6]},{target_ldu:[NaN,0,0]},{vertical_span_ldu:0},{image_size:[10,900]}]) {
      expect(()=>validateSourceCamera({...input,...patch})).toThrow();
    }
    expect(()=>createSourceCamera(input,0,900)).toThrow();
    expect(()=>createSourceCamera(input,1200,900,Infinity)).toThrow();
  });
});
