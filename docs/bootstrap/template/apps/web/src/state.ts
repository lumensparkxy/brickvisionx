import type { SceneManifest } from './contracts';
export function progressKey(scene: SceneManifest): string {
  return `guide2build:v1:${scene.set_number}:${scene.guide_id}:${scene.source_sha256}:${scene.revision}`;
}
export function clampStep(value: number, length: number): number {
  return Number.isFinite(value) ? Math.max(0, Math.min(Math.trunc(value), length - 1)) : 0;
}
export function readProgress(scene: SceneManifest): number {
  try { return clampStep(Number(localStorage.getItem(progressKey(scene)) ?? 0), scene.steps.length); }
  catch { return 0; }
}
export function saveProgress(scene: SceneManifest, step: number): void {
  try { localStorage.setItem(progressKey(scene), String(step)); } catch { /* Storage may be unavailable. */ }
}
