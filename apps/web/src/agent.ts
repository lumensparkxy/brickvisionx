/**
 * Shared contract between the chat panel, the voice front end and the 3D viewer.
 * The backend proposes a spoken reply plus viewer actions; the browser executes them.
 * Voice (speech-to-text / text-to-speech) is Gradium by default and can be replaced through setVoice(); see window.brickvision.
 */
import { post } from './api';
import { gradiumVoice, VoiceUnavailable } from './gradiumVoice';

export type ViewerAction =
  | { type: 'go_to_step'; step: number }
  | { type: 'play_steps'; step: number; count: number; narrations: string[] }
  | { type: 'rotate'; direction: 'left' | 'right' | 'up' | 'down'; degrees: number }
  | { type: 'zoom'; direction: 'in' | 'out' }
  | { type: 'reset_view' } | { type: 'replay_step' } | { type: 'stop' };

export interface ViewerContext {
  set_number: string; guide: string; current_step: number; total_steps: number; playing: boolean;
  steps: { step: number; instructions: string[]; pieces: string[] }[];
}
export interface ViewerController { context(): ViewerContext; run(action: ViewerAction): Promise<void>; }
export interface ChatTurn { role: 'user' | 'assistant'; text: string; }
export interface AgentReply { reply: string; actions: ViewerAction[]; }

const int = (value: unknown, fallback: number) => Number.isFinite(Number(value)) ? Math.trunc(Number(value)) : fallback;
/** Model output is untrusted: keep only well-formed actions. */
export function parseActions(value: unknown): ViewerAction[] {
  if (!Array.isArray(value)) return [];
  const actions: ViewerAction[] = [];
  for (const raw of value) {
    const item = (raw ?? {}) as Record<string, unknown>;
    switch (item.type) {
      case 'go_to_step': actions.push({ type: 'go_to_step', step: int(item.step, 1) }); break;
      case 'play_steps': actions.push({ type: 'play_steps', step: int(item.step, 1), count: Math.max(1, Math.min(12, int(item.count, 1))),
        narrations: Array.isArray(item.narrations) ? item.narrations.filter((line): line is string => typeof line === 'string') : [] }); break;
      case 'rotate': if (['left','right','up','down'].includes(item.direction as string)) actions.push({ type: 'rotate',
        direction: item.direction as 'left', degrees: Math.max(5, Math.min(720, Math.abs(Number(item.degrees)) || 90)) }); break;
      case 'zoom': if (item.direction === 'in' || item.direction === 'out') actions.push({ type: 'zoom', direction: item.direction }); break;
      case 'reset_view': case 'replay_step': case 'stop': actions.push({ type: item.type }); break;
    }
  }
  return actions;
}
export async function askAgent(messages: ChatTurn[], viewer: ViewerContext): Promise<AgentReply> {
  const body = await post<{ reply?: unknown; actions?: unknown }>('/chat', { messages, viewer });
  return { reply: typeof body.reply === 'string' ? body.reply : '', actions: parseActions(body.actions) };
}
export function describeAction(action: ViewerAction): string {
  switch (action.type) {
    case 'go_to_step': return `→ Step ${action.step}`;
    case 'play_steps': return action.count > 1 ? `▶ Steps ${action.step}–${action.step + action.count - 1}` : `▶ Step ${action.step}`;
    case 'rotate': return `↻ ${action.direction} ${Math.round(action.degrees)}°`;
    case 'zoom': return action.direction === 'in' ? '＋ Zoom in' : '－ Zoom out';
    case 'reset_view': return '⌖ Reset view';
    case 'replay_step': return '↺ Replay';
    case 'stop': return '■ Stop';
  }
}

/** Voice plug-in point. speak() must resolve when the audio has finished (or was stopped). */
export interface VoiceAdapter {
  speak(text: string): Promise<void>; stop(): void;
  /** Tap-to-talk: resolves with the transcript once the speaker is done; onPartial receives the text heard so far. */
  listen?(onPartial?: (text: string) => void): Promise<string>;
  stopListening?(): void;
}
type Recognition = { lang: string; interimResults: boolean; start(): void; stop(): void;
  onresult: ((event: { results: { 0: { transcript: string } }[] }) => void) | null; onerror: ((event: { error: string }) => void) | null; onend: (() => void) | null };
