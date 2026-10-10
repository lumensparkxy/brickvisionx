/** Sound effects for the fly-and-explode showpiece. Synthesized in the browser; silent when BrickBuddy's voice is off. */
import { isMuted } from './agent';

const STUNT_EVENT = 'brickvision:stunt';
let context: AudioContext | null = null;
let engine: { oscillator: OscillatorNode; gain: GainNode } | null = null;
function audio(): AudioContext {
  if (!context) context = new AudioContext();
  void context.resume().catch(() => undefined);
  return context;
}
function stopEngine(after = 0.05) {
  if (!engine || !context) return;
  const { oscillator, gain } = engine; engine = null;
  gain.gain.setTargetAtTime(0, context.currentTime, after / 3);
  oscillator.stop(context.currentTime + after + 0.3);
}
function play(phase: string) {
  if (phase === 'settled') return;
  if (isMuted()) { stopEngine(); return; }
  const ctx = audio(), now = ctx.currentTime;
  if (phase === 'takeoff') {
    stopEngine();
    const oscillator = ctx.createOscillator(), filter = ctx.createBiquadFilter(), gain = ctx.createGain();
    oscillator.type = 'sawtooth'; oscillator.frequency.setValueAtTime(48, now); oscillator.frequency.exponentialRampToValueAtTime(96, now + 1.4);
    filter.type = 'lowpass'; filter.frequency.value = 520;
    gain.gain.setValueAtTime(0, now); gain.gain.linearRampToValueAtTime(0.07, now + 0.6);
    oscillator.connect(filter).connect(gain).connect(ctx.destination); oscillator.start();
    engine = { oscillator, gain };
    window.setTimeout(() => stopEngine(), 9000); // Never leave the engine running if the stunt is interrupted.
  } else if (phase === 'dive' && engine) {
    engine.oscillator.frequency.cancelScheduledValues(now); engine.oscillator.frequency.setValueAtTime(engine.oscillator.frequency.value, now);
    engine.oscillator.frequency.exponentialRampToValueAtTime(300, now + 1); engine.gain.gain.linearRampToValueAtTime(0.11, now + 0.9);
  } else if (phase === 'impact') {
    stopEngine(0.02);
    const length = Math.floor(ctx.sampleRate * 1.6), buffer = ctx.createBuffer(1, length, ctx.sampleRate), data = buffer.getChannelData(0);
    for (let i = 0; i < length; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, 2);
    const noise = ctx.createBufferSource(), filter = ctx.createBiquadFilter(), gain = ctx.createGain();
    noise.buffer = buffer; filter.type = 'lowpass'; filter.frequency.setValueAtTime(1400, now); filter.frequency.exponentialRampToValueAtTime(70, now + 1.3);
    gain.gain.setValueAtTime(0.55, now); gain.gain.exponentialRampToValueAtTime(0.001, now + 1.5);
    noise.connect(filter).connect(gain).connect(ctx.destination); noise.start();
    const thump = ctx.createOscillator(), thumpGain = ctx.createGain();
    thump.frequency.setValueAtTime(110, now); thump.frequency.exponentialRampToValueAtTime(32, now + 0.5);
    thumpGain.gain.setValueAtTime(0.5, now); thumpGain.gain.exponentialRampToValueAtTime(0.001, now + 0.7);
    thump.connect(thumpGain).connect(ctx.destination); thump.start(); thump.stop(now + 0.8);
  }
}
// Installed once, even across dev-server hot updates.
const scope = globalThis as { __brickvisionStuntSound?: (event: Event) => void };
if (typeof window !== 'undefined') {
  if (scope.__brickvisionStuntSound) window.removeEventListener(STUNT_EVENT, scope.__brickvisionStuntSound);
  scope.__brickvisionStuntSound = event => play((event as CustomEvent<string>).detail);
  window.addEventListener(STUNT_EVENT, scope.__brickvisionStuntSound);
}
