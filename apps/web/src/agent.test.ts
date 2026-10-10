import { describe, expect, it } from 'vitest';
import { describeAction, parseActions } from './agent';

describe('viewer actions from model output', () => {
  it('keeps well-formed actions and coerces their numbers', () => {
    expect(parseActions([
      { type: 'go_to_step', step: '5' },
      { type: 'play_steps', step: 6, count: 3, narrations: ['a', 2, 'b'] },
      { type: 'rotate', direction: 'left', degrees: -180 },
      { type: 'zoom', direction: 'in' }, { type: 'reset_view' }, { type: 'stop' },
    ])).toEqual([
      { type: 'go_to_step', step: 5 },
      { type: 'play_steps', step: 6, count: 3, narrations: ['a', 'b'] },
      { type: 'rotate', direction: 'left', degrees: 180 },
      { type: 'zoom', direction: 'in' }, { type: 'reset_view' }, { type: 'stop' },
    ]);
  });
  it('drops unknown or malformed actions and bounds the rest', () => {
    expect(parseActions('rotate')).toEqual([]);
    expect(parseActions([null, { type: 'delete_everything' }, { type: 'rotate', direction: 'sideways', degrees: 90 }, { type: 'zoom', direction: 'up' }])).toEqual([]);
    expect(parseActions([{ type: 'play_steps', step: 1, count: 999 }])).toEqual([{ type: 'play_steps', step: 1, count: 12, narrations: [] }]);
    expect(parseActions([{ type: 'rotate', direction: 'right', degrees: 99999 }])).toEqual([{ type: 'rotate', direction: 'right', degrees: 720 }]);
    expect(parseActions([{ type: 'rotate', direction: 'up' }])).toEqual([{ type: 'rotate', direction: 'up', degrees: 90 }]);
  });
  it('accepts app-level actions only with catalogue-shaped identifiers', () => {
    expect(parseActions([
      { type: 'open_tutorial', set_number: '30669', guide_id: 'alt-02' }, { type: 'open_tutorial', set_number: '31134', guide_id: 'Not OK!' },
      { type: 'find_set', set_number: '60400' }, { type: 'go_home' }, { type: 'close_booklet' },
      { type: 'find_set', set_number: 'plane' }, { type: 'open_tutorial' }, { type: 'click', control_id: 'c1' },
    ])).toEqual([
      { type: 'open_tutorial', set_number: '30669', guide_id: 'alt-02' }, { type: 'open_tutorial', set_number: '31134' },
      { type: 'find_set', set_number: '60400' }, { type: 'go_home' }, { type: 'close_booklet' },
    ]);
  });
  it('labels actions for the chat chips', () => {
    expect(describeAction({ type: 'open_tutorial', set_number: '30669' })).toBe('▶ Open 30669');
    expect(describeAction({ type: 'play_steps', step: 6, count: 3, narrations: [] })).toBe('▶ Steps 6–8');
    expect(describeAction({ type: 'go_to_step', step: 5 })).toBe('→ Step 5');
  });
});
