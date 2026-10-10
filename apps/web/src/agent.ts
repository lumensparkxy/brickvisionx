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
/** Actions that move between screens; they work everywhere, not only in the 3D viewer. */
export type AppAction =
  | { type: 'find_set'; set_number: string }
  | { type: 'open_tutorial'; set_number: string; guide_id?: string }
  | { type: 'go_home' } | { type: 'close_booklet' };
export type BuddyAction = ViewerAction | AppAction;
export interface AppContext {
  screen: 'landing' | 'booklet' | 'tutorial'; set_number?: string | null; guide_id?: string | null;
  guides?: { guide_id: string; label: string; tutorial_available: boolean }[];
}
export interface AppController { context(): AppContext; run(action: AppAction): Promise<void>; }
export interface BuddyContext { app: AppContext; viewer: ViewerContext | null; }
export interface ChatTurn { role: 'user' | 'assistant'; text: string; }
export interface AgentReply { reply: string; actions: BuddyAction[]; }

// One assistant for the whole app. The app shell and the 3D viewer register here; the registry lives on the global
// object so a dev-server hot update of this module does not lose who is registered.
interface Hub { app: AppController | null; viewer: { current: ViewerController } | null; }
const hub: Hub = ((globalThis as { __brickvisionHub?: Hub }).__brickvisionHub ??= { app: null, viewer: null });
export function registerApp(controller: AppController) { hub.app = controller; return () => { if (hub.app === controller) hub.app = null; }; }
export function registerViewer(controller: { current: ViewerController }) { hub.viewer = controller; return () => { if (hub.viewer === controller) hub.viewer = null; }; }
const APP_ACTIONS = new Set(['find_set', 'open_tutorial', 'go_home', 'close_booklet']);
export const isAppAction = (action: BuddyAction): action is AppAction => APP_ACTIONS.has(action.type);
export function buddyContext(): BuddyContext {
  return { app: hub.app?.context() ?? { screen: hub.viewer ? 'tutorial' : 'landing' }, viewer: hub.viewer?.current.context() ?? null };
}
/** The viewer mounts a moment after a tutorial opens, so viewer actions wait briefly for it. */
async function viewerSoon(patience: number): Promise<ViewerController | null> {
  for (const until = Date.now() + patience; !hub.viewer && Date.now() < until;) await new Promise(done => setTimeout(done, 100));
  return hub.viewer?.current ?? null;
}
export async function runAction(action: BuddyAction): Promise<void> {
  if (isAppAction(action)) {
    if (!hub.app) throw new Error('I cannot move between screens right now.');
    return hub.app.run(action);
  }
  const viewer = await viewerSoon(action.type === 'stop' ? 0 : 8000);
  if (viewer) return viewer.run(action);
  if (action.type !== 'stop') throw new Error('Open a 3D tutorial first, then I can move through its steps.');
}
/** Ask the chat panel to open and start listening (used by the landing page's talk button). */
export const TALK_EVENT = 'brickvision:talk';
export const requestTalk = () => window.dispatchEvent(new Event(TALK_EVENT));

const int = (value: unknown, fallback: number) => Number.isFinite(Number(value)) ? Math.trunc(Number(value)) : fallback;
const SET_NUMBER = /^\d{4,7}$/;
/** Model output is untrusted: keep only well-formed actions. */
export function parseActions(value: unknown): BuddyAction[] {
  if (!Array.isArray(value)) return [];
  const actions: BuddyAction[] = [];
  for (const raw of value) {
    const item = (raw ?? {}) as Record<string, unknown>;
    switch (item.type) {
      case 'go_to_step': actions.push({ type: 'go_to_step', step: Math.max(1, int(item.step, 1)) }); break;
      case 'play_steps': actions.push({ type: 'play_steps', step: Math.max(1, int(item.step, 1)), count: Math.max(1, Math.min(12, int(item.count, 1))),
        narrations: Array.isArray(item.narrations) ? item.narrations.filter((line): line is string => typeof line === 'string') : [] }); break;
      case 'rotate': if (['left','right','up','down'].includes(item.direction as string)) actions.push({ type: 'rotate',
        direction: item.direction as 'left', degrees: Math.max(5, Math.min(720, Math.abs(Number(item.degrees)) || 90)) }); break;
      case 'zoom': if (item.direction === 'in' || item.direction === 'out') actions.push({ type: 'zoom', direction: item.direction }); break;
      case 'reset_view': case 'replay_step': case 'stop': case 'go_home': case 'close_booklet': actions.push({ type: item.type }); break;
      case 'find_set': if (typeof item.set_number === 'string' && SET_NUMBER.test(item.set_number)) actions.push({ type: 'find_set', set_number: item.set_number }); break;
      case 'open_tutorial': if (typeof item.set_number === 'string' && SET_NUMBER.test(item.set_number)) actions.push(
        typeof item.guide_id === 'string' && /^[a-z0-9-]{1,64}$/.test(item.guide_id)
          ? { type: 'open_tutorial', set_number: item.set_number, guide_id: item.guide_id } : { type: 'open_tutorial', set_number: item.set_number }); break;
    }
  }
  return actions;
}
export async function askAgent(messages: ChatTurn[], context: BuddyContext): Promise<AgentReply> {
  const body = await post<{ reply?: unknown; actions?: unknown }>('/chat', { messages, viewer: context.viewer ?? {}, app: context.app });
  return { reply: typeof body.reply === 'string' ? body.reply : '', actions: parseActions(body.actions) };
}
export function describeAction(action: BuddyAction): string {
  switch (action.type) {
    case 'find_set': return `⌕ Set ${action.set_number}`;
    case 'open_tutorial': return `▶ Open ${action.set_number}`;
    case 'go_home': return '⌂ Home';
    case 'close_booklet': return '✕ Close list';
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
let spoken = 0;
let gradiumDownUntil = 0; // One network blip must not downgrade the whole session: retry Gradium after a cool-off.
async function withFallback<T>(run: (voice: Required<VoiceAdapter>) => Promise<T>): Promise<T> {
  let reason: VoiceUnavailable | null = null;
  if (Date.now() >= gradiumDownUntil) {
    try { return await run(gradiumVoice); }
    catch (error) { if (!(error instanceof VoiceUnavailable)) throw error; reason = error; gradiumDownUntil = Date.now() + 20000; }
  }
  // If the browser cannot do it either, report why Gradium was unavailable: that is the cause worth fixing.
  try { return await run(browserVoice); } catch (error) { throw reason ?? error; }
}
const defaultVoice: Required<VoiceAdapter> = {
  // A line that was stopped while Gradium was still failing over must not start again on the browser voice.
  speak: text => { const mine = ++spoken; return withFallback(voice => mine === spoken ? voice.speak(text) : Promise.resolve()); },
  stop: () => { spoken++; gradiumVoice.stop(); browserVoice.stop(); },
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
// Narration lines travel as a window event, not through module state: a dev-server hot update re-creates this module,
// and a listener registered on the old copy would silently stop receiving lines (bubbles missing while the voice still speaks).
const NARRATION_EVENT = 'brickvision:narration';
export function onNarration(listener: (text: string) => void) {
  const handle = (event: Event) => listener((event as CustomEvent<string>).detail);
  window.addEventListener(NARRATION_EVENT, handle);
  return () => window.removeEventListener(NARRATION_EVENT, handle);
}
/** A walkthrough line: show it in the chat and speak it. */
export function narrate(text: string): Promise<void> { window.dispatchEvent(new CustomEvent<string>(NARRATION_EVENT, { detail: text })); return speak(text); }
