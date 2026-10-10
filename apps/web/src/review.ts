import type { SceneManifest, SourcePanel, StepSnapshot } from './contracts';
export interface Finding { item_id: string; kind: string; message: string; instance_ids: string[]; step_ids: string[]; source: SourcePanel; status: string; }
export function findingSteps(item: Finding, scene: SceneManifest): StepSnapshot[] {
  if (item.step_ids.length) return scene.steps.filter(step => item.step_ids.includes(step.step_id));
  return scene.steps.filter(step => step.introduced_instance_ids.some(id => item.instance_ids.includes(id)));
}
export function groupFindings(items: Finding[]) {
  const groups = new Map<string, {key:string; kind:string; message:string; status:string; items:Finding[]}>();
  for (const item of items) {
    const key = JSON.stringify([item.kind,item.message,item.status]);
    if (!groups.has(key)) groups.set(key,{key,kind:item.kind,message:item.message,status:item.status,items:[]});
    groups.get(key)!.items.push(item);
  }
  return [...groups.values()];
}
export const findingTitle: Record<string,string> = {
  part_mapping:'Part identity checks', occluded_connection:'Hidden connections', pose_ambiguity:'Position or orientation',
  ambiguous_colour:'Uncertain colour', part_variant:'Part variant', assembly_review:'Whole assembly review',
};
