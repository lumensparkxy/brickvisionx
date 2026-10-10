import {describe,it,expect} from 'vitest';
import {rigidAttachment} from './attachment';
import type {StepSnapshot} from './contracts';
describe('rigid subassembly replay',()=>{
  const before={poses:{a:{position_ldu:[0,0,0],quaternion_xyzw:[0,0,0,1]},b:{position_ldu:[20,0,0],quaternion_xyzw:[0,0,0,1]}}} as unknown as StepSnapshot;
  const after={action:'attach_subassembly',active_instance_ids:['a','b'],poses:{a:{position_ldu:[100,0,0],quaternion_xyzw:[0,Math.SQRT1_2,0,Math.SQRT1_2]},b:{position_ldu:[100,0,-20],quaternion_xyzw:[0,Math.SQRT1_2,0,Math.SQRT1_2]}}} as unknown as StepSnapshot;
  it('keeps physical separation through rotation and translation',()=>{const motion=rigidAttachment(before,after)!;expect(motion).toBeTruthy();for(const t of [0,.25,.5,.75,1]){const a=motion('a',t).position_ldu,b=motion('b',t).position_ldu;expect(Math.hypot(...a.map((n,i)=>n-b[i]))).toBeCloseTo(20,8);}expect(motion('b',1).position_ldu[2]).toBeCloseTo(-20);});
  it('declines a distorted attachment rather than inventing rigid motion',()=>{const distorted=structuredClone(after);distorted.poses.b.position_ldu=[100,0,-30];expect(rigidAttachment(before,distorted)).toBeNull();});
});
