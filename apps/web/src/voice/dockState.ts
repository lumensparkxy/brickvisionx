import { useSyncExternalStore } from 'react';

/** Shared by every dock instance (booklet dialog, viewer), so moving or minimizing it survives navigation. */
export interface DockPosition { x: number; y: number }
export interface DockState { minimized: boolean; position: DockPosition | null }

const KEY = 'guide2build.voiceDock';
const MARGIN = 8;
const listeners = new Set<() => void>();

function validPosition(value: unknown): value is DockPosition {
  const item = value as DockPosition | null;
  return !!item && Number.isFinite(item.x) && Number.isFinite(item.y);
}

function load(): DockState {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? 'null');
    if (typeof value?.minimized === 'boolean') return {minimized: value.minimized, position: validPosition(value.position) ? value.position : null};
  } catch { /* unreadable storage falls back to defaults */ }
  return {minimized: true, position: null};
}

let state: DockState = typeof window === 'undefined' ? {minimized: true, position: null} : load();

export function setDockState(patch: Partial<DockState>, persist = true) {
  state = {...state, ...patch};
  if (persist) { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* private mode: keep in memory */ } }
  listeners.forEach(listener => listener());
}

export function useDockState(): DockState {
  return useSyncExternalStore(listener => { listeners.add(listener); return () => { listeners.delete(listener); }; }, () => state, () => state);
}

export function clampPosition(x: number, y: number, width: number, height: number): DockPosition {
  return {
    x: Math.round(Math.min(Math.max(MARGIN, x), Math.max(MARGIN, window.innerWidth - width - MARGIN))),
    y: Math.round(Math.min(Math.max(MARGIN, y), Math.max(MARGIN, window.innerHeight - height - MARGIN))),
  };
}
