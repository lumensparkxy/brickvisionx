import { describe, expect, it } from 'vitest';
import { clampStep, progressKey } from './state';
import type { SceneManifest } from './contracts';
describe('instruction state', () => {
  it('bounds seek positions', () => { expect(clampStep(-4, 12)).toBe(0); expect(clampStep(100, 12)).toBe(11); });
  it('rejects nonfinite storage values', () => { expect(clampStep(NaN, 12)).toBe(0); });
  it('scopes progress to source and revision', () => {
    const scene = { set_number: '99999', guide_id: 'synthetic', source_sha256: 'a'.repeat(64), revision: 'r1' } as SceneManifest;
    expect(progressKey(scene)).not.toBe(progressKey({ ...scene, revision: 'r2' }));
  });
});
