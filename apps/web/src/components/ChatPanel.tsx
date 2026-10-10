import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type FormEvent, type PointerEvent } from 'react';
import IconSparkles from '@tabler/icons-react/dist/esm/icons/IconSparkles.mjs';
import IconMicrophone from '@tabler/icons-react/dist/esm/icons/IconMicrophone.mjs';
import IconSend2 from '@tabler/icons-react/dist/esm/icons/IconSend2.mjs';
import IconVolume from '@tabler/icons-react/dist/esm/icons/IconVolume.mjs';
import IconVolumeOff from '@tabler/icons-react/dist/esm/icons/IconVolumeOff.mjs';
import IconMessageChatbot from '@tabler/icons-react/dist/esm/icons/IconMessageChatbot.mjs';
import IconMinus from '@tabler/icons-react/dist/esm/icons/IconMinus.mjs';
import { askAgent, buddyContext, describeAction, isMuted, listen, onNarration, onVoiceChange, runAction, setMuted, setVoice, speak, stopListening, stopSpeaking,
  TALK_EVENT, type BuddyAction, type ChatTurn } from '../agent';
import { MIC_LEVEL_EVENT } from '../gradiumVoice';
import './chat.css';

interface Message extends ChatTurn { actions?: BuddyAction[]; narration?: boolean; error?: boolean; }
const IN_TUTORIAL = ['Take me to step 5', 'Walk me through the next 3 steps', 'Spin it around'];
const ELSEWHERE = ['Show me the plane', 'Which sets do you have?'];
/** Hands-free mode turns itself off after this long without hearing anything. */
const IDLE_OFF_MS = 120_000;

// The dock is anchored by its bottom-right corner, so the launcher and the open panel share one position.
interface Anchor { right: number; bottom: number; }
const DOCK_KEY = 'brickvisionx:dock', DEFAULT_ANCHOR: Anchor = { right: 24, bottom: 124 }, MARGIN = 8;
function savedAnchor(): Anchor {
  try { const value = JSON.parse(localStorage.getItem(DOCK_KEY) ?? 'null') as Anchor | null;
    if (value && Number.isFinite(value.right) && Number.isFinite(value.bottom)) return { right: value.right, bottom: value.bottom }; } catch { /* Fall back to the default corner. */ }
  return DEFAULT_ANCHOR;
}
const clampAnchor = (anchor: Anchor, width: number, height: number): Anchor => ({
  right: Math.round(Math.min(Math.max(MARGIN, anchor.right), Math.max(MARGIN, window.innerWidth - width - MARGIN))),
  bottom: Math.round(Math.min(Math.max(MARGIN, anchor.bottom), Math.max(MARGIN, window.innerHeight - height - MARGIN))),
});

