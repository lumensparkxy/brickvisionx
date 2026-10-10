import { useEffect, useRef, useState, type FormEvent, type RefObject } from 'react';
import IconSparkles from '@tabler/icons-react/dist/esm/icons/IconSparkles.mjs';
import IconMicrophone from '@tabler/icons-react/dist/esm/icons/IconMicrophone.mjs';
import IconSend2 from '@tabler/icons-react/dist/esm/icons/IconSend2.mjs';
import IconVolume from '@tabler/icons-react/dist/esm/icons/IconVolume.mjs';
import IconVolumeOff from '@tabler/icons-react/dist/esm/icons/IconVolumeOff.mjs';
import IconMessageChatbot from '@tabler/icons-react/dist/esm/icons/IconMessageChatbot.mjs';
import IconX from '@tabler/icons-react/dist/esm/icons/IconX.mjs';
import { askAgent, describeAction, isMuted, listen, onNarration, onVoiceChange, setMuted, setVoice, speak, stopSpeaking,
  type ChatTurn, type ViewerAction, type ViewerController } from '../agent';
import './chat.css';

interface Message extends ChatTurn { actions?: ViewerAction[]; narration?: boolean; error?: boolean; }
const SUGGESTIONS = ['Take me to step 5', 'Walk me through the next 3 steps', 'Spin it around'];

export default function ChatPanel({ controller }: { controller: RefObject<ViewerController> }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false); const [listening, setListening] = useState(false);
  const [silent, setSilent] = useState(isMuted);
  const list = useRef<HTMLDivElement>(null); const input = useRef<HTMLInputElement>(null);
  const history = useRef<Message[]>([]); const turn = useRef(0); const thinking = useRef(false);
  const append = (message: Message) => { history.current = [...history.current, message]; setMessages(history.current); };
  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || thinking.current) return;
    const mine = ++turn.current;
    stopSpeaking(); setOpen(true); setDraft('');
    append({ role: 'user', text });
    const turns = history.current.filter(m => !m.error).map(({ role, text }) => ({ role, text })).slice(-14);
    thinking.current = true; setBusy(true);
    try {
      const result = await askAgent(turns, controller.current.context());
      thinking.current = false; setBusy(false);
      append({ role: 'assistant', text: result.reply, actions: result.actions });
      const act = async () => { for (const action of result.actions) { if (turn.current !== mine) return; await controller.current.run(action); } };
      // A narrated walkthrough speaks per step, so the intro line goes first; otherwise talk while acting.
      if (result.actions.some(action => action.type === 'play_steps')) { await speak(result.reply); await act(); }
      else await Promise.all([speak(result.reply), act()]);
    } catch (error) {
      append({ role: 'assistant', text: error instanceof Error ? error.message : 'Something went wrong. Please try again.', error: true });
    } finally { thinking.current = false; setBusy(false); }
  };
  const sendRef = useRef(send); sendRef.current = send;
  const talk = async () => {
    if (listening || busy) return;
    stopSpeaking(); setListening(true);
    try { const heard = await listen(); if (heard) await send(heard); }
    catch (error) { append({ role: 'assistant', text: error instanceof Error ? error.message : 'Voice input failed.', error: true }); }
    finally { setListening(false); }
  };
  useEffect(() => onNarration(text => append({ role: 'assistant', text, narration: true })), []);
  useEffect(() => onVoiceChange(() => setSilent(isMuted())), []);
  useEffect(() => { list.current?.scrollTo({ top: list.current.scrollHeight, behavior: 'smooth' }); }, [messages, busy, open]);
  useEffect(() => { if (open) input.current?.focus(); }, [open]);
  // Integration surface for the voice front end and for debugging from the console.
  useEffect(() => {
    const scope = window as unknown as { brickvision?: unknown };
    scope.brickvision = { send: (text: string) => sendRef.current(text), run: (action: ViewerAction) => controller.current.run(action),
      context: () => controller.current.context(), setVoice, speak, stop: stopSpeaking, open: () => setOpen(true) };
    return () => { delete scope.brickvision; };
  }, [controller]);
  const submit = (event: FormEvent) => { event.preventDefault(); void send(draft); };
  return <div className={`buddy${open ? ' open' : ''}`}>
    {open && <section className="buddy-panel" aria-label="Build buddy chat">
      <header className="buddy-header">
        <span className="buddy-avatar" aria-hidden="true"><IconSparkles size={20}/></span>
        <div className="buddy-title"><strong>BrickBuddy</strong><small role="status">{busy ? 'Thinking…' : listening ? 'Listening…' : 'Ask me to move, explain or spin the model'}</small></div>
        <button type="button" className="buddy-icon" aria-pressed={!silent} aria-label={silent ? 'Turn voice on' : 'Turn voice off'} title={silent ? 'Turn voice on' : 'Turn voice off'} onClick={() => setMuted(!silent)}>{silent ? <IconVolumeOff size={19}/> : <IconVolume size={19}/>}</button>
        <button type="button" className="buddy-icon" aria-label="Close chat" title="Close chat" onClick={() => setOpen(false)}><IconX size={19}/></button>
      </header>
      <div className="buddy-messages" ref={list} aria-live="polite">
        {messages.length === 0 && <div className="buddy-empty"><p>Hi! I can drive the 3D model while your hands are busy. Try:</p>{SUGGESTIONS.map(text => <button type="button" key={text} onClick={() => void send(text)}>{text}</button>)}</div>}
        {messages.map((message, i) => <div key={i} className={`buddy-msg ${message.role}${message.error ? ' error' : ''}${message.narration ? ' narration' : ''}`}>
          <p>{message.text}</p>
          {message.actions && message.actions.length > 0 && <div className="buddy-chips">{message.actions.map((action, k) => <span key={k}>{describeAction(action)}</span>)}</div>}
        </div>)}
        {busy && <div className="buddy-msg assistant typing" aria-label="BrickBuddy is thinking"><span/><span/><span/></div>}
      </div>
      <form className="buddy-form" onSubmit={submit}>
        <button type="button" className={`buddy-mic${listening ? ' live' : ''}`} aria-label={listening ? 'Listening' : 'Talk to BrickBuddy'} title="Talk to BrickBuddy" disabled={busy} onClick={() => void talk()}><IconMicrophone size={20}/></button>
        <input ref={input} value={draft} onChange={event => setDraft(event.target.value)} placeholder="Ask BrickBuddy…" aria-label="Message BrickBuddy" autoComplete="off"/>
        <button type="submit" className="buddy-send" aria-label="Send" disabled={busy || !draft.trim()}><IconSend2 size={19}/></button>
      </form>
    </section>}
    <button type="button" className="buddy-launcher" aria-expanded={open} aria-label={open ? 'Hide build buddy' : 'Chat with your build buddy'} title="BrickBuddy" onClick={() => setOpen(value => !value)}>{open ? <IconX size={26}/> : <IconMessageChatbot size={28}/>}</button>
  </div>;
}
