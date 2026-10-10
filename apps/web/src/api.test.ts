import { describe, expect, it } from 'vitest';
import { parseEnginePreviews, parseImageQuality, previewCoverageText, previewForGuide, withPreviewAvailability } from './api';

const alpha = {profile:'alpha', max_rms_pixels:8, max_point_pixels:12, strict_max_rms_pixels:4,
  relaxed_steps:[{step_id:'sample', rms_pixels:7.76, max_error_pixels:9.86}]};

describe('image quality status', () => {
  it('retains measured alpha errors for the unverified sample label', () => {
    expect(parseImageQuality(alpha)).toEqual(alpha);
    expect(parseImageQuality({...alpha, profile:'strict', relaxed_steps:[]}).profile).toBe('strict');
  });
  it('rejects unknown profiles and invalid measurements', () => {
    for (const value of [null, {...alpha, profile:'approved'}, {...alpha, max_rms_pixels:Infinity},
      {...alpha, relaxed_steps:[{step_id:'sample', rms_pixels:NaN, max_error_pixels:9.86}]}]) {
      expect(() => parseImageQuality(value)).toThrow('Invalid image-quality');
    }
  });
});

const first = {job_id:'a'.repeat(32), set_number:'30669', guide_id:'alt-02', state:'paused', stage:'alpha_complete',
  revision:'alpha-first', experiment_revision:'campaign-01', completed_panels:12, total_panels:12,
  instance_count:32, step_count:16, candidate_available:true, candidate_message:null, error:null,
  generation_mode:'alpha_fast', completed_pages:8, page_count:8, uncertainty_notes:['Transparent colour needs review.'], image_quality:alpha};
const second = {...first, job_id:'b'.repeat(32), guide_id:'alt-01', revision:null, candidate_available:false, step_count:0, instance_count:0};
const third = {...first, job_id:'c'.repeat(32), set_number:'60400', guide_id:'booklet-01', revision:'other-set'};

describe('campaign preview identity and coverage', () => {
  it('distinguishes source processing from available reconstruction in exploration', () => {
    const exploration={processed_panels:3,reconstructed_panels:2,model_calls_used:7,max_model_calls:100,instructions:[
      {ordinal:1,main_step_number:2,page_index:1,step_ids:[],reconstructed:false,finding_count:1,
       findings:[{category:'source_view',message:'No renderable proposal.',instance_ids:[],step_ids:[]}]}]};
    const preview=parseEnginePreviews({...first,generation_mode:'standard',execution_policy:'explore',exploration})[0];
    expect(previewCoverageText(preview)).toContain('3 of 12 instructions processed · 2 reconstructed');
    expect(preview.exploration?.instructions[0].reconstructed).toBe(false);
    for(const bad of [{...exploration,reconstructed_panels:4},{...exploration,model_calls_used:-1},
      {...exploration,instructions:[{...exploration.instructions[0],needs_recheck:'yes'}]},
      {...exploration,instructions:[{...exploration.instructions[0],findings:[{message:123}]}]}]) {
      expect(()=>parseEnginePreviews({...first,execution_policy:'explore',exploration:bad})).toThrow('Invalid exploration');
    }
  });
  it('supports a single preview and preserves separate campaign jobs', () => {
    expect(parseEnginePreviews(first)).toEqual([first]);
    const values = parseEnginePreviews({candidates:[first,second,third]});
    expect(previewForGuide(values,'30669','alt-02','alpha-first')?.job_id).toBe(first.job_id);
    expect(previewForGuide(values,'30669','alt-01')?.candidate_available).toBe(false);
    expect(previewForGuide(values,'30669','alt-02','older-revision')).toBeUndefined();
    expect(previewForGuide(values,'60400','booklet-01')?.revision).toBe('other-set');
  });
  it('updates availability only for the matching set and guide', () => {
    const info = {set_number:'30669',name:'Synthetic transport only',official_page:'https://www.lego.com',guides:[
      {guide_id:'alt-02',label:'First',pdf_url:'https://www.lego.com/test.pdf',expected_main_steps:12,tutorial_available:false},
      {guide_id:'alt-01',label:'Second',pdf_url:'https://www.lego.com/test.pdf',expected_main_steps:null,tutorial_available:false},
      {guide_id:'main',label:'Unselected',pdf_url:'https://www.lego.com/test.pdf',expected_main_steps:null,tutorial_available:false}]};
    const values = parseEnginePreviews({candidates:[first,second,third]});
    const updated = withPreviewAvailability(info,values);
    expect(updated.guides.map(guide=>guide.tutorial_available)).toEqual([true,false,false]);
    expect(info.guides.every(guide=>!guide.tutorial_available)).toBe(true);
    expect(withPreviewAvailability({...info,set_number:'99999'},values).guides.every(guide=>!guide.tutorial_available)).toBe(true);
  });
  it('describes fast alpha page coverage without inferring complete instructions', () => {
    const fast = parseEnginePreviews(first)[0];
    expect(previewCoverageText(fast)).toBe('8 of 8 source pages processed · 16 candidate instructions · 32 physical pieces');
    expect(fast.uncertainty_notes).toEqual(['Transparent colour needs review.']);
    expect(previewCoverageText({...fast,generation_mode:'standard'})).toContain('12 of 12 source panels');
  });
  it('rejects mixed identities, duplicate guides and malformed notes', () => {
    for (const value of [null, {candidates:[]}, {...first,guide_id:undefined}, {...first,completed_pages:-1},
      {...first,uncertainty_notes:[{}]}, {...first,error:[]}, {candidates:[first,first]}]) {
      expect(()=>parseEnginePreviews(value)).toThrow();
    }
  });
});
