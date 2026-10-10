/**
 * Gradium voice for BrickBuddy: streaming text-to-speech and tap-to-talk speech-to-text.
 * The browser only ever holds a single-use token minted by our backend, never the API key.
 */
import { post } from './api';
import type { VoiceAdapter } from './agent';

/** End of turn: Gradium's 2 s-horizon inactivity probability must stay above the threshold this many steps (80 ms each) in a row. */
export const VAD_THRESHOLD = 0.6;
export const VAD_CONSECUTIVE_STEPS = 4;
/** Hard cap on one utterance. */
export const MAX_LISTEN_MS = 30000;
/** If nothing was transcribed after this long and the input is flat, stop and say so. */
const DEAF_CHECK_MS = 6000;
const SILENCE_PEAK = 0.003;
const VIRTUAL_INPUT = /hue sync|teams|zoom|blackhole|loopback|soundflower|virtual|aggregate|multi-output|krisp|obs/i;

const TTS_URL = 'wss://api.gradium.ai/api/speech/tts';
const STT_URL = 'wss://api.gradium.ai/api/speech/asr';
const TTS_RATE = 48000; // output_format "pcm": 48 kHz, 16-bit, mono
const STT_RATE = 24000; // input_format "pcm": 24 kHz, 16-bit, mono
const CHUNK_SAMPLES = 1920; // 80 ms at 24 kHz
const SCHEDULE_AHEAD_S = 0.06;
const FLUSH_TIMEOUT_MS = 2500; // how long to wait for the last words after end_of_stream
const MAX_BACKLOG_CHUNKS = 50; // audio captured while the token and socket are still on their way (4 s)

/** Gradium cannot be used at all (not configured, token rejected, unreachable): callers should fall back. */
export class VoiceUnavailable extends Error {
  constructor(message = 'Voice is not available right now.') { super(message); this.name = 'VoiceUnavailable'; }
}

interface VoiceToken { token: string; voice_id: string; }
interface TtsMessage { type?: string; audio?: string; sample_rate?: number; message?: string; }
interface SttMessage { type?: string; text?: string; message?: string; vad?: { inactivity_prob?: number }[]; }

/** One single-use token per WebSocket connection. It expires within seconds: mint it right before connecting, never cache it. */
async function getToken(): Promise<VoiceToken> {
  try {
    const body = await post<VoiceToken>('/voice/token');
    if (typeof body?.token !== 'string' || !body.token) throw new Error('The voice service returned no token.');
    return body;
  } catch (error) {
    throw new VoiceUnavailable(error instanceof Error ? error.message : undefined);
  }
}
const openSocket = (url: string, token: string) => new WebSocket(`${url}?token=${encodeURIComponent(token)}`);
function send(socket: WebSocket | null, message: object) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
}
function closeSocket(socket: WebSocket | null) {
  if (!socket) return;
  socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null;
  try { socket.close(); } catch { /* Already closed. */ }
}
/** Server frames are untrusted JSON: anything unreadable becomes an empty message. */
function parse<T extends object>(data: unknown): T {
  try { const value: unknown = JSON.parse(String(data)); if (value && typeof value === 'object') return value as T; } catch { /* Not JSON. */ }
  return {} as T;
}

/** base64 of 16-bit signed little-endian PCM -> float samples. */
function decodePcm16(base64: string): Float32Array {
  const binary = atob(base64);
  const samples = new Float32Array(binary.length >> 1);
  for (let i = 0; i < samples.length; i++) {
    const value = binary.charCodeAt(2 * i) | (binary.charCodeAt(2 * i + 1) << 8);
    samples[i] = (value > 0x7fff ? value - 0x10000 : value) / 32768;
  }
  return samples;
}
/** Float samples -> base64 of 16-bit signed little-endian PCM. */
function encodePcm16(samples: Float32Array): string {
  const bytes = new Uint8Array(samples.length * 2);
  const view = new DataView(bytes.buffer);
  for (let i = 0; i < samples.length; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(i * 2, sample < 0 ? sample * 32768 : sample * 32767, true);
  }
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}
/** Streaming linear resampler: it carries its read position across blocks, so nothing is dropped at block edges. */
function createResampler(fromRate: number, toRate: number): (input: Float32Array) => Float32Array {
  const step = fromRate / toRate;
  let position = 0; // Read position in the next block; -1 is the last sample of the previous block.
  let previous = 0;
  return input => {
    if (step === 1 || input.length === 0) return input;
    const output: number[] = [];
    for (; position < input.length - 1; position += step) {
      const index = Math.floor(position);
      const before = index < 0 ? previous : input[index];
      output.push(before + (input[index + 1] - before) * (position - index));
    }
    previous = input[input.length - 1];
    position -= input.length;
    return Float32Array.from(output);
  };
}

