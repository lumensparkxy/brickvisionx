export interface ControlInfo { id: string; label: string; kind: 'button' | 'tab' | 'link' | 'toggle' }
export interface ControlSnapshot { controls: ControlInfo[]; elements: Map<string, HTMLElement> }

export const MAX_CONTROLS = 80;
const MAX_LABEL = 120;
const SELECTOR = 'button, [role="tab"], summary, a[href]';

function visible(element: HTMLElement): boolean {
  if (element.closest('[hidden]')) return false;
  return typeof element.checkVisibility === 'function' ? element.checkVisibility({visibilityProperty: true}) : true;
}

/** Same checks as when the control was listed; the page may have changed while Gemini was thinking. */
export function usable(element: HTMLElement): boolean {
  if (!element.isConnected || element.closest('[inert], .voice-chat')) return false;
  if ((element as HTMLButtonElement).disabled || element.getAttribute('aria-disabled') === 'true') return false;
  const modal = element.ownerDocument.querySelector('dialog[open]');
  return (!modal || modal.contains(element)) && visible(element);
}

function labelFor(element: HTMLElement): string {
  const text = element.getAttribute('aria-label') || element.textContent || element.getAttribute('title') || '';
  return text.replace(/\s+/g, ' ').trim().slice(0, MAX_LABEL);
}

function kindFor(element: HTMLElement): ControlInfo['kind'] {
  if (element.getAttribute('role') === 'tab') return 'tab';
  if (element.tagName === 'A') return 'link';
  if (element.tagName === 'SUMMARY' || element.hasAttribute('aria-pressed')) return 'toggle';
  return 'button';
}

export function collectControls(root: Document = document): ControlSnapshot {
  const scope = root.querySelector<HTMLElement>('dialog[open]') ?? root;
  const found = [...scope.querySelectorAll<HTMLElement>(SELECTOR)]
    .filter(usable).map(element => ({element, label: labelFor(element)})).filter(item => item.label);
  const counts = new Map<string, number>();
  for (const item of found) counts.set(item.label, (counts.get(item.label) ?? 0) + 1);
  const seen = new Map<string, number>();
  const controls: ControlInfo[] = [];
  const elements = new Map<string, HTMLElement>();
  for (const {element, label} of found.slice(0, MAX_CONTROLS)) {
    let name = label;
    if ((counts.get(label) ?? 0) > 1) {
      const context = element.closest<HTMLElement>('[data-voice-scope]')?.dataset.voiceScope;
      name = context ? `${label} (${context})` : label;
      const repeat = (seen.get(name) ?? 0) + 1;
      seen.set(name, repeat);
      if (repeat > 1) name = `${name} #${repeat}`;
    }
    const id = `c${controls.length + 1}`;
    controls.push({id, label: name.slice(0, 160), kind: kindFor(element)});
    elements.set(id, element);
  }
  return {controls, elements};
}
