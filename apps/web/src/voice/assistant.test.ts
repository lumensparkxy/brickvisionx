import { describe, expect, it } from 'vitest';
import { parseAction, stepIndexFor } from './assistant';

describe('assistant navigation actions', () => {
  it('keeps well-formed actions and only their fields', () => {
    expect(parseAction({type: 'find_set', set_number: '60400', step: 3})).toEqual({type: 'find_set', set_number: '60400'});
    expect(parseAction({type: 'open_tutorial', set_number: '30669', guide_id: 'alt-02'})).toEqual({type: 'open_tutorial', set_number: '30669', guide_id: 'alt-02'});
    expect(parseAction({type: 'open_tutorial', set_number: '30669'})).toEqual({type: 'open_tutorial', set_number: '30669'});
    expect(parseAction({type: 'go_to_step', step: 4})).toEqual({type: 'go_to_step', step: 4});
    expect(parseAction({type: 'next_step', set_number: '1'})).toEqual({type: 'next_step'});
    expect(parseAction({type: 'click', control_id: 'c12', step: 2})).toEqual({type: 'click', control_id: 'c12'});
  });

  it('refuses click ids that are not control ids', () => {
    for (const control_id of [undefined, 12, '#prepare', 'c1234', 'button.next']) expect(parseAction({type: 'click', control_id})).toEqual({type: 'none'});
  });

  it('turns malformed or unknown actions into none', () => {
    for (const value of [null, 'go_home', {}, {type: 'delete_everything'}, {type: 'find_set', set_number: 'abc'},
      {type: 'find_set'}, {type: 'go_to_step', step: 0}, {type: 'go_to_step', step: 2.5},
      {type: 'open_tutorial', set_number: '30669', guide_id: '../x'}]) {
      expect(parseAction(value).type === 'none' || (value as {guide_id?: string})?.guide_id === '../x').toBe(true);
    }
    expect(parseAction({type: 'open_tutorial', set_number: '30669', guide_id: '../x'})).toEqual({type: 'open_tutorial', set_number: '30669'});
  });

  it('maps a printed step number to its first instruction', () => {
    const steps = [{main_step_number: null}, {main_step_number: 1}, {main_step_number: 1}, {main_step_number: 2}];
    expect(stepIndexFor(steps, 1)).toBe(1);
    expect(stepIndexFor(steps, 2)).toBe(3);
    expect(stepIndexFor(steps, 7)).toBe(-1);
  });
});
