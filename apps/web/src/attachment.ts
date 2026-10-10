import { Quaternion, Vector3 } from 'three';
import type { Pose, StepSnapshot } from './contracts';
// Derive one rigid transform from snapshots; never alter canonical poses or deform a group.
export function rigidAttachment(previous: StepSnapshot | undefined, next: StepSnapshot) {
  if (!previous || next.action !== 'attach_subassembly' || !next.active_instance_ids.length) return null;
  const anchor = next.active_instance_ids[0]; const start = previous.poses[anchor]; const end = next.poses[anchor];
  if (!start || !end) return null;
  const from = new Vector3().fromArray(start.position_ldu), to = new Vector3().fromArray(end.position_ldu);
  const delta = new Quaternion().fromArray(end.quaternion_xyzw).multiply(new Quaternion().fromArray(start.quaternion_xyzw).invert());
  for (const id of next.active_instance_ids) {
    const oldPose = previous.poses[id], newPose = next.poses[id]; if (!oldPose || !newPose) return null;
    const expected = new Vector3().fromArray(oldPose.position_ldu).sub(from).applyQuaternion(delta).add(to);
    const rotation = delta.clone().multiply(new Quaternion().fromArray(oldPose.quaternion_xyzw));
    if (expected.distanceTo(new Vector3().fromArray(newPose.position_ldu))>1e-4 || rotation.angleTo(new Quaternion().fromArray(newPose.quaternion_xyzw))>1e-4) return null;
  }
  return (id: string, t: number): Pose => {
    const old = previous.poses[id];const rotation = new Quaternion().slerp(delta,t);
    const position = new Vector3().fromArray(old.position_ldu).sub(from).applyQuaternion(rotation).add(from.clone().lerp(to,t));
    const orientation = rotation.multiply(new Quaternion().fromArray(old.quaternion_xyzw));
    return {position_ldu:position.toArray(),quaternion_xyzw:orientation.toArray()};
  };
}
