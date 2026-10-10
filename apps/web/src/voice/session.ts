import { post } from '../api';
import { ChunkBuffer, STT_SAMPLE_RATE, TurnDetector, base64ToPcm16, bytesToBase64, floatToPcm16, pcm16ToFloat } from './audio';

export const GRADIUM_STT_MODEL = 'default';
export const GRADIUM_TTS_MODEL = 'default';
export const GRADIUM_VOICE_ID = 'YTpq7expH9539ERJ';
export const GRADIUM_VOICE_NAME = 'Emma';
const GRADIUM_WS = 'wss://api.gradium.ai/api/speech';

export type VoiceState = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking' | 'error';
export interface VoiceCallbacks {
  onState: (state: VoiceState) => void;
  onPartial: (text: string) => void;
  onError: (message: string) => void;
  /** Returns the text to speak, or null to stay silent and keep listening. */
  onUtterance: (text: string) => Promise<string | null>;
}

const WORKLET = `class PcmCapture extends AudioWorkletProcessor {
  process(inputs) { const channel = inputs[0] && inputs[0][0]; if (channel) this.port.postMessage(channel.slice(0)); return true; }
}
registerProcessor('pcm-capture', PcmCapture);`;

async function gradiumSocket(path: 'asr' | 'tts'): Promise<WebSocket> {
  const { token } = await post<{token: string}>('/voice/token');
  const url = new URL(`${GRADIUM_WS}/${path}`);
  url.searchParams.set('token', token);
  return new WebSocket(url);
}

/** Microphone -> Gradium STT -> onUtterance (assistant) -> Gradium TTS -> speakers. */
export class VoiceSession {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private capture: AudioWorkletNode | null = null;
  private stt: WebSocket | null = null;
  private tts: WebSocket | null = null;
  private chunks = new ChunkBuffer();
  private detector = new TurnDetector();
  private state: VoiceState = 'idle';
  private partial = '';
  private flushId = 0;
  private awaitingFlush = false;
  private playhead = 0;
  private sources = new Set<AudioBufferSourceNode>();
  private stopped = false;
  private muted = false;

  constructor(private callbacks: VoiceCallbacks) {}

  /** Mute only the microphone; replies already in progress keep thinking and speaking. */
  setMuted(muted: boolean) {
    this.muted = muted;
    this.stream?.getAudioTracks().forEach(track => { track.enabled = !muted; });
  }