// ---------------------------------------------------------------- text to speech
let player: AudioContext | null = null;
/** One shared output context, created lazily at the voice's own rate so chunks join without resampling seams. */
function playerContext(): AudioContext {
  if (!player) { try { player = new AudioContext({ sampleRate: TTS_RATE }); } catch { player = new AudioContext(); } }
  void player.resume().catch(() => undefined);
  return player;
}
// Browsers only let audio start after a user gesture, so wake the output on the first one.
if (typeof window !== 'undefined') {
  for (const gesture of ['click', 'keydown']) window.addEventListener(gesture, () => { playerContext(); }, { once: true, capture: true });
}

let stopSpeech: (() => void) | null = null;

function speak(text: string): Promise<void> {
  stop();
  return new Promise<void>((resolve, reject) => {
    const sources = new Set<AudioBufferSourceNode>();
    let socket: WebSocket | null = null;
    let sampleRate = TTS_RATE, playhead = 0, timer = 0;
    let started = false, ended = false, settled = false;

    const settle = (error?: Error) => {
      if (settled) return;
      settled = true; window.clearTimeout(timer);
      if (stopSpeech === halt) stopSpeech = null;
      closeSocket(socket); socket = null;
      if (error) reject(error); else resolve();
    };
    const halt = () => {
      sources.forEach(source => { try { source.stop(); } catch { /* Already ended. */ } });
      sources.clear(); settle();
    };
    // The stream is over: resolve once everything that was scheduled has actually been heard.
    const finish = () => {
      if (ended || settled) return;
      ended = true; closeSocket(socket); socket = null;
      const remaining = started ? Math.max(0, playhead - playerContext().currentTime) : 0;
      timer = window.setTimeout(() => settle(), remaining * 1000);
    };
    // A failure before any audio means Gradium is unusable; later on, just let the scheduled audio play out.
    const fail = (message: string) => {
      if (ended || settled) return;
      if (started) finish(); else settle(new VoiceUnavailable(message));
    };
    const play = (samples: Float32Array) => {
      if (!samples.length) return;
      const context = playerContext();
      const buffer = context.createBuffer(1, samples.length, sampleRate);
      buffer.getChannelData(0).set(samples);
      const source = context.createBufferSource();
      source.buffer = buffer; source.connect(context.destination);
      source.onended = () => { sources.delete(source); source.disconnect(); };
      playhead = Math.max(playhead, context.currentTime + SCHEDULE_AHEAD_S);
      source.start(playhead); playhead += buffer.duration;
      sources.add(source); started = true;
    };

    stopSpeech = halt;
    getToken().then(({ token, voice_id }) => {
      if (settled) return;
      const ws = socket = openSocket(TTS_URL, token);
      // Gradium accepts the whole request up front, so there is no need to wait for "ready".
      ws.onopen = () => {
        send(ws, { type: 'setup', model_name: 'default', voice_id, output_format: 'pcm' });
        send(ws, { type: 'text', text }); send(ws, { type: 'end_of_stream' });
      };
      ws.onmessage = event => {
        const message = parse<TtsMessage>(event.data);
        if (message.type === 'ready') {
          const rate = Number(message.sample_rate);
          if (rate >= 8000 && rate <= 96000) sampleRate = rate;
        } else if (message.type === 'audio') { if (typeof message.audio === 'string') play(decodePcm16(message.audio)); }
        else if (message.type === 'end_of_stream') finish();
        else if (message.type === 'error') fail(message.message || 'Gradium could not speak that.');
      };
      // A bad token still connects and is then closed with 1008; a clean close just ends the stream.
      ws.onerror = () => fail('Could not reach the Gradium voice service.');
      ws.onclose = event => { if (event.code === 1000) finish(); else fail('Gradium closed the voice connection before any audio arrived.'); };
    }).catch((error: unknown) => settle(error instanceof VoiceUnavailable ? error : new VoiceUnavailable(error instanceof Error ? error.message : undefined)));
  });
}
/** Silence at once; the pending speak() resolves. Safe to call at any time. */
function stop() { stopSpeech?.(); }

