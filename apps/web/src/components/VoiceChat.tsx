import IconMicrophone from '@tabler/icons-react/dist/esm/icons/IconMicrophone.mjs';
import IconMicrophoneOff from '@tabler/icons-react/dist/esm/icons/IconMicrophoneOff.mjs';
import IconPlayerStop from '@tabler/icons-react/dist/esm/icons/IconPlayerStop.mjs';
import IconGridDots from '@tabler/icons-react/dist/esm/icons/IconGridDots.mjs';
import IconMinus from '@tabler/icons-react/dist/esm/icons/IconMinus.mjs';
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type FormEvent, type KeyboardEvent, type PointerEvent } from 'react';
import { clampPosition, setDockState, useDockState } from '../voice/dockState';
import { GRADIUM_VOICE_NAME, type VoiceState } from '../voice/session';
import type { Assistant } from '../voice/useAssistant';
import './voice.css';

const STATUS: Record<VoiceState, string> = {
  idle: 'Say or type where to go: “open the plane tutorial”, “next step”.',
  connecting: 'Connecting to your microphone…',
  listening: 'Listening — try “go to step 3” or “go home”.',
  thinking: 'Thinking…',
  speaking: `${GRADIUM_VOICE_NAME} is speaking…`,
  error: 'Voice chat stopped.',
};
const MUTED: Partial<Record<VoiceState, string>> = {
  listening: 'Microphone muted — type a command, or unmute to talk.',
  thinking: 'Microphone muted · thinking…',
  speaking: `Microphone muted · ${GRADIUM_VOICE_NAME} is speaking…`,
};

