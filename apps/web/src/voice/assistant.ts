import { post } from '../api';
import type { ControlInfo } from './controls';

export type AssistantAction =
  | {type: 'none'}
  | {type: 'find_set'; set_number: string}
  | {type: 'open_tutorial'; set_number: string; guide_id?: string}
  | {type: 'go_to_step'; step: number}
  | {type: 'click'; control_id: string}
  | {type: 'close_booklet' | 'go_home' | 'how_it_works' | 'next_step' | 'previous_step' | 'replay_step' | 'play_build'};

export interface StepCommand { type: 'next_step' | 'previous_step' | 'go_to_step' | 'replay_step' | 'play_build'; step?: number; token: number }
export interface StepContext { index: number; total: number; label: string; main_step_numbers: number[] }
export interface AssistantContext {
  screen: 'landing' | 'booklet' | 'tutorial';
  set_number?: string | null;
  guide_id?: string | null;
  guides?: {guide_id: string; label: string; tutorial_available: boolean}[];
  step?: StepContext | null;
  controls?: ControlInfo[];
}
export interface AssistantTurn { role: 'user' | 'assistant'; text: string }
export interface AssistantReply { text: string; action: AssistantAction }

const SIMPLE = new Set(['close_booklet', 'go_home', 'how_it_works', 'next_step', 'previous_step', 'replay_step', 'play_build']);
const SET_NUMBER = /^\d{4,7}$/;

/** The server validates actions too; the browser still refuses anything malformed. */
export function parseAction(value: unknown): AssistantAction {
  if (!value || typeof value !== 'object') return {type: 'none'};
  const action = value as Record<string, unknown>;
  const type = action.type;
  if (typeof type !== 'string') return {type: 'none'};
  if (SIMPLE.has(type)) return {type} as AssistantAction;
  if (type === 'find_set' && typeof action.set_number === 'string' && SET_NUMBER.test(action.set_number)) return {type, set_number: action.set_number};
  if (type === 'open_tutorial' && typeof action.set_number === 'string' && SET_NUMBER.test(action.set_number)) {
    return typeof action.guide_id === 'string' && /^[a-z0-9-]{1,64}$/.test(action.guide_id)
      ? {type, set_number: action.set_number, guide_id: action.guide_id} : {type, set_number: action.set_number};
  }
  if (type === 'click' && typeof action.control_id === 'string' && /^c\d{1,3}$/.test(action.control_id)) return {type, control_id: action.control_id};
  if (type === 'go_to_step' && Number.isInteger(action.step) && (action.step as number) > 0) return {type, step: action.step as number};
  return {type: 'none'};
}

export async function askAssistant(messages: AssistantTurn[], context: AssistantContext): Promise<AssistantReply> {
  const reply = await post<{text?: unknown; action?: unknown}>('/voice/reply', {messages, context});
  if (typeof reply.text !== 'string' || !reply.text.trim()) throw new Error('The assistant returned an empty reply.');
  return {text: reply.text, action: parseAction(reply.action)};
}

export function stepIndexFor(steps: {main_step_number: number | null}[], step: number): number {
  return steps.findIndex(item => item.main_step_number === step);
}