// ---------------------------------------------------------------- speech to text
// Hands raw microphone samples to the main thread, off the audio thread.
const CAPTURE_WORKLET = `
class Capture extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor("capture", Capture);
`;
function microphoneError(error: unknown): Error {
  const name = error instanceof Error ? error.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') return new Error('The microphone is blocked. Allow it for this page, or type instead.');
  if (name === 'NotFoundError') return new Error('I could not find a microphone. Type instead!');
  return new Error('I could not start the microphone. Type instead!');
}

let stopHearing: (() => void) | null = null;
/** Live input level (0..1 peak per 80 ms) for the mic button, as a window event. */
export const MIC_LEVEL_EVENT = 'brickvision:mic-level';
const reportLevel = (level: number) => window.dispatchEvent(new CustomEvent<number>(MIC_LEVEL_EVENT, { detail: level }));

/** Tap-to-talk: resolves with the transcript when the speaker stops, stopListening() is called or MAX_LISTEN_MS passes. */
function listen(onPartial?: (text: string) => void): Promise<string> {
  if (stopHearing) return Promise.reject(new Error('I am already listening.'));
  return new Promise<string>((resolve, reject) => {
    const segments: string[] = [];
    const chunk = new Float32Array(CHUNK_SAMPLES);
    const backlog: string[] = []; // Encoded chunks captured before Gradium was ready.
    let filled = 0, quietSteps = 0, maxTimer = 0, flushTimer = 0, deafTimer = 0;
    let chunks = 0, loudest = 0, micLabel = '';
    let ready = false, ending = false, settled = false;
    let stream: MediaStream | null = null, capture: AudioContext | null = null, socket: WebSocket | null = null;
    let nodes: AudioNode[] = [];

    /** Stop the microphone and the capture graph. Idempotent. */
    const release = () => {
      nodes.forEach(node => node.disconnect()); nodes = [];
      stream?.getTracks().forEach(track => track.stop()); stream = null;
      if (capture) { void capture.close().catch(() => undefined); capture = null; }
    };
    const settle = (error?: Error) => {
      if (settled) return;
      settled = true; window.clearTimeout(maxTimer); window.clearTimeout(flushTimer); window.clearTimeout(deafTimer);
      if (stopHearing === end) stopHearing = null;
      release(); closeSocket(socket); socket = null; reportLevel(0);
      if (error) reject(error); else resolve(segments.join(' ').trim());
    };
    const emit = (samples: Float32Array) => {
      let peak = 0; for (let i = 0; i < samples.length; i++) peak = Math.max(peak, Math.abs(samples[i]));
      chunks++; loudest = Math.max(loudest, peak); reportLevel(peak);
      const audio = encodePcm16(samples);
      if (ready) send(socket, { type: 'audio', audio });
      else if (backlog.push(audio) > MAX_BACKLOG_CHUNKS) backlog.shift();
    };
    const feed = (samples: Float32Array) => {
      for (let offset = 0; offset < samples.length;) {
        const count = Math.min(samples.length - offset, CHUNK_SAMPLES - filled);
        chunk.set(samples.subarray(offset, offset + count), filled);
        filled += count; offset += count;
        if (filled === CHUNK_SAMPLES) { emit(chunk); filled = 0; }
      }
    };
    /** Stop feeding audio, flush what is pending and give Gradium a moment to return the last words. */
    const end = () => {
      if (ending || settled) return;
      ending = true; window.clearTimeout(maxTimer); window.clearTimeout(deafTimer); release(); reportLevel(0);
      if (!ready || socket?.readyState !== WebSocket.OPEN) { settle(); return; }
      if (filled) { emit(chunk.subarray(0, filled)); filled = 0; }
      send(socket, { type: 'end_of_stream' });
      flushTimer = window.setTimeout(() => settle(), FLUSH_TIMEOUT_MS);
    };
    const start = async () => {
      // Create the capture context synchronously, while the tap still counts as a user gesture:
      // Safari leaves a context created after an await suspended, and then no audio ever flows.
      const context = capture = new AudioContext();
      void context.resume().catch(() => undefined);
      // Microphone first: the token only lives a few seconds, so it is minted right before the socket opens.
      let microphone: MediaStream;
      const wanted = { channelCount: 1, echoCancellation: true, noiseSuppression: true };
      try {
        microphone = stream = await navigator.mediaDevices.getUserMedia({ audio: wanted });
        // Meeting and light-sync apps install virtual inputs that are pure silence. If the browser picked one, switch to a real microphone.
        micLabel = microphone.getAudioTracks()[0]?.label ?? '';
        if (VIRTUAL_INPUT.test(micLabel)) {
          const real = (await navigator.mediaDevices.enumerateDevices()).find(device => device.kind === 'audioinput' && device.label
            && !VIRTUAL_INPUT.test(device.label) && device.deviceId !== 'default' && device.deviceId !== 'communications');
          if (real) {
            microphone.getTracks().forEach(track => track.stop());
            microphone = stream = await navigator.mediaDevices.getUserMedia({ audio: { ...wanted, deviceId: { exact: real.deviceId } } });
            micLabel = microphone.getAudioTracks()[0]?.label ?? real.label;
          }
        }
      } catch (error) { throw microphoneError(error); }
      if (settled) { release(); return; }
      if (context.state !== 'running') await Promise.race([context.resume().catch(() => undefined), new Promise(done => window.setTimeout(done, 800))]);
      const workletUrl = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: 'text/javascript' }));
      try { await context.audioWorklet.addModule(workletUrl); } finally { URL.revokeObjectURL(workletUrl); }
      if (settled) { release(); return; }

      const source = context.createMediaStreamSource(microphone);
      const worklet = new AudioWorkletNode(context, 'capture');
      const silence = context.createGain(); silence.gain.value = 0;
      const resample = createResampler(context.sampleRate, STT_RATE);
      worklet.port.onmessage = (event: MessageEvent<Float32Array>) => { if (!ending && !settled) feed(resample(event.data)); };
      source.connect(worklet); worklet.connect(silence).connect(context.destination);
      nodes = [source, worklet, silence];
      maxTimer = window.setTimeout(end, MAX_LISTEN_MS);
      // Say why nothing is being written instead of listening to nothing forever.
      deafTimer = window.setTimeout(() => {
        if (segments.length || ending || settled) return;
        if (chunks === 0) settle(new Error('This browser is not delivering microphone audio. Reload the page or use Chrome, or type instead.'));
        else if (loudest < SILENCE_PEAK) settle(new Error(`I only hear silence from ${micLabel ? `"${micLabel}"` : 'the microphone'}. Pick your real microphone in the browser's site settings (the icon left of the address bar), or type instead.`));
        else deafTimer = window.setTimeout(() => { if (!segments.length) end(); }, 4000); // Sound but no words: give up quietly.
      }, DEAF_CHECK_MS);

      const { token } = await getToken();
      if (settled) return;
      const ws = socket = openSocket(STT_URL, token);
      ws.onopen = () => send(ws, { type: 'setup', model_name: 'default', input_format: 'pcm', json_config: { language: 'en' } });
      ws.onmessage = event => {
        const message = parse<SttMessage>(event.data);
        switch (message.type) {
          case 'ready':
            ready = true;
            backlog.splice(0).forEach(audio => send(ws, { type: 'audio', audio }));
            break;
          case 'text':
            if (typeof message.text === 'string' && message.text.trim()) segments.push(message.text.trim());
            onPartial?.(segments.join(' '));
            break;
          case 'step': case 'vad': { // "vad" is the legacy name of the same message.
            const quiet = Number(message.vad?.[2]?.inactivity_prob) > VAD_THRESHOLD;
            quietSteps = quiet ? quietSteps + 1 : 0;
            if (segments.length > 0 && quietSteps >= VAD_CONSECUTIVE_STEPS) end();
            break;
          }
          case 'end_of_stream': settle(); break;
          case 'error': {
            const reason = `Gradium could not transcribe that${message.message ? `: ${message.message}` : '.'}`;
            settle(ready ? new Error(reason) : new VoiceUnavailable(reason));
            break;
          }
        }
      };
      // A bad token still connects and is then closed with 1008: before "ready" that means Gradium is unusable.
      // Once listening has begun, a dropped connection just ends the turn with what was heard.
      ws.onerror = () => settle(ready ? undefined : new VoiceUnavailable('Could not reach the Gradium voice service.'));
      ws.onclose = event => settle(ready || event.code === 1000 ? undefined : new VoiceUnavailable('Gradium refused the voice connection.'));
    };

    stopHearing = end;
    start().catch((error: unknown) => settle(error instanceof Error ? error : new Error('Voice input failed.')));
  });
}
/** End the current listen(); its promise resolves with the transcript. No-op when not listening. */
function stopListening() { stopHearing?.(); }

export const gradiumVoice: Required<VoiceAdapter> = { speak, stop, listen, stopListening };
