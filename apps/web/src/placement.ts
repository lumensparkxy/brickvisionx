import { Box3, Quaternion, Vector3 } from 'three';
import evidence from '../../../config/placement-30669-alt-02-v3.json';
import type { SceneManifest, StepSnapshot } from './contracts';
export interface PlacementPlan { mode:'translate'|'highlight'; offset:Vector3; reason:string; }
export interface ReplayPlan { mode:'translate'|'preview'|'highlight'; offset:Vector3; reason:string; }

/** A camera-relative visual entrance, not an inferred physical attachment path.
 * Keep source-bound approaches and their collision guard independent from this effect.
 * One shared offset preserves the relative poses of an active subassembly.
 */
export function replayPlan(approach:PlacementPlan, cameraRotation:Quaternion, viewHeight:number):ReplayPlan {
  if(approach.mode==='translate')return approach;
  return {mode:'preview',offset:new Vector3(0,Math.max(8,viewHeight*.18),0).applyQuaternion(cameraRotation),reason:'visual_preview'};
}

/** Authored presentation hints are scoped to exact source, revision, step and active identities. */
export function approachFor(scene:SceneManifest, step:StepSnapshot):PlacementPlan {
  const item=evidence.steps.find(item=>item.step_id===step.step_id);
  if(scene.source_sha256!==evidence.source_sha256 || scene.revision!==evidence.revision || !item ||
    (item.source.page_index!==step.source.page_index || item.source.source_sha256!==step.source.source_sha256 || item.source.bbox.some((value,i)=>value!==step.source.bbox[i])) ||
    item.instance_ids.length!==step.active_instance_ids.length || !item.instance_ids.every(id=>step.active_instance_ids.includes(id)))
    return {mode:'highlight',offset:new Vector3(),reason:'unreviewed_direction'};
  if(item.approach==='highlight')return {mode:'highlight',offset:new Vector3(),reason:'starting_pieces'};
  return {mode:'translate',offset:new Vector3(0,item.approach==='below'?-evidence.distance_ldu:evidence.distance_ldu,0),reason:item.approach};
}

/** Broad-phase guard, NOT connector/narrow-phase validation.
 * A straight axis-aligned approach may only intersect an obstacle inside its existing final
 * contact envelope. Reject extra swept overlap, even if a mesh-shaped cavity might allow it.
 */
export function approachIsClear(moving:Box3[], obstacles:Box3[], offset:Vector3):boolean {
  if(offset.toArray().filter(n=>Math.abs(n)>1e-8).length!==1)return false;
  return moving.every(end=>obstacles.every(obstacle=>{
    const swept=end.clone().union(end.clone().translate(offset));
    const crossing=swept.intersect(obstacle);
    if(crossing.isEmpty())return true;
    const contact=end.clone().intersect(obstacle);
    return !contact.isEmpty() && contact.expandByScalar(1e-5).containsBox(crossing);
  }));
}
export function checkedApproach(plan:PlacementPlan,moving:Box3[],obstacles:Box3[]):PlacementPlan {
  return plan.mode==='translate' && !approachIsClear(moving,obstacles,plan.offset)
    ? {mode:'highlight',offset:new Vector3(),reason:'blocked_approach'} : plan;
}
