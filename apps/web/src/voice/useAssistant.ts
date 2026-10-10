import { useEffect, useRef, useState } from 'react';
import { askAssistant, type AssistantAction, type AssistantContext, type AssistantTurn } from './assistant';
import { VoiceSession, type VoiceState } from './session';

const HISTORY_TURNS = 12;

export interface Assistant {
  voiceState: VoiceState;
  voiceActive: boolean;
  turns: AssistantTurn[];
  partial: string;
  error: string | null;
  pending: boolean;
  muted: boolean;
  toggleVoice: () => void;
  toggleMute: () => void;
  submitText: (text: string) => void;
}

/** One assistant for the whole app, so voice survives moving between landing, booklet and tutorial. */
export function useAssistant(getContext: () => AssistantContext, perform: (action: AssistantAction) => Promise<void> | void): Assistant {
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [partial, setPartial] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [muted, setMuted] = useState(false);
  const session = useRef<VoiceSession | null>(null);
  const history = useRef<AssistantTurn[]>([]);
  const latest = useRef({getContext, perform});
  latest.current = {getContext, perform};

  useEffect(() => () => session.current?.stop(), []);

  const push = (turn: AssistantTurn) => {
    history.current = [...history.current, turn];
    setTurns(history.current);
  };

  async function handle(text: string): Promise<string | null> {
    push({role: 'user', text});
    setPending(true);
    setError(null);
    try {
      const reply = await askAssistant(history.current.slice(-HISTORY_TURNS), latest.current.getContext());
      push({role: 'assistant', text: reply.text});
      if (reply.action.type !== 'none') {
        try { await latest.current.perform(reply.action); }
        catch (failure) { setError(failure instanceof Error ? failure.message : 'That navigation could not be completed.'); }
      }
      return reply.text;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'The assistant could not reply.');
      return null;
    } finally {
      setPending(false);
    }
  }

  const voiceActive = voiceState !== 'idle' && voiceState !== 'error';

  function toggleVoice() {
    if (session.current && voiceActive) {
      session.current.stop();
      session.current = null;
      setMuted(false);
      return;
    }
    setError(null);
    setPartial('');
    setMuted(false);
    session.current = new VoiceSession({onState: setVoiceState, onPartial: setPartial, onError: setError, onUtterance: handle});
    void session.current.start();
  }

  function toggleMute() {
    if (!session.current || !voiceActive) return;
    session.current.setMuted(!muted);
    setMuted(!muted);
  }

  function submitText(text: string) {
    const value = text.trim();
    if (!value || pending) return;
    if (session.current && voiceActive) session.current.submit(value);
    else void handle(value);
  }

  return {voiceState, voiceActive, turns, partial, error, pending, muted: muted && voiceActive, toggleVoice, toggleMute, submitText};
}
