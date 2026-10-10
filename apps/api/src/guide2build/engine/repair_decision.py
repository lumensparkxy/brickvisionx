"""Versioned assembly repair eligibility; unknown checks are never a repair trigger."""
from __future__ import annotations

from ..releases.models import digest
from .assembly_context import complete_groups, rigid_groups

VERSION = "actionable-assembly-repair-v2"
PROMPT = """An assembly repair is authorized only for the actionable defects in
assembly_repair_decision. Localize changes to its current snapshot/instance/group scope;
never rewrite accepted history. Preserve all remaining uncertainty and evidence. Camera
fit, unsupported metadata and generic uncertainty alone do not justify changing assembly
poses. A non-renderable or structurally invalid proposal may be rebuilt within this same
instruction and the existing attempt limit. Visual comparison and camera diagnosis still run.
If membership is uncertain, recover it from source before moving any member; the expanded
inventory scope is context, not permission to move unrelated pieces or treat it as one group.
"""
STRUCTURAL = {"historical_movement", "nonrigid_group", "exact_coincident_geometry",
              "symmetric_coincident_geometry", "occupied_connector", "sequence_contract_violation",
              "indexed_sequence_mismatch"}
DOMAINS = {"identity", "count", "colour", "placement", "grouping", "sequence", "coverage"}


