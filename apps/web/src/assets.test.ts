import { afterEach, describe, expect, it, vi } from 'vitest';
import { modelAssetUrl } from './assets';

afterEach(() => vi.unstubAllGlobals());
describe('published asset cache version', () => {
  it('refreshes storage chunks, provenance, colours and nested individual parts consistently', () => {
    vi.stubGlobal('location', {origin: 'https://portal.example'});
    for (const path of ['chunks/00000.json', 'ldraw/provenance.json', 'ldraw/LDConfig.ldr', 'ldraw/parts/s/part.dat', 'ldraw/p/primitive.dat']) {
      const original = new URL(`https://storage.googleapis.com/synthetic-assets/synthetic-release/${path}`);
      const result = modelAssetUrl(original);
      expect(result.pathname).toBe(original.pathname);
      expect(result.search).toBe('?g2b-transport=2');
      expect(modelAssetUrl(result).href).toBe(result.href);
      expect(original.search).toBe('');
    }
  });
  it('preserves local and other origins without adding a cache version', () => {
    vi.stubGlobal('location', {origin: 'http://127.0.0.1:5173'});
    for (const value of ['/assets-local/ldraw/parts/part.dat', '/published-assets/synthetic/chunks/0.json',
      'https://www.lego.com/booklet.pdf', 'https://storage.googleapis.com.evil.example/part.dat']) {
      expect(modelAssetUrl(value).href).toBe(new URL(value, location.origin).href);
    }
  });
});
