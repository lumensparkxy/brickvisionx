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
export function partsList(scene: SceneManifest, ids?: string[]) {
  const selected = ids ? new Set(ids) : null;
  const groups = new Map<string, { partId: string; color: string; quantity: number }>();
  for (const part of scene.instances) {
    if (selected && !selected.has(part.instance_id)) continue;
    const key = `${part.part_id}:${part.color_code}`;
    const row = groups.get(key) ?? { partId: part.part_id, color: part.color_code, quantity: 0 };
    row.quantity++; groups.set(key, row);
  }
  return [...groups.values()].sort((a,b) => a.partId.localeCompare(b.partId) || a.color.localeCompare(b.color));
}