def decide_repair(record, previous, *, attempts_used, max_attempts, calls_remaining):
    if (type(attempts_used) is not int or type(max_attempts) is not int
            or not 1 <= attempts_used <= max_attempts <= 2
            or type(calls_remaining) is not int or not 0 <= calls_remaining <= 1000):
        raise ValueError("Invalid bounded assembly repair decision inputs")
    candidate = record.get("candidate")
    steps = (candidate or {}).get("steps", [])
    fresh = steps[len((previous or {}).get("steps", [])):]
    step_ids = {step["step_id"] for step in fresh}
    known_ids = {part["instance_id"] for part in (candidate or {}).get("instances", [])}
    defects = {}
    localized = record.get("review_profile") == "localized-source-v4"
    items = [*record.get("findings", []), *(record.get("selected_quality") or {}).get("defects", []),
             *(record.get("visual_review") or {}).get("visible_defects", [])]
    if localized:
        from .localized_review import _observations, uncertainty_summary
        reviews = (record.get("selected_quality") or {}).get("review_observations")
        if reviews is None:
            reviews = [record["visual_review"]] if record.get("visual_review") else []
        # Grouped profiles reference original observations; use their authenticated
        # normalized subjects once, not those groups as additional repair votes.
        items = [item for item in items if item.get("code") in STRUCTURAL] + [
            dict(item, basis="agent_source_comparison") for item in _observations(reviews, step_ids)]
    # These are checked contract failures or typed source-visible discrepancies,
    # not interpretation of ambiguous prose, finding count, or camera residuals.
    for item in items:
        affected = set(item.get("step_ids", [])) | ({item["step_id"]} if item.get("step_id") else set())
        structural = item.get("code") in STRUCTURAL and item.get("severity") in {"error", "major"}
        visible = (item.get("domain") in DOMAINS and item.get("severity") in {"major", "minor"}
                   and (item.get("category") == "source_visible_defect"
                        or item.get("basis") == "agent_source_comparison"
                        or item in (record.get("visual_review") or {}).get("visible_defects", [])))
        if not (structural or visible) or not affected & step_ids:
            continue
        identities = set(item.get("instance_ids", []))
        if not identities <= known_ids:
            raise ValueError("Actionable repair names an unknown physical instance")
        defect = {"code": item.get("code", "source_visible_defect"), "domain": item.get("domain"),
            "basis": "deterministic_contract" if structural else "agent_source_comparison",
            "step_ids": sorted(affected & step_ids), "instance_ids": sorted(identities),
            "description": item.get("description", item.get("message", ""))}
        if localized and visible:
            possible = set(item.get("subject_candidates", []))
            if not possible <= known_ids or (item["localization"] != "identified" and identities):
                raise ValueError("Localized repair subject binding is inconsistent")
            defect.update(localization=item["localization"], severity=item["severity"], identified_instance_ids=sorted(identities),
                subject_candidates=sorted(possible), alternatives_are_not_all_defective=item["localization"] != "identified")
        defects[digest(defect)] = defect
    actionable = [defects[key] for key in sorted(defects)]
    renderable = bool(candidate) and bool(record.get("rendered"))
    reason = "no_renderable_proposal" if not renderable else "current_assembly_defect" if actionable else "no_actionable_assembly_defect"
    needed = not renderable or bool(actionable)
    if needed and attempts_used >= max_attempts:
        reason = "attempt_limit_reached"
    elif needed and not calls_remaining:
        reason = "model_call_budget_exhausted"
    identifiers = set().union(*(set(item["instance_ids"]) for item in actionable))
    identified = set(identifiers)
    alternatives = {}
    unlocalized = False
    if localized:
        for item in actionable:
            if item.get("localization") in {"one_of", "unlocalized"}:
                value = {"domain": item["domain"], "step_ids": item["step_ids"],
                    "localization": item["localization"], "severity": item["severity"], "possible_instance_ids": item["subject_candidates"]}
                alternatives[digest(value)] = value
                identifiers.update(item["subject_candidates"])
                unlocalized |= item["localization"] == "unlocalized"
    if needed and (not identifiers or unlocalized):
        identifiers.update(identity for step in fresh for identity in [*step["introduced_instance_ids"], *step["active_instance_ids"]])
    groups, _, ambiguous = rigid_groups(steps)
    identifiers = complete_groups(identifiers, groups)
    if ambiguous and needed:
        # A partial inferred group is unsafe. Retain every possible member as
        # repair context without asserting they form one assembly or may all move.
        identifiers = set(known_ids)
    result = {"version": VERSION, "action": "repair" if needed and attempts_used < max_attempts and calls_remaining else "continue",
        "reason": reason, "repair_needed": needed, "attempts_used": attempts_used,
        "max_attempts": max_attempts, "calls_remaining_at_decision": calls_remaining,
        "previous_scene_sha256": digest(previous) if previous else None,
        "candidate_scene_sha256": digest(candidate) if candidate else None,
        "findings_sha256": digest(record.get("findings", [])),
        "quality_sha256": digest(record.get("selected_quality")),
        "actionable_defects": actionable,
        "scope": {"step_ids": sorted(step_ids), "instance_ids": sorted(identifiers),
                  "group_ids": sorted(group for group, members in groups.items() if members & identifiers),
                  "group_membership_uncertain": ambiguous, "history_edit_allowed": False,
                  "membership_scope": "full_inventory_conservative" if ambiguous and needed else "declared_complete_groups"},
        "remaining_findings": [{"index": i, "sha256": digest(item),
            "category": item.get("code", item.get("category", item.get("domain", "uncategorized")))}
            for i, item in enumerate(record.get("findings", []))],
        "remaining_findings_status": "retained_in_full_in_bound_trial_outcomes",
        "camera_and_visual_review": "unchanged", "physical_verification": "not_run"}

    if localized:
        quality = record.get("selected_quality") or {}
        contexts = quality.get("review_context_omissions", [record["review_context_summary"]] if record.get("review_context_summary") else [])
        result["version"] = VERSION + "/validated-review-subjects-v4"
        result["scope"].update(identified_instance_ids=sorted(identified),
            alternative_subjects=[alternatives[key] for key in sorted(alternatives)],
            unlocalized_subjects=unlocalized, scope_members_are_not_all_defective=True,
            unresolved_evidence=uncertainty_summary(reviews, step_ids),
            review_context_complete=quality.get("review_context_complete", record.get("review_context_complete", False)),
            review_context_omissions=contexts[:6], omitted_review_context_summaries=max(0, len(contexts) - 6),
            defect_count_scope=quality.get("defect_count_scope", "Subject incidence and unresolved lower bounds; not a clean-assembly certificate"))
    return result
