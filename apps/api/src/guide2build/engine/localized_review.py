"""Opt-in rendered-candidate subjects; observations are evidence, not truth.

No source retrieval, geometry, inference, pose mutation or persistent cache.
Legacy review/selection contracts live unchanged in exploration.py.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Literal

from pydantic import Field, model_validator

from ..core.models import StrictModel
from ..releases.models import canonical, digest
from .instruction import InstructionFinding

PROFILE = "localized-source-v4"
VERSION = "rendered-review-subjects-v4"
SELECTION_VERSION = "source-quality-localized-selection-v4"
UNCERTAINTY_VERSION = "capacity-one-unresolved-scope-v1"
LIMITS = {"instances": 128, "pose_rows": 512, "observations": 256, "bytes": 96_000}
PROMPT = """\nRendered candidate localization contract:
Each candidate's rendered_context binds its actual scene and image hashes. Its
instance IDs, source boxes and poses describe the candidate, not correct poses.
Use these physical IDs; do not invent names from an observation's spelling.
Observation mappings use equal source boxes only, not verified part identity.
For each visible defect, set localization to identified for a definite subject,
one_of for a genuinely ambiguous choice among supplied subjects, or unlocalized
when no supplied subject can be established. instance_ids and observation_ids
name the subject set; one_of does not claim every listed piece is defective.
If unlocalized, leave both lists empty and preserve the concrete observation.
Do not manufacture IDs to avoid uncertainty. Pose/source metadata does not prove
hidden engagement. Missing descriptor rows/observations mean partial coverage,
never a clean assembly; retain that limitation in findings. Describe separate
visible discrepancies, but do not paraphrase a complaint to create extra votes.
"""


class VisibleDefect(StrictModel):
    domain: Literal["identity", "count", "colour", "placement", "grouping", "sequence", "coverage"]
    severity: Literal["major", "minor"]
    step_ids: list[str] = Field(min_length=1, max_length=32)
    instance_ids: list[str] = Field(max_length=64)
    observation_ids: list[str] = Field(max_length=64)
    localization: Literal["identified", "one_of", "unlocalized"]
    description: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def localized_subject(self):
        for values in (self.step_ids, self.instance_ids, self.observation_ids):
            if len(values) != len(set(values)):
                raise ValueError("Review subject identifiers must be unique")
        empty = not self.instance_ids and not self.observation_ids
        if empty != (self.localization == "unlocalized"):
            raise ValueError("Unlocalized review observations must have no invented subject")
        return self


class CandidateReview(StrictModel):
    hypothesis_id: str = Field(min_length=1, max_length=120)
    coverage_agrees: bool
    assembly_agrees: bool
    findings: list[InstructionFinding] = Field(max_length=64)
    visible_defects: list[VisibleDefect] = Field(default_factory=list, max_length=64)


class CandidateComparison(StrictModel):
    selected_hypothesis_id: str | None
    reviews: list[CandidateReview] = Field(min_length=1, max_length=3)
    reason: str = Field(min_length=1, max_length=4000)


def normalize_profile(value="legacy"):
    if not isinstance(value, str) or value not in {"legacy", PROFILE}:
        raise ValueError("Unknown source review profile")
    return value


def binding():
    return {"name": PROFILE, "version": VERSION, "selection_version": SELECTION_VERSION,
            "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(), "limits": dict(LIMITS),
            "repair_scope_version": "validated-review-subjects-v4",
            "feedback_scope_version": "localized-review-omissions-v4",
            "uncertainty_preference_version": UNCERTAINTY_VERSION}


def describe(scene, step_ids, observations, frames, source_image):
    """Bound exact current rendered metadata; never silently claim full coverage."""
    if len(set(step_ids)) != len(step_ids) or not 1 <= len(step_ids) <= 20:
        raise ValueError("Review requires one to twenty distinct current snapshots")
    if len(scene["instances"]) > 8192 or len(observations) > 256:
        raise ValueError("Review input exceeds the existing scene/observation bound")
    if [frame["step_id"] for frame in frames] != list(step_ids):
        raise ValueError("Review frames must bind the exact rendered snapshot order")
    steps = {step["step_id"]: step for step in scene["steps"]}
    current = [steps[identity] for identity in step_ids]
    parts = {part["instance_id"]: part for part in scene["instances"]}
    visible = set().union(*(set(step["visible_instance_ids"]) for step in current))
    introduced = set().union(*(set(step["introduced_instance_ids"]) for step in current))
    active = set().union(*(set(step["active_instance_ids"]) for step in current))
    if not visible <= parts.keys():
        raise ValueError("Review snapshot refers to unknown physical instances")
    if any(step["source"][key] != source_image[key] for step in current for key in ("source_sha256", "page_index")):
        raise ValueError("Review snapshots must use the actual current source image")
    if any(set(step["poses"]) != set(step["visible_instance_ids"]) for step in current):
        raise ValueError("Review snapshot poses must match actual visibility")
    if any(item["source"][key] != source_image[key] for item in observations for key in ("source_sha256", "page_index")):
        raise ValueError("Review observations differ from the actual source image")
    observation_count, observation_digest = len(observations), digest(observations)
    by_observation = {}
    for item in observations:
        by_observation.setdefault(item["observation_id"], []).append(item)
    ambiguous_observations = sorted(identity for identity, items in by_observation.items()
                                    if len({digest(item["source"]) for item in items}) > 1)
    observations = [items[0] for identity, items in by_observation.items() if identity not in ambiguous_observations]
    for frame in frames:
        if (type(frame["image_index"]) is not int or not 1 <= frame["image_index"] < 64
                or not isinstance(frame["png_sha256"], str) or len(frame["png_sha256"]) != 64):
            raise ValueError("Review frame has an invalid image binding")
    ranked = sorted(visible, key=lambda identity: (identity not in introduced, identity not in active, identity))
    included, pose_rows = [], 0
    for identity in ranked:
        count = sum(identity in step["poses"] for step in current)
        if len(included) >= LIMITS["instances"] or pose_rows + count > LIMITS["pose_rows"]:
            continue
        included.append(identity)
        pose_rows += count
    associations = {item["observation_id"]: sorted(identity for identity in visible
                     if parts[identity]["source"] == item["source"]) for item in observations}
    selected_observations = sorted(observations, key=lambda item:
        (not bool(set(associations[item["observation_id"]]) & set(included)), item["observation_id"]))[:LIMITS["observations"]]
    scene_sha256 = digest(scene)

    def assemble():
        selected = set(included)
        payload = {"version": VERSION, "profile": PROFILE, "scene_sha256": scene_sha256,
            "source_image": deepcopy(source_image), "frames": deepcopy(frames),
            "instances": [{key: deepcopy(parts[identity][key]) for key in
                ("instance_id", "part_id", "color_code", "geometry_ref", "source")} for identity in included],
            "snapshots": [{**{key: deepcopy(step.get(key)) for key in
                ("step_id", "source", "action", "assembly_group_id")},
                **{key: [identity for identity in step[key] if identity in selected] for key in
                   ("introduced_instance_ids", "active_instance_ids", "visible_instance_ids")},
                "poses": {identity: deepcopy(pose) for identity, pose in step["poses"].items() if identity in selected},
                "omitted_visible_instances": len(set(step["visible_instance_ids"]) - selected)} for step in current],
            "observations": [{"observation_id": item["observation_id"], "source": deepcopy(item["source"]),
                "possible_instance_ids": [identity for identity in associations[item["observation_id"]] if identity in selected],
                "omitted_possible_instances": len(set(associations[item["observation_id"]]) - selected),
                "mapping_basis": "equal_source_box_not_identity_or_pose_validation"} for item in selected_observations],
            "coverage": {"visible_instances_total": len(visible), "included_instances": len(included),
                "omitted_instances": len(visible - selected), "omitted_instance_ids_sha256": digest(sorted(visible - selected)),
                "pose_rows_total": sum(len(step["poses"]) for step in current),
                "pose_rows_included": sum(len(set(step["poses"]) & selected) for step in current),
                "observations_total": observation_count, "included_observations": len(selected_observations),
                "omitted_observations": observation_count - len(selected_observations),
                "ambiguous_observation_ids": ambiguous_observations,
                "observations_input_sha256": observation_digest,
                "complete": len(visible) == len(included) and observation_count == len(selected_observations)},
            "limits": dict(LIMITS), "assembly_verified": False}
        return {**payload, "receipt_sha256": digest(payload)}

    value = assemble()
    while len(canonical(value)) > LIMITS["bytes"]:
        if len(selected_observations) > 8:
            selected_observations.pop()
        elif included:
            included.pop()
        elif selected_observations:
            selected_observations.pop()
        else:
            raise ValueError("Review fixed metadata exceeds the context resource bound")
        value = assemble()
    return value


def verify_descriptor(value):
    if (value.get("version") != VERSION or value.get("profile") != PROFILE
            or value.get("limits") != LIMITS or len(canonical(value)) > LIMITS["bytes"]
            or value.get("receipt_sha256") != digest({key: item for key, item in value.items() if key != "receipt_sha256"})):
        raise ValueError("Rendered review descriptor changed or exceeds its bound")


def coverage_summary(descriptor):
    """Bounded omissions travel with zero-defect and unavailable reviews too."""
    verify_descriptor(descriptor)
    coverage = descriptor["coverage"]
    return {"descriptor_sha256": descriptor["receipt_sha256"], "complete": coverage["complete"],
        **{key: coverage[key] for key in ("visible_instances_total", "included_instances", "omitted_instances",
                                        "pose_rows_total", "pose_rows_included", "omitted_observations")},
        "omitted_pose_rows": coverage["pose_rows_total"] - coverage["pose_rows_included"],
        "ambiguous_observation_ids_count": len(coverage["ambiguous_observation_ids"]),
        "scope": "Candidate metadata coverage only; neither visible-pixel coverage nor assembly correctness"}


def normalize_review(value, descriptor):
    """Validate model subjects, then derive deterministic keys from actual context."""
    verify_descriptor(descriptor)
    result = CandidateReview.model_validate(value).model_dump(mode="json")
    steps = {step["step_id"]: step for step in descriptor["snapshots"]}
    observations = {item["observation_id"]: item for item in descriptor["observations"]}
    for defect in result["visible_defects"]:
        if not set(defect["step_ids"]) <= steps.keys():
            raise ValueError("Visible defect names an unreviewed snapshot")
        known = set.intersection(*(set(steps[identity]["poses"]) for identity in defect["step_ids"]))
        if not set(defect["instance_ids"]) <= known or not set(defect["observation_ids"]) <= observations.keys():
            raise ValueError("Visible defect names an omitted or unknown review subject")
        subjects = set(defect["instance_ids"])
        for identity in defect["observation_ids"]:
            observation = observations[identity]
            possible = set(observation["possible_instance_ids"])
            if observation["omitted_possible_instances"] or not possible or not possible <= known:
                raise ValueError("Source observation cannot establish a complete visible physical subject")
            subjects.update(possible)
        if defect["localization"] == "one_of" and len(subjects) < 2:
            raise ValueError("Ambiguous subject requires at least two actual alternatives")
        if defect["localization"] == "identified" and any(
                len(observations[identity]["possible_instance_ids"]) > 1 for identity in defect["observation_ids"]):
            raise ValueError("A multiply mapped source observation cannot establish an identified subject")
        defect["subject_candidates"] = sorted(subjects)
        # Preserve raw provider identifiers in comparison.json and here; downstream
        # instance scope names only validated identified subjects, not alternatives.
        defect["reported_instance_ids"] = defect["instance_ids"]
        defect["instance_ids"] = sorted(subjects) if defect["localization"] == "identified" else []
        defect["localization_profile"] = PROFILE
        defect["identified_instance_ids"] = list(defect["instance_ids"])
        defect["review_context"] = coverage_summary(descriptor)
        if defect["localization"] != "identified":
            defect["alternatives"] = [{"kind": "review_subject", "instance_ids": sorted(subjects),
                "candidate_count": len(subjects), "localization": defect["localization"], "severity": defect["severity"],
                "meaning": "Alternatives for inspection; not all asserted defective or authorized to move"}]
            defect["uncertainties"] = ["The affected physical subject is not identified."]
    result["localization_receipt"] = {"profile": PROFILE, "version": VERSION,
        "descriptor_sha256": descriptor["receipt_sha256"], "coverage_complete": descriptor["coverage"]["complete"],
        "coverage": coverage_summary(descriptor)}
    return result


def _observations(reviews, step_ids):
    if len(reviews) > 6 or sum(len(review.get("visible_defects", [])) for review in reviews) > 384:
        raise ValueError("Localized comparison exceeds the retained review bound")
    items = {}
    for review in reviews:
        if review.get("localization_receipt", {}).get("profile") != PROFILE:
            raise ValueError("Localized selection lacks its validated subject binding")
        for value in review.get("visible_defects", []):
            affected = sorted(set(value["step_ids"]) & step_ids)
            if not affected:
                continue
            # The immutable raw reviews retain every descriptor binding. The same
            # subject observation in two equivalent render contexts is not a vote.
            item = {key: deepcopy(part) for key, part in value.items() if key != "review_context"}
            item["step_ids"] = affected
            for key in ("instance_ids", "reported_instance_ids", "identified_instance_ids", "observation_ids", "subject_candidates"):
                item[key] = sorted(item.get(key, []))
            items[digest(item)] = item
    return [items[key] for key in sorted(items)]


def _overlaps(item, other):
    return (item["domain"] == other["domain"] and bool(set(item["step_ids"]) & set(other["step_ids"]))
            and (not item["subject_candidates"] or not other["subject_candidates"]
                 or bool(set(item["subject_candidates"]) & set(other["subject_candidates"]))))


def _uncertain_scopes(values):
    """One witness per semantic scope, regardless of wording or repeat reviews."""
    scopes = {}
    for item in values:
        if item["localization"] == "identified":
            continue
        scope = {key: item[key] for key in ("domain", "step_ids", "subject_candidates", "localization")}
        key = digest(scope)
        if key not in scopes or item["severity"] == "major":
            scopes[key] = scope | {"severity": item["severity"]}
    return [scopes[key] for key in sorted(scopes)]


def uncertainty_summary(reviews, step_ids):
    """Explicit uncertain severity, separate from identified incidence and truth.

    Repeated wording and lower-severity descriptions of one subject scope do not
    create more votes. Keep the highest reported unresolved severity per scope.
    These scope counts describe supplied review evidence, not actual defects.
    """
    scopes = _uncertain_scopes(_observations(reviews, step_ids))
    counts = {domain: {"major": 0, "minor": 0} for domain in
              ("identity", "count", "colour", "placement", "grouping", "sequence", "coverage")}
    for item in scopes:
        counts[item["domain"]][item["severity"]] += 1
    return {"version": UNCERTAINTY_VERSION, "scope_count": len(scopes), "severity_scope_counts": counts,
        "scopes_sha256": digest(scopes),
        "highest_severity": "major" if any(item["severity"] == "major" for item in scopes) else "minor" if scopes else None,
        "count_basis": "Unresolved review subject scopes, not independent or verified defects",
        "uncertainty_may_overlap_identified_subjects": True}


def group_defects(reviews, step_ids):
    """Identified per-subject incidence is monotone under added uncertainty.

    Each identified physical subject is an anchor, not a counted prose variant.
    Multi-subject identified claims name each affected subject; this is subject
    incidence, not a number of independent mechanical faults. Ambiguous claims
    can be associated with several anchors but can never union their identities,
    change their identified severity, or count as another identified subject.
    Unanchored uncertainty remains a lower-bound group with all observations.
    """
    values = _observations(reviews, step_ids)
    anchors, uncertain = {}, []
    for item in values:
        if item["localization"] == "identified":
            for identity in item["subject_candidates"]:
                anchors.setdefault((item["domain"], identity), []).append(item)
        else:
            uncertain.append(item)
    groups = []
    attached = set()
    retained = set()

    def group(observations, identified, identity=None):
        observations = sorted({digest(item): item for item in observations}.values(), key=digest)
        precise = identified or observations
        shown = []
        for item in observations:
            key = digest(item)
            shown.append(item if key not in retained else {"observation_sha256": key, "retained_in_review_observations": True})
            retained.add(key)
        return {"domain": observations[0]["domain"],
            "severity": "major" if any(item["severity"] == "major" for item in precise) else "minor",
            "step_ids": sorted(set().union(*(set(item["step_ids"]) for item in precise))),
            "instance_ids": [identity] if identity else [], "identified_instance_ids": [identity] if identity else [],
            "observation_ids": sorted(set().union(*(set(item["observation_ids"]) for item in observations))),
            "subject_candidates": [identity] if identity else sorted(set().union(*(set(item["subject_candidates"]) for item in observations))),
            "basis": "agent_source_comparison", "description": observations[0]["description"] if len(observations) == 1
                else f"{len(observations)} retained source observations share a conservative discrepancy group; see observations.",
            "observations": shown, "observation_count": len(observations),
            "incidence": "identified_subject" if identity else "unlocalized_lower_bound",
            "localization_profile": PROFILE,
            "localization": "identified" if identity else "unlocalized" if any(not item["subject_candidates"] for item in observations) else "one_of",
            "localization_uncertainty": any(item["localization"] != "identified" for item in observations),
            "unresolved_severity": "major" if any(item["localization"] != "identified" and item["severity"] == "major" for item in observations)
                else "minor" if any(item["localization"] != "identified" for item in observations) else None,
            "count_basis": "identified_physical_subject_not_independent_fault" if identity else "one_group_lower_bound_not_wording_count",
            "alternatives": [{"observation_sha256": digest(item), "localization": item["localization"], "severity": item["severity"]}
                             for item in observations if item["localization"] != "identified"]}

    for (domain, identity), identified in sorted(anchors.items()):
        anchor = {"domain": domain, "step_ids": sorted(set().union(*(set(item["step_ids"]) for item in identified))),
                  "subject_candidates": [identity]}
        associations = [item for item in uncertain if _overlaps(anchor, item)]
        attached.update(digest(item) for item in associations)
        groups.append(group([*identified, *associations], identified, identity))
    # Unknown incidence may cover several unestablished subjects. It never gains
    # prose votes and cannot support superiority without preference_guard below.
    remaining = {}
    for item in uncertain:
        if digest(item) not in attached:
            remaining.setdefault(item["domain"], []).append(item)
    groups.extend(group(remaining[key], []) for key in sorted(remaining))
    return sorted(groups, key=digest)


def _uncertainty_guard(uncertain, old_uncertain):
    """A capacity-one matching is necessary, not proof of defect equivalence.

    Existing review limits bound each side at 384 scopes. An augmenting-path
    matcher avoids greedy/order-dependent refusals; its edges require both a
    compatible domain/step/subject scope and non-increasing reported severity.
    No old anonymous observation can supply two independent coverage witnesses.
    """
    edges = []
    for item in uncertain:
        # Identical or narrower alternative sets can be residual uncertainty;
        # a new anonymous/expanded set cannot justify reduced defect counts.
        covering = [index for index, old in enumerate(old_uncertain) if item["domain"] == old["domain"] and set(item["step_ids"]) <= set(old["step_ids"])
                   and (not old["subject_candidates"] or (item["subject_candidates"]
                        and set(item["subject_candidates"]) <= set(old["subject_candidates"])))]
        if not covering:
            return "less_localized_review_cannot_establish_superiority"
        compatible = [index for index in covering if old_uncertain[index]["severity"] == "major" or item["severity"] == "minor"]
        if not compatible:
            return "worsened_unresolved_severity_cannot_establish_superiority"
        edges.append(compatible)
    # Left scopes and right witnesses are already canonicalized and sorted.
    # Each old witness is consumed at most once, including after path reassignment.
    owners = {}
    for start in range(len(edges)):
        pending, parents, seen_old = [start], {}, set()
        index, endpoint = 0, None
        while index < len(pending) and endpoint is None:
            subject = pending[index]
            index += 1
            for witness in edges[subject]:
                if witness in seen_old:
                    continue
                seen_old.add(witness)
                parents[witness] = subject
                if witness not in owners:
                    endpoint = witness
                    break
                pending.append(owners[witness])
        if endpoint is None:
            return "distinct_unresolved_witnesses_required_for_superiority"
        while endpoint is not None:
            subject = parents[endpoint]
            previous = next((old for old in edges[subject] if owners.get(old) == subject), None)
            owners[endpoint] = subject
            if previous is not None:
                del owners[previous]
            endpoint = previous
    return None


def preference_guard(preferred, other):
    """A lower bound or broader subject uncertainty cannot establish superiority."""
    left = _observations(preferred["review_observations"], set(preferred["current_step_ids"]))
    right = _observations(other["review_observations"], set(other["current_step_ids"]))
    uncertain = _uncertain_scopes(left)
    reason = _uncertainty_guard(uncertain, _uncertain_scopes(right))
    if reason:
        return reason
    precise = {}
    for item in left:
        if item["localization"] == "identified":
            for identity in item["subject_candidates"]:
                for step in item["step_ids"]:
                    key = item["domain"], step, identity
                    precise[key] = max(precise.get(key, 0), 2 if item["severity"] == "major" else 1)
    for item in right:
        if item["localization"] != "identified":
            continue
        for identity in item["subject_candidates"]:
            for step in item["step_ids"]:
                if precise.get((item["domain"], step, identity), 0) < (2 if item["severity"] == "major" else 1):
                    missing = {"domain": item["domain"], "step_ids": [step], "subject_candidates": [identity]}
                    if any(_overlaps(missing, alternative) for alternative in uncertain):
                        return "unresolved_subject_can_explain_apparently_removed_defect"
    return None
