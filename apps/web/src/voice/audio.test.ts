import { describe, expect, it } from 'vitest';
import { ChunkBuffer, STT_CHUNK_SAMPLES, TurnDetector, base64ToPcm16, bytesToBase64, floatToPcm16, pcm16ToFloat } from './audio';

const step = (prob: number) => ({vad: [{horizon_s: 0.5, inactivity_prob: prob}, {horizon_s: 1, inactivity_prob: prob}, {horizon_s: 2, inactivity_prob: 0}]});

describe('voice audio helpers', () => {
  it('clamps float samples into signed 16-bit PCM and back', () => {
    const pcm = floatToPcm16(new Float32Array([-2, -1, 0, 0.5, 1, 2]));
    expect(Array.from(pcm)).toEqual([-32768, -32768, 0, 16383, 32767, 32767]);
    expect(pcm16ToFloat(pcm)[0]).toBe(-1);
  });

  it('round-trips PCM through base64', () => {
    const pcm = new Int16Array([1, -2, 300, -32768]);
    expect(Array.from(base64ToPcm16(bytesToBase64(new Uint8Array(pcm.buffer))))).toEqual([1, -2, 300, -32768]);
  });

  it('emits fixed 80 ms chunks from 128-sample worklet blocks', () => {
    const buffer = new ChunkBuffer();
    const chunks = Array.from({length: 30}, () => buffer.push(new Int16Array(128).fill(7))).flat();
    expect(chunks).toHaveLength(Math.floor(30 * 128 / STT_CHUNK_SAMPLES));
    expect(chunks[0]).toHaveLength(STT_CHUNK_SAMPLES);
  });

  it('ends a turn only after consecutive confident steps with speech', () => {
    const detector = new TurnDetector(0.6, 3, 1);
    expect(detector.update(step(0.9), true)).toBe(false);
    expect(detector.update(step(0.2), true)).toBe(false);
    expect([step(0.9), step(0.9), step(0.9)].map(item => detector.update(item, true))).toEqual([false, false, true]);
    expect([step(0.9), step(0.9), step(0.9)].map(item => detector.update(item, false))).toEqual([false, false, false]);
  });
});