export default function VoiceChat({assistant, variant = 'hero'}: {assistant: Assistant; variant?: 'hero' | 'dock'}) {
  const {voiceState, voiceActive, turns, partial, error, pending, muted, toggleVoice, toggleMute, submitText} = assistant;
  const [draft, setDraft] = useState('');
  const dock = useDockState();
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{dx: number; dy: number} | null>(null);
  const supported = typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && 'AudioWorkletNode' in window;
  const state: VoiceState = pending && !voiceActive ? 'thinking' : voiceState;
  const status = error ?? (!supported ? 'Voice needs microphone support; you can still type a command.'
    : (muted && MUTED[state]) || STATUS[state]);
  const recent = turns.slice(partial ? -1 : -2);

  function submit(event: FormEvent) {
    event.preventDefault();
    submitText(draft);
    setDraft('');
  }

  const isDock = variant === 'dock';
  const minimized = isDock && dock.minimized;

  // Keep the dock on screen when it changes size (minimize/expand) or the window shrinks.
  useLayoutEffect(() => {
    if (!isDock || !dock.position || !box.current) return;
    const {width, height} = box.current.getBoundingClientRect();
    const next = clampPosition(dock.position.x, dock.position.y, width, height);
    if (next.x !== dock.position.x || next.y !== dock.position.y) setDockState({position: next}, false);
  });
  useEffect(() => {
    if (!isDock) return;
    const refit = () => { const current = box.current?.getBoundingClientRect(); if (current && dock.position) setDockState({position: clampPosition(current.left, current.top, current.width, current.height)}, false); };
    window.addEventListener('resize', refit);
    return () => window.removeEventListener('resize', refit);
  }, [isDock, dock.position]);

  function startDrag(event: PointerEvent<HTMLButtonElement>) {
    if (!box.current || event.button !== 0) return;
    const rect = box.current.getBoundingClientRect();
    drag.current = {dx: event.clientX - rect.left, dy: event.clientY - rect.top};
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  }
  function moveDrag(event: PointerEvent<HTMLButtonElement>) {
    if (!drag.current || !box.current) return;
    const {width, height} = box.current.getBoundingClientRect();
    setDockState({position: clampPosition(event.clientX - drag.current.dx, event.clientY - drag.current.dy, width, height)}, false);
  }
  function endDrag(event: PointerEvent<HTMLButtonElement>) {
    if (!drag.current) return;
    drag.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
    setDockState({});
  }
  function nudge(event: KeyboardEvent<HTMLButtonElement>) {
    const step = event.shiftKey ? 80 : 24;
    const delta = {ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step]}[event.key];
    if (!delta || !box.current) return;
    event.preventDefault();
    const rect = box.current.getBoundingClientRect();
    setDockState({position: clampPosition(rect.left + delta[0], rect.top + delta[1], rect.width, rect.height)});
  }

  const placed: CSSProperties | undefined = isDock && dock.position ? {left: dock.position.x, top: dock.position.y, right: 'auto', bottom: 'auto'} : undefined;
  const grip = isDock && <button type="button" className="voice-grip" aria-label="Move build helper (drag, or use arrow keys)" title="Drag to move"
    onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag} onKeyDown={nudge}>
    <IconGridDots size={16} stroke={2.4} aria-hidden="true"/>
  </button>;

  // The dock floats over working controls, so it can shrink to a small pill that still shows the voice state.
  if (minimized) return <div ref={box} style={placed} className={`voice-chat voice-dock voice-collapsed voice-${state}${muted ? ' voice-muted' : ''}`}>
    {grip}
    <button type="button" className="voice-button" onClick={() => setDockState({minimized: false})} aria-label="Open build helper" aria-expanded={false}
      title={voiceActive ? status : 'Open build helper'}>
      <span className="voice-orb" aria-hidden="true">
        <span className="voice-ring"/><span className="voice-ring delay"/>
        {muted ? <IconMicrophoneOff size={22} stroke={2.2}/> : <IconMicrophone size={22} stroke={2.2}/>}
      </span>
    </button>
  </div>;

  return <div ref={box} style={placed} className={`voice-chat voice-${variant} voice-${state}${muted ? ' voice-muted' : ''}`}>
    {isDock && <div className="voice-dock-bar">
      {grip}
      <button type="button" className="voice-hide" onClick={() => setDockState({minimized: true})} aria-label="Minimize build helper" aria-expanded={true} title="Minimize">
        <IconMinus size={16} stroke={2.4} aria-hidden="true"/>
      </button>
    </div>}
    <div className="voice-row">
      <button type="button" className="voice-button" onClick={toggleVoice} disabled={!supported} aria-pressed={voiceActive}
        aria-label={voiceActive ? 'Stop voice chat' : 'Start voice chat'}>
        <span className="voice-orb" aria-hidden="true">
          <span className="voice-ring"/><span className="voice-ring delay"/>
          {voiceActive ? <IconPlayerStop size={variant === 'dock' ? 20 : 24} stroke={2.2}/> : <IconMicrophone size={variant === 'dock' ? 22 : 26} stroke={2.2}/>}
        </span>
      </button>
      {voiceActive && <button type="button" className="voice-mute" onClick={toggleMute} aria-pressed={muted}
        aria-label={muted ? 'Unmute microphone' : 'Mute microphone'} title={muted ? 'Unmute microphone' : 'Mute microphone'}>
        {muted ? <IconMicrophoneOff size={18} stroke={2.2} aria-hidden="true"/> : <IconMicrophone size={18} stroke={2.2} aria-hidden="true"/>}
      </button>}
      <div className="voice-copy">
        <strong>{voiceActive ? 'Voice helper is on' : 'Talk to the build helper'}</strong>
        <span role="status" aria-live="polite">{status}</span>
      </div>
    </div>
    {(recent.length > 0 || partial) && <ol className="voice-transcript" aria-label="Assistant conversation">
      {recent.map((turn, index) => <li key={turns.length - recent.length + index} className={turn.role}><span>{turn.role === 'user' ? 'You' : GRADIUM_VOICE_NAME}</span>{turn.text}</li>)}
      {partial && <li className="user partial"><span>You</span>{partial}</li>}
    </ol>}
    <form className="voice-command" onSubmit={submit}>
      <label className="sr-only" htmlFor={`voice-command-${variant}`}>Type a command for the build helper</label>
      <input id={`voice-command-${variant}`} value={draft} onChange={event => setDraft(event.target.value)} maxLength={500}
        placeholder="Type a command…" autoComplete="off" disabled={pending}/>
      <button type="submit" className="secondary" disabled={pending || !draft.trim()}>Send</button>
    </form>
    {variant === 'hero' && <p className="voice-note">Voice by Gradium · navigation and replies by Gemini · microphone only while on</p>}
  </div>;
}
