import { describe, expect, it } from 'vitest';
import fixture from '../../../tests/fixtures/synthetic.scene.json';
import {parseScene,parseSet} from './validation';
import {partsList} from './state';
import {parseJob,parseGuideStatus} from './api';
describe('runtime scene contract',()=>{
  it('validates the shared backend fixture and freezes snapshots',()=>{const scene=parseScene(fixture);expect(Object.isFrozen(scene.steps[0].poses)).toBe(true);expect(partsList(scene)[0].quantity).toBe(2);expect(partsList(scene,scene.steps[2].introduced_instance_ids)).toEqual([]);});
  it('rejects non-unit rotations, provenance mismatch and unseen instances',()=>{
    const bad=structuredClone(fixture);bad.steps[0].poses.a.quaternion_xyzw=[0,0,0,2];expect(()=>parseScene(bad)).toThrow('pose');
    const source=structuredClone(fixture);source.steps[0].source.source_sha256='0'.repeat(64);expect(()=>parseScene(source)).toThrow('source');
    const ids=structuredClone(fixture);ids.steps[0].active_instance_ids=['b'];expect(()=>parseScene(ids)).toThrow('visibility');
  });
  it('rejects unsafe geometry and command-like colour fields before rendering',()=>{const bad=structuredClone(fixture);bad.instances[0].geometry_ref='parts/../escape.dat';expect(()=>parseScene(bad)).toThrow();bad.instances[0].geometry_ref='parts/a.dat';bad.instances[0].color_code='4\n1';expect(()=>parseScene(bad)).toThrow();});
  it('rejects duplicate introductions and missing snapshots',()=>{const bad=structuredClone(fixture);bad.steps[2].introduced_instance_ids=['a'];expect(()=>parseScene(bad)).toThrow('twice');expect(()=>parseScene({...fixture,steps:[]})).toThrow();});
  it('rejects non-official source links',()=>{expect(()=>parseSet({set_number:'30669',name:'Example',official_page:'javascript:alert(1)',guides:[]})).toThrow();});
  it('preserves unknown instruction counts and defaults absent tutorial availability to false',()=>{
    const source={set_number:'10316',name:'Rivendell',official_page:'https://www.lego.com/en-us/service/building-instructions/10316',guides:[{guide_id:'booklet-01',label:'Official booklet 1 of 3',pdf_url:'https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6455635.pdf',expected_main_steps:null}]};
    expect(parseSet(source).guides[0]).toMatchObject({expected_main_steps:null,tutorial_available:false});
    expect(parseSet({...source,guides:[{...source.guides[0],expected_main_steps:12,tutorial_available:true}]}).guides[0].tutorial_available).toBe(true);
    for (const change of [{expected_main_steps:0},{expected_main_steps:-1},{expected_main_steps:'unknown'},{tutorial_available:'true'}]) expect(()=>parseSet({...source,guides:[{...source.guides[0],...change}]})).toThrow('invalid set');
  });
  it('requires a consistent public alpha availability status and preserves legacy guide metadata',()=>{
    const guide={guide_id:'synthetic',label:'Synthetic transport fixture',pdf_url:'https://www.lego.com/test.pdf',expected_main_steps:null,tutorial_available:true};
    const source={set_number:'99999',name:'Synthetic transport fixture',official_page:'https://www.lego.com/',guides:[guide]};
    const alpha={...guide,release_kind:'unverified_alpha',alpha_available:true,status:'alpha_unverified'};
    expect(parseSet({...source,guides:[alpha]},true).guides[0]).toMatchObject(alpha);
    expect(parseSet(source,true).guides[0]).not.toHaveProperty('release_kind');
    for(const change of [{release_kind:'reviewed'},{status:'published'},{tutorial_available:false},{alpha_available:false},{alpha_available:'true'}])
      expect(()=>parseSet({...source,guides:[{...alpha,...change}]},true)).toThrow('invalid alpha');
    for(const change of [{status:'alpha_unverified'},{alpha_available:true}])
      expect(()=>parseSet({...source,guides:[{...guide,...change}]},true)).toThrow('invalid alpha');
  });
});

describe('runtime processing contracts',()=>{
  const job={job_id:'job',state:'failed',stage:'fetching',completed_units:0,total_units:null,attempts:1,output_revision:null,source_sha256:null,error:{code:'interrupted',message:'Interrupted'}};
  it('rejects object error messages that cannot render safely',()=>{expect(parseJob(job).error).toEqual(job.error);expect(()=>parseJob({...job,error:{code:'bad',message:{unexpected:true}}})).toThrow('Invalid processing');});
  it('rejects invalid counters, states, source hashes and status pointers',()=>{for(const change of [{attempts:-1},{total_units:NaN},{state:'made_up'},{source_sha256:'wrong'}])expect(()=>parseJob({...job,...change})).toThrow();expect(()=>parseGuideStatus({source_available:true,job:null,latest_candidate_revision:{bad:true},latest_reviewed_revision:null})).toThrow();});
});
