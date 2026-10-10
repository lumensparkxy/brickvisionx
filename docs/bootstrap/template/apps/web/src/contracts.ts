// Kept aligned with Python contracts and packages/contracts/scene.schema.json.
// Codex should replace hand-maintenance with generated TypeScript during M1.
export interface Pose { position_ldu: [number, number, number]; quaternion_xyzw: [number, number, number, number]; }
export interface SourcePanel { page_index: number; bbox: [number, number, number, number]; source_sha256: string; }
export interface PartInstance {
  instance_id: string; part_id: string; color_code: string; geometry_ref: string;
  source: SourcePanel; origin: 'vision_proposal' | 'pdf_assisted_authoring' | 'human_correction';
  mapping_status: 'candidate' | 'agent_reviewed' | 'human_reviewed';
}
export interface StepSnapshot {
  step_id: string; main_step_number: number; substep_label: string | null; instruction: string;
  source: SourcePanel; introduced_instance_ids: string[]; active_instance_ids: string[];
  visible_instance_ids: string[]; poses: Record<string, Pose>;
  action: 'add_parts' | 'build_subassembly' | 'attach_subassembly' | 'inspect'; assembly_group_id: string | null;
}
export interface SceneManifest {
  schema_version: '1.0'; set_number: string; guide_id: string; revision: string;
  source_sha256: string; coordinate_system: 'right_handed_y_up_ldu';
  status: 'candidate' | 'needs_review' | 'agent_reviewed' | 'human_reviewed';
  geometry_check: 'not_run' | 'pass' | 'fail'; connector_check: 'not_run' | 'pass' | 'fail';
  physical_build_check: 'not_run' | 'pass' | 'fail';
  instances: PartInstance[]; steps: StepSnapshot[];
  reviews: { actor_type: 'agent' | 'human'; actor_id: string; reviewed_revision: string;
    evidence_paths: string[]; decision: 'accepted' | 'changes_requested'; recorded_at: string }[];
}
export interface Guide { guide_id: string; label: string; pdf_url: string; expected_main_steps: number; }
export interface SetInfo { set_number: string; name: string; official_page: string; guides: Guide[]; }