  async start() {
    this.setState('connecting');
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true}});
      this.setMuted(this.muted);
      this.context = new AudioContext({sampleRate: STT_SAMPLE_RATE});
      const moduleUrl = URL.createObjectURL(new Blob([WORKLET], {type: 'text/javascript'}));
      await this.context.audioWorklet.addModule(moduleUrl);
      URL.revokeObjectURL(moduleUrl);
      if (this.stopped) return;
      const source = this.context.createMediaStreamSource(this.stream);
      this.capture = new AudioWorkletNode(this.context, 'pcm-capture');
      const mute = this.context.createGain();
      mute.gain.value = 0;
      source.connect(this.capture).connect(mute).connect(this.context.destination);
      this.capture.port.onmessage = event => this.onAudio(event.data as Float32Array);
      await this.openStt();
    } catch (error) {
      this.fail(error instanceof DOMException && error.name === 'NotAllowedError'
        ? 'Microphone access was blocked. Allow it in the browser to talk.'
        : error instanceof Error ? error.message : 'The voice session could not start.');
    }
  }

  stop() {
    this.stopped = true;
    for (const socket of [this.stt, this.tts]) {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type: 'end_of_stream'}));
      socket?.close();
    }
    this.stt = this.tts = null;
    this.stopPlayback();
    this.capture?.disconnect();
    this.stream?.getTracks().forEach(track => track.stop());
    void this.context?.close();
    this.context = null;
    if (this.state !== 'error') this.setState('idle');
  }

  private async openStt() {
    const socket = await gradiumSocket('asr');
    if (this.stopped) { socket.close(); return; }
    this.stt = socket;
    socket.onopen = () => socket.send(JSON.stringify({type: 'setup', model_name: GRADIUM_STT_MODEL, input_format: 'pcm',
      json_config: {language: 'en', delay_in_frames: 16}}));
    socket.onmessage = event => this.onSttMessage(JSON.parse(event.data));
    socket.onerror = () => this.fail('The speech recognition connection failed.');
    socket.onclose = () => { if (!this.stopped && this.stt === socket) this.fail('The speech recognition connection closed.'); };
  }

  private onAudio(block: Float32Array) {
    if (!this.stt || this.stt.readyState !== WebSocket.OPEN || this.state === 'connecting') return;
    // While the assistant answers or the mic is muted, send silence: the stream stays open and a
    // half-spoken turn still ends through voice-activity detection.
    const pcm = this.state === 'listening' && !this.muted ? floatToPcm16(block) : new Int16Array(block.length);
    for (const chunk of this.chunks.push(pcm)) {
      this.stt.send(JSON.stringify({type: 'audio', audio: bytesToBase64(new Uint8Array(chunk.buffer))}));
    }
  }

  private onSttMessage(message: {type: string; text?: string; message?: string; vad?: {horizon_s: number; inactivity_prob: number}[]}) {
    if (message.type === 'ready') this.setState('listening');
    else if (message.type === 'text' && this.state === 'listening' && message.text) {
      this.partial = `${this.partial} ${message.text}`.trim();
      this.callbacks.onPartial(this.partial);
    } else if (message.type === 'step' && this.state === 'listening' && !this.awaitingFlush) {
      if (this.detector.update(message, this.partial.length > 0)) {
        this.awaitingFlush = true;
        this.flushId += 1;
        this.stt?.send(JSON.stringify({type: 'flush', flush_id: this.flushId}));
      }
    } else if (message.type === 'flushed' && this.awaitingFlush) {
      this.awaitingFlush = false;
      const text = this.partial.trim();
      this.partial = '';
      this.callbacks.onPartial('');
      if (text) void this.respond(text);
    } else if (message.type === 'error') this.fail(message.message || 'Speech recognition reported an error.');
  }

  /** Typed input while voice is on: answered aloud like a spoken turn. */
  submit(text: string) {
    if (this.state === 'listening') void this.respond(text);
  }

  private async respond(text: string) {
    this.setState('thinking');
    try {
      const reply = await this.callbacks.onUtterance(text);
      if (this.stopped) return;
      if (reply) await this.speak(reply);
      else { this.detector.reset(); this.setState('listening'); }
    } catch (error) {
      if (!this.stopped) this.fail(error instanceof Error ? error.message : 'The assistant could not reply.');
    }
  }

  private async speak(text: string) {
    const context = this.context;
    if (!context) return;
    this.setState('speaking');
    const socket = await gradiumSocket('tts');
    if (this.stopped) { socket.close(); return; }
    this.tts = socket;
    this.playhead = context.currentTime + 0.08;
    await new Promise<void>((resolve, reject) => {
      socket.onopen = () => {
        socket.send(JSON.stringify({type: 'setup', model_name: GRADIUM_TTS_MODEL, voice_id: GRADIUM_VOICE_ID, output_format: 'pcm_24000'}));
        socket.send(JSON.stringify({type: 'text', text}));
        socket.send(JSON.stringify({type: 'end_of_stream'}));
      };
      socket.onmessage = event => {
        const message = JSON.parse(event.data);
        if (message.type === 'audio') this.play(base64ToPcm16(message.audio));
        else if (message.type === 'end_of_stream') { socket.close(); resolve(); }
        else if (message.type === 'error') reject(new Error(message.message || 'Speech synthesis failed.'));
      };
      socket.onerror = () => reject(new Error('The speech synthesis connection failed.'));
      socket.onclose = () => resolve();
    });
    this.tts = null;
    const remaining = Math.max(0, this.playhead - context.currentTime);
    await new Promise(resolve => setTimeout(resolve, remaining * 1000 + 150));
    if (!this.stopped) {
      this.detector.reset();
      this.setState('listening');
    }
  }

  private play(pcm: Int16Array) {
    if (!this.context || pcm.length === 0) return;
    const buffer = this.context.createBuffer(1, pcm.length, STT_SAMPLE_RATE);
    buffer.copyToChannel(pcm16ToFloat(pcm) as Float32Array<ArrayBuffer>, 0);
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.context.destination);
    const at = Math.max(this.playhead, this.context.currentTime + 0.02);
    source.start(at);
    this.playhead = at + buffer.duration;
    this.sources.add(source);
    source.onended = () => this.sources.delete(source);
  }

  private stopPlayback() {
    for (const source of this.sources) { try { source.stop(); } catch { /* already ended */ } }
    this.sources.clear();
  }

  private setState(state: VoiceState) {
    this.state = state;
    this.callbacks.onState(state);
  }

  private fail(message: string) {
    if (this.stopped) return;
    this.setState('error');
    this.callbacks.onError(message);
    this.stop();
  }
}
