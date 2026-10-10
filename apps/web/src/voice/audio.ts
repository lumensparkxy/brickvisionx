export const STT_SAMPLE_RATE = 24000;
export const STT_CHUNK_SAMPLES = 1920;

export function floatToPcm16(samples: Float32Array): Int16Array {
  const pcm = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    pcm[i] = sample < 0 ? sample * 32768 : sample * 32767;
  }
  return pcm;
}

export function pcm16ToFloat(pcm: Int16Array): Float32Array {
  const samples = new Float32Array(pcm.length);
  for (let i = 0; i < pcm.length; i += 1) samples[i] = pcm[i] / 32768;
  return samples;
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

export function base64ToPcm16(value: string): Int16Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length & ~1);
  for (let i = 0; i < bytes.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new Int16Array(bytes.buffer);
}

/** Collects 128-sample worklet blocks into fixed 80 ms PCM16 chunks. */
export class ChunkBuffer {
  private pending = new Int16Array(STT_CHUNK_SAMPLES);
  private filled = 0;

  push(block: Int16Array): Int16Array[] {
    const out: Int16Array[] = [];
    let offset = 0;
    while (offset < block.length) {
      const take = Math.min(block.length - offset, STT_CHUNK_SAMPLES - this.filled);
      this.pending.set(block.subarray(offset, offset + take), this.filled);
      this.filled += take;
      offset += take;
      if (this.filled === STT_CHUNK_SAMPLES) {
        out.push(this.pending);
        this.pending = new Int16Array(STT_CHUNK_SAMPLES);
        this.filled = 0;
      }
    }
    return out;
  }
}

export interface VadStep { vad?: {horizon_s: number; inactivity_prob: number}[] }

/** Semantic-VAD end-of-turn rule: several consecutive confident steps at the 1 s horizon. */
export class TurnDetector {
  private streak = 0;
  constructor(private threshold = 0.6, private requiredSteps = 3, private horizonSeconds = 1) {}

  update(step: VadStep, hasSpeech: boolean): boolean {
    const horizon = step.vad?.find(item => item.horizon_s === this.horizonSeconds) ?? step.vad?.[step.vad.length - 1];
    this.streak = horizon && horizon.inactivity_prob > this.threshold ? this.streak + 1 : 0;
    if (hasSpeech && this.streak >= this.requiredSteps) {
      this.streak = 0;
      return true;
    }
    return false;
  }

  reset() { this.streak = 0; }
}