let recognition: Recognition | null = null;
/** Browser speech: the fallback when Gradium is not available. */
const browserVoice: Required<VoiceAdapter> = {
  speak: text => new Promise(resolve => {
    if (!('speechSynthesis' in window)) { resolve(); return; }
    const utterance = new SpeechSynthesisUtterance(text); utterance.rate = 1.05;
    utterance.onend = utterance.onerror = () => resolve();
    speechSynthesis.cancel(); speechSynthesis.speak(utterance);
  }),
  stop: () => { if ('speechSynthesis' in window) speechSynthesis.cancel(); },
  // Browser recognition only reports the final result here, so onPartial is ignored.
  listen: () => new Promise((resolve, reject) => {
    const scope = window as unknown as Record<string, (new () => Recognition) | undefined>;
    const Ctor = scope.SpeechRecognition ?? scope.webkitSpeechRecognition;
    if (!Ctor) { reject(new Error('Voice input is not available in this browser yet. Type instead!')); return; }
    const current = new Ctor(); current.lang = 'en-US'; current.interimResults = false;
    current.onresult = event => resolve(event.results[0][0].transcript);
    current.onerror = event => reject(new Error(`I could not hear that (${event.error}).`));
    current.onend = () => { if (recognition === current) recognition = null; resolve(''); };
    recognition = current; current.start();
  }),
  stopListening: () => recognition?.stop(),
};
/** Default voice: Gradium, switching to browser speech for the rest of the session once Gradium proves unavailable. */
let gradiumDownUntil = 0; // One network blip must not downgrade the whole session: retry Gradium after a cool-off.
async function withFallback<T>(run: (voice: Required<VoiceAdapter>) => Promise<T>): Promise<T> {
  if (Date.now() >= gradiumDownUntil) {
    try { return await run(gradiumVoice); }
    catch (error) { if (!(error instanceof VoiceUnavailable)) throw error; gradiumDownUntil = Date.now() + 20000; }
  }
  return run(browserVoice);
}
const defaultVoice: Required<VoiceAdapter> = {
  speak: text => withFallback(voice => voice.speak(text)),
  stop: () => { gradiumVoice.stop(); browserVoice.stop(); },
  listen: onPartial => withFallback(voice => voice.listen(onPartial)),
  stopListening: () => { gradiumVoice.stopListening(); browserVoice.stopListening(); },
};
const VOICE_KEY = 'brickvisionx:voice', VOICE_EVENT = 'brickvision:voice';
let adapter: VoiceAdapter = defaultVoice;
// Voice starts on at every page load: a mute left over from an earlier visit must not silence a demo.
let muted = false;
try { localStorage.removeItem(VOICE_KEY); } catch { /* Storage may be unavailable. */ }
let openMics = 0;
let cancel: (() => void) | null = null;
export const isMuted = () => muted;
export function setMuted(value: boolean) {
  if (value) stopSpeaking();
  muted = value;
  window.dispatchEvent(new Event(VOICE_EVENT));
}
export function onVoiceChange(listener: () => void) { window.addEventListener(VOICE_EVENT, listener); return () => window.removeEventListener(VOICE_EVENT, listener); }
/** Register a real voice provider (speech out, optionally speech in) and turn sound on. */
export function setVoice(next: VoiceAdapter | null) { stopSpeaking(); stopListening(); adapter = next ?? defaultVoice; setMuted(false); }
/**
 * Tap-to-talk; resolves with the transcript ('' when nothing was heard). A registered adapter that cannot listen
 * leaves the microphone to the default voice. Nothing is spoken aloud while the microphone is open.
 */
export async function listen(onPartial?: (text: string) => void): Promise<string> {
  openMics++;
  try { return await (adapter.listen ? adapter.listen(onPartial) : defaultVoice.listen(onPartial)); }
  finally { openMics--; }
}
/** End the current listen(); its promise then resolves with what was heard. */
export function stopListening() { if (adapter.listen) adapter.stopListening?.(); else defaultVoice.stopListening(); }
export function stopSpeaking() { cancel?.(); }
/** Resolves when the line has been spoken; when muted (or while the microphone is open) it waits a short reading pause instead. */
export function speak(text: string): Promise<void> {
  stopSpeaking();
  if (!text.trim()) return Promise.resolve();
  return new Promise<void>(resolve => {
    const audible = !muted && openMics === 0; let settled = false;
    const done = () => { if (settled) return; settled = true; window.clearTimeout(timer); if (cancel === abort) cancel = null; resolve(); };
    const abort = () => { if (audible) adapter.stop(); done(); };
    // Safety net: never let a stuck audio backend freeze a walkthrough.
    const timer = window.setTimeout(done, audible ? 8000 + text.length * 110 : Math.min(4200, 900 + text.length * 30));
    cancel = abort;
    if (audible) adapter.speak(text).then(done, done);
  });
}
const narrationListeners = new Set<(text: string) => void>();
export function onNarration(listener: (text: string) => void) { narrationListeners.add(listener); return () => { narrationListeners.delete(listener); }; }
/** A walkthrough line: show it in the chat and speak it. */
export function narrate(text: string): Promise<void> { narrationListeners.forEach(listener => listener(text)); return speak(text); }
