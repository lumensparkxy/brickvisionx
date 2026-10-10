import { useEffect, useRef, useState, type FormEvent, type RefObject } from 'react';
import IconSparkles from '@tabler/icons-react/dist/esm/icons/IconSparkles.mjs';
import IconMicrophone from '@tabler/icons-react/dist/esm/icons/IconMicrophone.mjs';
import IconSend2 from '@tabler/icons-react/dist/esm/icons/IconSend2.mjs';
import IconVolume from '@tabler/icons-react/dist/esm/icons/IconVolume.mjs';
import IconVolumeOff from '@tabler/icons-react/dist/esm/icons/IconVolumeOff.mjs';
import IconMessageChatbot from '@tabler/icons-react/dist/esm/icons/IconMessageChatbot.mjs';
import IconX from '@tabler/icons-react/dist/esm/icons/IconX.mjs';
import { askAgent, describeAction, isMuted, listen, onNarration, onVoiceChange, setMuted, setVoice, speak, stopListening, stopSpeaking,
  type ChatTurn, type ViewerAction, type ViewerController } from '../agent';
import { MIC_LEVEL_EVENT } from '../gradiumVoice';
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
    void controller.current.run({ type: 'stop' }); // A new request ends any walkthrough still playing.
    append({ role: 'user', text });
    // Only send turns the API accepts (non-empty, bounded), or one odd reply would poison every later request.
    const turns = history.current.filter(m => !m.error && m.text.trim()).map(({ role, text }) => ({ role, text: text.slice(0, 2000) })).slice(-14);
    thinking.current = true; setBusy(true);
    try {
      const result = await askAgent(turns, controller.current.context());
      if (turn.current !== mine) return; // Superseded, or the viewer was closed: drop the stale answer.
      thinking.current = false; setBusy(false);
      const reply = result.reply.trim() || (result.actions.length ? 'On it!' : 'Sorry, I did not catch that. Could you say it again?');
      append({ role: 'assistant', text: reply, actions: result.actions });
      const act = async () => { for (const action of result.actions) { if (turn.current !== mine) return; await controller.current.run(action); } };
      // A narrated walkthrough speaks per step, so the intro line goes first; otherwise talk while acting.
      if (result.actions.some(action => action.type === 'play_steps')) { await speak(reply); await act(); }
      else await Promise.all([speak(reply), act()]);
    } catch (error) {
      if (turn.current === mine) append({ role: 'assistant', text: error instanceof Error ? error.message : 'Something went wrong. Please try again.', error: true });
    } finally { if (turn.current === mine) { thinking.current = false; setBusy(false); } } // An older turn must not unlock a newer one.
  };
  const sendRef = useRef(send); sendRef.current = send;
  // Mic toggle: tap to talk, tap again (or just stop talking) to send what was heard.
  const hearing = useRef(false);
  const talk = async () => {
    if (hearing.current) { stopListening(); return; }
    if (thinking.current) return;
    stopSpeaking(); // BrickBuddy's own voice must not be transcribed.
    hearing.current = true; setListening(true);
    let heard = '';
    try { heard = (await listen(setDraft)).trim(); }
    catch (error) { append({ role: 'assistant', text: error instanceof Error ? error.message : 'Voice input failed.', error: true }); }
    finally { hearing.current = false; setListening(false); setDraft(''); }
    if (heard) await send(heard);
  };
  // Leaving the viewer: stop the mic and the voice, and invalidate any answer still on its way.
  useEffect(() => () => { turn.current++; stopListening(); stopSpeaking(); }, []);
  // The mic button swells with the input level, so it is obvious whether sound is arriving.
  const mic = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const show = (event: Event) => mic.current?.style.setProperty('--level', String(Math.min(1, (event as CustomEvent<number>).detail * 4)));
    window.addEventListener(MIC_LEVEL_EVENT, show); return () => window.removeEventListener(MIC_LEVEL_EVENT, show);
  }, []);
  useEffect(() => onNarration(text => append({ role: 'assistant', text, narration: true })), []);
  useEffect(() => onVoiceChange(() => setSilent(isMuted())), []);
  useEffect(() => { list.current?.scrollTo({ top: list.current.scrollHeight, behavior: 'smooth' }); }, [messages, busy, open]);
  useEffect(() => { if (open) input.current?.focus(); }, [open]);
  // Integration surface for the voice front end and for debugging from the console.
  useEffect(() => {
    const scope = window as unknown as { brickvision?: unknown };
    scope.brickvision = { send: (text: string) => sendRef.current(text), run: (action: ViewerAction) => controller.current.run(action),
      context: () => controller.current.context(), setVoice, speak, stop: stopSpeaking, listen, stopListening, open: () => setOpen(true) };
    return () => { delete scope.brickvision; };
  }, [controller]);
  // While listening the draft is the live transcript: Enter ends the turn, which sends it once.
  const submit = (event: FormEvent) => { event.preventDefault(); if (hearing.current) stopListening(); else void send(draft); };
  return <div className={`buddy${open ? ' open' : ''}`}>
    {open && <section className="buddy-panel" aria-label="Build buddy chat">
      <header className="buddy-header">
        <span className="buddy-avatar" aria-hidden="true"><IconSparkles size={20}/></span>
        <div className="buddy-title"><strong>BrickBuddy</strong><small role="status">{listening ? 'Listening… tap mic to send' : busy ? 'Thinking…' : 'Ask me to move, explain or spin the model'}</small></div>
        <button type="button" className={`buddy-icon${silent ? ' voice-off' : ''}`} aria-pressed={!silent} aria-label={silent ? 'Turn voice on' : 'Turn voice off'} title={silent ? 'Turn voice on' : 'Turn voice off'} onClick={() => setMuted(!silent)}>{silent ? <><IconVolumeOff size={17}/>Voice off</> : <IconVolume size={19}/>}</button>
        <button type="button" className="buddy-icon" aria-label="Close chat" title="Close chat" onClick={() => { stopListening(); setOpen(false); }}><IconX size={19}/></button>
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
        <button ref={mic} type="button" className={`buddy-mic${listening ? ' live' : ''}`} aria-pressed={listening} aria-label={listening ? 'Stop listening and send' : 'Talk to BrickBuddy'} title={listening ? 'Stop listening and send' : 'Talk to BrickBuddy'} disabled={busy && !listening} onClick={() => void talk()}><IconMicrophone size={20}/></button>
        <input ref={input} value={draft} readOnly={listening} onChange={event => setDraft(event.target.value)} placeholder={listening ? 'Listening…' : 'Ask BrickBuddy…'} aria-label="Message BrickBuddy" autoComplete="off"/>
        <button type="submit" className="buddy-send" aria-label="Send" disabled={busy || !draft.trim()}><IconSend2 size={19}/></button>
      </form>
    </section>}
    <button type="button" className="buddy-launcher" aria-expanded={open} aria-label={open ? 'Hide build buddy' : 'Chat with your build buddy'} title="BrickBuddy" onClick={() => { if (open) stopListening(); setOpen(value => !value); }}>{open ? <IconX size={26}/> : <IconMessageChatbot size={28}/>}</button>
  </div>;
}