/** BrickBuddy: one chat + voice assistant for the whole app, in a dock that can be moved and minimized. */
export default function ChatPanel() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false); const [listening, setListening] = useState(false);
  const [handsFree, setHandsFree] = useState(false);
  const [silent, setSilent] = useState(isMuted);
  const [anchor, setAnchor] = useState(savedAnchor);
  const list = useRef<HTMLDivElement>(null); const input = useRef<HTMLInputElement>(null); const dock = useRef<HTMLDivElement>(null);
  const history = useRef<Message[]>([]); const turn = useRef(0); const thinking = useRef(false);
  const append = (message: Message) => { history.current = [...history.current, message]; setMessages(history.current); };
  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || thinking.current) return;
    const mine = ++turn.current;
    stopSpeaking(); setOpen(true); setDraft('');
    void runAction({ type: 'stop' }); // A new request ends any walkthrough still playing.
    append({ role: 'user', text });
    // Only send turns the API accepts (non-empty, bounded), or one odd reply would poison every later request.
    const turns = history.current.filter(m => !m.error && m.text.trim()).map(({ role, text }) => ({ role, text: text.slice(0, 2000) })).slice(-14);
    thinking.current = true; setBusy(true);
    try {
      const result = await askAgent(turns, buddyContext());
      if (turn.current !== mine) return; // Superseded: drop the stale answer.
      thinking.current = false; setBusy(false);
      const reply = result.reply.trim() || (result.actions.length ? 'On it!' : 'Sorry, I did not catch that. Could you say it again?');
      append({ role: 'assistant', text: reply, actions: result.actions });
      const act = async () => {
        for (const action of result.actions) {
          if (turn.current !== mine) return;
          try { await runAction(action); }
          catch (error) { append({ role: 'assistant', text: error instanceof Error ? error.message : 'That did not work.', error: true }); return; }
        }
      };
      // A narrated walkthrough speaks per step, so the intro line goes first; otherwise talk while acting.
      if (result.actions.some(action => action.type === 'play_steps')) { await speak(reply); await act(); }
      else await Promise.all([speak(reply), act()]);
    } catch (error) {
      if (turn.current === mine) append({ role: 'assistant', text: error instanceof Error ? error.message : 'Something went wrong. Please try again.', error: true });
    } finally { if (turn.current === mine) { thinking.current = false; setBusy(false); } } // An older turn must not unlock a newer one.
  };
  const sendRef = useRef(send); sendRef.current = send;

  // Hands-free conversation: listen, answer, and listen again once BrickBuddy (and any walkthrough) has finished,
  // until the mic is tapped off. The microphone is never open while BrickBuddy is speaking.
  const talking = useRef(false); const hearing = useRef(false);
  const converse = async () => {
    if (talking.current) return;
    talking.current = true; setHandsFree(true); setOpen(true);
    let lastHeard = Date.now(), first = true;
    try {
      while (talking.current) {
        stopSpeaking(); hearing.current = true; setListening(true);
        let heard = ''; let failure: Error | null = null;
        try { heard = (await listen(setDraft)).trim(); }
        catch (error) { failure = error instanceof Error ? error : new Error('Voice input failed.'); }
        finally { hearing.current = false; setListening(false); setDraft(''); }
        // A quiet room can look like a silent microphone; only treat that as a problem on the very first try.
        if (failure && (first || !/only hear silence/.test(failure.message))) { append({ role: 'assistant', text: failure.message, error: true }); break; }
        first = false;
        if (heard) { lastHeard = Date.now(); await sendRef.current(heard); }
        else if (Date.now() - lastHeard > IDLE_OFF_MS) { append({ role: 'assistant', text: 'I will stop listening for now. Tap the mic whenever you need me.' }); break; }
      }
    } finally { talking.current = false; setHandsFree(false); }
  };
  const converseRef = useRef(converse); converseRef.current = converse;
  const tapMic = () => {
    if (!talking.current) { void converse(); return; }
    if (hearing.current) { talking.current = false; stopListening(); return; } // Off; whatever was heard is still sent.
    stopSpeaking(); void runAction({ type: 'stop' }); // Tap while BrickBuddy talks: interrupt, then it listens again.
  };
  useEffect(() => { const start = () => void converseRef.current(); window.addEventListener(TALK_EVENT, start); return () => window.removeEventListener(TALK_EVENT, start); }, []);
  // Unmount: stop the mic and the voice, and invalidate any answer still on its way.
  useEffect(() => () => { turn.current++; talking.current = false; stopListening(); stopSpeaking(); }, []);
  // The mic button swells with the input level, so it is obvious whether sound is arriving.
  const mic = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const show = (event: Event) => mic.current?.style.setProperty('--level', String(Math.min(1, (event as CustomEvent<number>).detail * 4)));
    window.addEventListener(MIC_LEVEL_EVENT, show); return () => window.removeEventListener(MIC_LEVEL_EVENT, show);
  }, []);
  useEffect(() => onNarration(text => append({ role: 'assistant', text, narration: true })), []);
  useEffect(() => onVoiceChange(() => setSilent(isMuted())), []);
  useEffect(() => { list.current?.scrollTo({ top: list.current.scrollHeight, behavior: 'smooth' }); }, [messages, busy, open]);
  useEffect(() => { if (open && !talking.current) input.current?.focus(); }, [open]);
  // Integration surface for scripts and for debugging from the console.
  useEffect(() => {
    const scope = window as unknown as { brickvision?: unknown };
    scope.brickvision = { send: (text: string) => sendRef.current(text), run: runAction, talk: () => converseRef.current(),
      context: () => { const context = buddyContext(); return { ...(context.viewer ?? {}), app: context.app }; },
      setVoice, speak, stop: stopSpeaking, listen, stopListening, open: () => setOpen(true) };
    return () => { delete scope.brickvision; };
  }, []);

  // Moving the dock: drag the header (or the launcher); it stays inside the window and remembers its place.
  const drag = useRef<{ x: number; y: number; from: Anchor; moved: boolean } | null>(null);
  const fit = (next: Anchor) => { const box = dock.current?.getBoundingClientRect(); return box ? clampAnchor(next, box.width, box.height) : next; };
  const startDrag = (event: PointerEvent<HTMLElement>) => {
    if (event.button !== 0 || (event.currentTarget.tagName !== 'BUTTON' && (event.target as HTMLElement).closest('button'))) return;
    drag.current = { x: event.clientX, y: event.clientY, from: anchor, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const moveDrag = (event: PointerEvent<HTMLElement>) => {
    const start = drag.current; if (!start) return;
    const dx = event.clientX - start.x, dy = event.clientY - start.y;
    if (!start.moved && Math.hypot(dx, dy) < 5) return;
    start.moved = true; setAnchor(fit({ right: start.from.right - dx, bottom: start.from.bottom - dy }));
  };
  const endDrag = (event: PointerEvent<HTMLElement>): boolean => {
    const start = drag.current; drag.current = null;
    if (!start) return false;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (start.moved) { try { localStorage.setItem(DOCK_KEY, JSON.stringify(anchor)); } catch { /* Position is kept for this visit only. */ } }
    return start.moved;
  };
  const dragged = useRef(false); // A drag that ends on the launcher must not also toggle it.
  useLayoutEffect(() => { const next = fit(anchor); if (next.right !== anchor.right || next.bottom !== anchor.bottom) setAnchor(next); });
  useEffect(() => { const refit = () => setAnchor(current => fit(current)); window.addEventListener('resize', refit); return () => window.removeEventListener('resize', refit); }, []);

  // While listening the draft is the live transcript: Enter ends the turn, which sends it once.
  const submit = (event: FormEvent) => { event.preventDefault(); if (hearing.current) stopListening(); else void send(draft); };
  const inTutorial = buddyContext().viewer !== null;
  const status = listening ? 'Listening… just talk' : busy ? 'Thinking…' : handsFree ? 'Speaking… tap the mic to interrupt'
    : inTutorial ? 'Ask me to move, explain or spin the model' : 'Tell me what you want to build';
  const micLabel = !handsFree ? 'Talk to BrickBuddy' : listening ? 'Stop listening' : 'Interrupt BrickBuddy';
  const place = { '--dock-right': `${anchor.right}px`, '--dock-bottom': `${anchor.bottom}px` } as CSSProperties;
  return <div ref={dock} style={place} className={`buddy${open ? ' open' : ''}${handsFree ? ' hands-free' : ''}`}>
    {open && <section className="buddy-panel" aria-label="Build buddy chat">
      <header className="buddy-header" title="Drag to move" onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}>
        <span className="buddy-avatar" aria-hidden="true"><IconSparkles size={20}/></span>
        <div className="buddy-title"><strong>BrickBuddy</strong><small role="status">{status}</small></div>
        <button type="button" className={`buddy-icon${silent ? ' voice-off' : ''}`} aria-pressed={!silent} aria-label={silent ? 'Turn voice on' : 'Turn voice off'} title={silent ? 'Turn voice on' : 'Turn voice off'} onClick={() => setMuted(!silent)}>{silent ? <><IconVolumeOff size={17}/>Voice off</> : <IconVolume size={19}/>}</button>
        <button type="button" className="buddy-icon" aria-label="Minimize chat" title="Minimize" onClick={() => setOpen(false)}><IconMinus size={19}/></button>
      </header>
      <div className="buddy-messages" ref={list} aria-live="polite">
        {messages.length === 0 && <div className="buddy-empty"><p>{inTutorial ? 'Hi! I can drive the 3D model while your hands are busy. Try:' : 'Hi! Tell me what you want to build and I will open it. Try:'}</p>{(inTutorial ? IN_TUTORIAL : ELSEWHERE).map(text => <button type="button" key={text} onClick={() => void send(text)}>{text}</button>)}</div>}
        {messages.map((message, i) => <div key={i} className={`buddy-msg ${message.role}${message.error ? ' error' : ''}${message.narration ? ' narration' : ''}`}>
          <p>{message.text}</p>
          {message.actions && message.actions.length > 0 && <div className="buddy-chips">{message.actions.map((action, k) => <span key={k}>{describeAction(action)}</span>)}</div>}
        </div>)}
        {busy && <div className="buddy-msg assistant typing" aria-label="BrickBuddy is thinking"><span/><span/><span/></div>}
      </div>
      <form className="buddy-form" onSubmit={submit}>
        <button ref={mic} type="button" className={`buddy-mic${listening ? ' live' : handsFree ? ' waiting' : ''}`} aria-pressed={handsFree} aria-label={micLabel} title={micLabel} onClick={tapMic}><IconMicrophone size={20}/></button>
        <input ref={input} value={draft} readOnly={listening} onChange={event => setDraft(event.target.value)} placeholder={listening ? 'Listening…' : 'Ask BrickBuddy…'} aria-label="Message BrickBuddy" autoComplete="off"/>
        <button type="submit" className="buddy-send" aria-label="Send" disabled={busy || !draft.trim()}><IconSend2 size={19}/></button>
      </form>
    </section>}
    <button type="button" className={`buddy-launcher${listening ? ' live' : ''}`} aria-expanded={open} aria-label={open ? 'Minimize build buddy' : 'Chat with your build buddy'} title="BrickBuddy · drag to move"
      onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={event => { dragged.current = endDrag(event); }} onPointerCancel={endDrag}
      onClick={() => { if (dragged.current) { dragged.current = false; return; } setOpen(value => !value); }}>{open ? <IconMinus size={26}/> : <IconMessageChatbot size={28}/>}</button>
  </div>;
}
