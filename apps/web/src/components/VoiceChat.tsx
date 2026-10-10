import IconMicrophone from '@tabler/icons-react/dist/esm/icons/IconMicrophone.mjs';
import IconMicrophoneOff from '@tabler/icons-react/dist/esm/icons/IconMicrophoneOff.mjs';
import IconPlayerStop from '@tabler/icons-react/dist/esm/icons/IconPlayerStop.mjs';
import { useState, type FormEvent } from 'react';
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
  const [open, setOpen] = useState(false);
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

  // The dock floats over working controls, so it stays a small button until needed.
  const collapsible = variant === 'dock' && !voiceActive && !pending;
  if (collapsible && !open) return <div className={`voice-chat voice-dock voice-collapsed voice-${state}`}>
    <button type="button" className="voice-button" onClick={() => setOpen(true)} aria-label="Open build helper" aria-expanded={false}>
      <span className="voice-orb" aria-hidden="true"><IconMicrophone size={22} stroke={2.2}/></span>
    </button>
  </div>;

  return <div className={`voice-chat voice-${variant} voice-${state}${muted ? ' voice-muted' : ''}`}>
    {collapsible && <button type="button" className="voice-hide" onClick={() => setOpen(false)} aria-label="Hide build helper" aria-expanded={true}>×</button>}
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
