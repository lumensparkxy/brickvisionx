import { describe,it,expect } from 'vitest';
import { findingSteps,groupFindings,type Finding } from './review';
import type { SceneManifest } from './contracts';
const first:Finding={item_id:'one',kind:'part_mapping',message:'Check source',status:'open',instance_ids:['a'],step_ids:[],source:{page_index:1,bbox:[0,0,1,1],source_sha256:'a'.repeat(64)}};
describe('review finding presentation',()=>{
  it('groups repeated wording while retaining each identity and source record',()=>{
    const second={...first,item_id:'two',instance_ids:['b'],source:{...first.source,page_index:2}};
    const groups=groupFindings([first,second]);expect(groups).toHaveLength(1);expect(groups[0].items).toEqual([first,second]);
  });
  it('never merges distinct statuses or different evidence messages',()=>{
    expect(groupFindings([first,{...first,item_id:'two',status:'resolved'},{...first,item_id:'three',message:'Different uncertainty'}])).toHaveLength(3);
  });
  it('derives missing mapping step IDs from introduction, not later visibility',()=>{
    const scene={steps:[{step_id:'s1',introduced_instance_ids:['a'],visible_instance_ids:['a']},{step_id:'s2',introduced_instance_ids:['b'],visible_instance_ids:['a','b']}]} as unknown as SceneManifest;
    expect(findingSteps(first,scene).map(s=>s.step_id)).toEqual(['s1']);
    expect(findingSteps({...first,step_ids:['s2']},scene).map(s=>s.step_id)).toEqual(['s2']);
  });
});
