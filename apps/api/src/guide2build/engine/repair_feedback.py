"""Deterministic, bounded prompt views of retained reconstruction findings.

This module neither resolves findings nor judges assembly correctness. The caller
must retain the original evidence; the returned detached JSON receipt identifies
that exact input and the prioritization context. Hashes use releases.models'
canonical UTF-8 JSON. ``receipt_sha256`` hashes every other receipt field.
"""
from __future__ import annotations

from collections import Counter
import math

from ..releases.models import canonical, digest


VERSION = "repair-feedback-v2"
PROMPT_VERSION = "repair-feedback-prompt-v1"
GROUPING_VERSION = "semantic-finding-with-scope-occurrences-v1"
MAX_GROUPS = 24
MAX_BYTES = 16 * 1024
MAX_INPUT_FINDINGS = 20_000
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_INPUT_NODES = 300_000
MAX_INPUT_DEPTH = 12
MAX_INPUT_STRING_CHARS = 128 * 1024
MAX_CONTEXT_IDS = 8192
MAX_GROUP_BYTES = 2304

_SCOPE_FIELDS = {"step_id", "step_ids", "instance_ids", "ordinal", "page_index", "inherited_from_job"}
_FIELD_ORDER = (
    "category", "code", "domain", "severity", "resolution", "reason", "description", "message",
    "correction", "alternatives", "uncertainties", "candidate_part_ids", "candidate_color_codes",
    "source", "observation_id", "origin", "basis", "scope", "feature", "nominal_mates", "workspace",
    "distance_ldu", "nominal_contact", "parts", "connectivity_basis", "alternative_selection_ids",
)
_SCOPES = ("current_step", "dependency", "unscoped", "historical")
_UNCERTAINTIES = ("explicit", "unverified_diagnostic", "not_classified")


class _JsonBudget:
    """Reject malformed/oversized data before hashing; never hash a sampled list."""

    def __init__(self, *, depth_allowance=0):
        self.nodes = 0
        self.bytes = 0
        self.active = set()
        self.max_depth = MAX_INPUT_DEPTH + depth_allowance

    def _charge(self, size):
        self.bytes += size
        if self.bytes > MAX_INPUT_BYTES:
            raise ValueError("Feedback input exceeds JSON byte limit")

    def copy(self, value, depth=0):
        self.nodes += 1
        if self.nodes > MAX_INPUT_NODES or depth > self.max_depth:
            raise ValueError("Feedback input exceeds node/depth limit")
        kind = type(value)
        if value is None or kind in (str, int, float, bool):
            if kind is str and len(value) > MAX_INPUT_STRING_CHARS:
                raise ValueError("Feedback input exceeds string limit")
            if kind is int and value.bit_length() > 256:
                raise ValueError("Feedback integers exceed supported range")
            if kind is float and not math.isfinite(value):
                raise ValueError("Feedback requires finite JSON numbers")
            try:
                self._charge(len(canonical(value)))
            except (UnicodeError, OverflowError) as error:
                raise ValueError("Feedback requires valid UTF-8 JSON") from error
            return value
        if kind not in (list, tuple, dict):
            raise ValueError("Feedback accepts plain JSON values only")
        identity = id(value)
        if identity in self.active:
            raise ValueError("Feedback input contains a cycle")
        self.active.add(identity)
        try:
            self._charge(2 + max(0, len(value) - 1))
            if kind in (list, tuple):
                return [self.copy(item, depth + 1) for item in value]
            result = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError("Feedback object keys must be strings")
                self.copy(key, depth + 1)
                self._charge(1)
                result[key] = self.copy(item, depth + 1)
            return result
        finally:
            self.active.remove(identity)


def _ids(values, name):
    if type(values) not in (list, tuple, set, frozenset) or len(values) > MAX_CONTEXT_IDS:
        raise ValueError(f"{name} requires at most {MAX_CONTEXT_IDS} explicit IDs")
    for value in values:
        if type(value) is not str or not value:
            raise ValueError(f"{name} must contain nonempty string IDs")
        try:
            length = len(value.encode("utf-8"))
        except UnicodeError as error:
            raise ValueError(f"{name} must contain valid UTF-8 IDs") from error
        if length > 512:
            raise ValueError(f"{name} ID exceeds 512 UTF-8 bytes")
    return set(values)


def _steps(value):
    result = _ids(value.get("step_ids", []) if value.get("step_ids") is not None else [], "finding.step_ids")
    if value.get("step_id") is not None:
        result.update(_ids([value["step_id"]], "finding.step_id"))
    return result


def _labels(value):
    return " ".join(value.get(key) or "" for key in ("category", "code", "domain")).lower()


def _kind(value):
    labels = _labels(value)
    if "aabb" in labels or "overlap_candidate" in labels or "broad_phase" in labels:
        return "broad_phase"
    if (value.get("category") in {"part", "material", "part_variant"}
            or any(word in labels for word in ("identity", "quantity", "quantities", "count", "colour", "color", "mapping", "missing_part"))):
        return "identity_or_quantity"
    if (value.get("category") == "side" or any(word in labels for word in
            ("exact_coincident", "duplicate", "floating", "group", "wrong_side", "historical_movement", "history", "sequence_contract", "indexed_sequence"))):
        return "structural_or_side"
    if value.get("category") == "source_visible_defect":
        return "source_visible_defect"
    if (value.get("category") == "connection" and value.get("instance_ids")
            and (value.get("step_id") or value.get("step_ids"))
            and type(value.get("correction")) is str and value["correction"].strip()
            and value["correction"].strip() != "Review the indicated official source and provisional reconstruction."):
        # Typed source-review guidance can identify a local repair without
        # asserting which inherited pose is wrong. Prioritization is not proof.
        return "source_connection_guidance"
    return "review_or_uncertainty"


def _uncertainty(value, kind):
    alternatives = value.get("candidate_part_ids")
    colours = value.get("candidate_color_codes")
    localized_unknown = value.get("localization_profile") == "localized-source-v4" and (
        value.get("localization") in {"one_of", "unlocalized"} or value.get("review_context", {}).get("complete") is False)
    if (localized_unknown or value.get("uncertainties") or value.get("alternatives")
            or (type(alternatives) is list and len(alternatives) > 1)
            or (type(colours) is dict and any(type(v) is list and len(v) > 1 for v in colours.values()))
            or any(word in _labels(value) for word in ("uncertain", "ambigu", "unsupported"))
            or value.get("severity") == "unsupported"):
        return "explicit"
    if kind == "broad_phase" or value.get("severity") == "review":
        return "unverified_diagnostic"
    return "not_classified"


def _category(value):
    return value.get("code") or value.get("category") or value.get("domain") or "uncategorized"


def _short(text, limit):
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text, 0
    return encoded[:max(0, limit - 3)].decode("utf-8", errors="ignore") + "…", 1


def _preview(value, text_bytes, items, depth=0):
    """Return a detached preview and number of shortened/omitted value slots."""
    if type(value) is str:
        return _short(value, text_bytes)
    if type(value) not in (list, dict):
        return value, 0
    if depth == 4:
        return None, 1
    if type(value) is list:
        result, trimmed = [], max(0, len(value) - items)
        for item in value[:items]:
            shown, count = _preview(item, text_bytes, items, depth + 1)
            result.append(shown)
            trimmed += count
        return result, trimmed
    keys = sorted(value, key=lambda key: (_FIELD_ORDER.index(key) if key in _FIELD_ORDER else len(_FIELD_ORDER), key))
    result, trimmed = {}, 0
    for key in keys:
        if len(result) == 26 or len(key.encode("utf-8")) > 128:
            trimmed += 1
            continue
        shown, count = _preview(value[key], text_bytes, items, depth + 1)
        result[key] = shown
        trimmed += count
    return result, trimmed


def _rank(group):
    scope, kind = group["relevance"], group["kind"]
    if kind == "broad_phase":
        priority = 8
    elif scope == "historical":
        priority = 7
    elif scope == "unscoped":
        priority = 6
    elif kind in ("identity_or_quantity", "structural_or_side", "source_visible_defect", "source_connection_guidance"):
        priority = ("identity_or_quantity", "structural_or_side", "source_visible_defect", "source_connection_guidance").index(kind)
    elif scope == "dependency" and group["uncertainty"] == "explicit":
        priority = 4
    else:
        priority = 5
    severity = {"error": 0, "major": 0, "minor": 1, "unsupported": 2, "review": 3}.get(group["semantic"].get("severity"), 4)
    return priority, _SCOPES.index(scope), severity, group["group_id"]


def _group_preview(group, current, dependencies):
    steps = sorted(group["steps"], key=lambda item: (item not in current, item not in dependencies, item))
    instance_ids = sorted(group["instances"])
    evidence = {
        "member_records_sha256": digest(sorted(group["records"].items())),
        "distinct_input_records": len(group["records"]),
        "step_ids_count": len(steps), "step_ids_sha256": digest(sorted(steps)),
        "instance_ids_count": len(instance_ids), "instance_ids_sha256": digest(instance_ids),
        "provenance_sha256": digest({"page_indexes": sorted(group["pages"]), "ordinals": sorted(group["ordinals"]),
                                     "inherited_from_jobs": sorted(group["jobs"])}),
    }
    source = group["semantic"].get("source")
    if "source" in group["semantic"]:
        evidence["source_value_sha256"] = digest(source)
    preview_semantic = {key: value for key, value in group["semantic"].items() if key != "source"}
    # Adaptive previews constrain one pathological finding without allowing it
    # to consume the entire receipt. Nothing is truncated in the input archive.
    for text_bytes, items, scope_items in ((768, 8, 8), (384, 4, 4), (160, 2, 2), (64, 1, 1)):
        shown, trimmed = _preview(preview_semantic, text_bytes, items)
        if "source" in group["semantic"]:
            # A shortened bbox/hash would look like a different source binding.
            # Preserve small complete bindings; omit an oversized binding with
            # its exact value hash, never emit a partly truncated rectangle.
            if len(canonical(source)) <= 1024:
                shown["source"] = source
            else:
                shown.pop("source", None)
                trimmed += 1
        if group["semantic"].get("localization_profile") == "localized-source-v4":
            semantic = group["semantic"]
            shown["subject_scope"] = {"localization": semantic.get("localization", "unlocalized"),
                "identified_count": len(group["instances"]),
                "unresolved_severity": semantic.get("severity") if semantic.get("localization") != "identified" else None,
                "alternative_candidate_count": len(semantic.get("subject_candidates", [])) if semantic.get("localization") != "identified" else 0,
                "alternatives_are_not_all_defective": semantic.get("localization") != "identified",
                "preview_may_omit_identifiers": True}
            if "review_context" in semantic:
                context = semantic["review_context"]
                shown["review_context"] = {key: context[key] for key in ("complete", "omitted_instances",
                    "omitted_pose_rows", "omitted_observations", "ambiguous_observation_ids_count")}
        shown_steps, step_trimmed = _preview(steps, 128, scope_items)
        shown_ids, id_trimmed = _preview(instance_ids, 128, scope_items)
        value = {
            "group_id": group["group_id"], "relevance": group["relevance"], "priority_class": group["kind"],
            "uncertainty": group["uncertainty"], "occurrence_count": group["count"],
            "step_ids": shown_steps, "instance_ids": shown_ids, "finding": shown,
            "evidence": evidence,
            "preview": {"truncated": bool(trimmed + step_trimmed + id_trimmed),
                        "shortened_or_omitted_value_slots": trimmed + step_trimmed + id_trimmed},
        }
        if len(canonical(value)) <= MAX_GROUP_BYTES:
            return value
    # A record with many maximal key names can exceed even the smallest view.
    # Its omission is counted, never replaced with a misleading empty finding.
    return None


def compact_feedback(findings, current_step_ids, affected_instance_ids=(), *, dependency_step_ids=(),
                     max_groups=MAX_GROUPS, max_bytes=MAX_BYTES, input_truncated=None):
    """Return a <=24-group, <=16 KiB canonical JSON receipt for prompt use.

    ``findings`` is a list/tuple of plain JSON objects. ``input_truncated`` is
    True for known incomplete upstream diagnostics, False for an explicitly
    complete supplied list, and None (default) when upstream completeness is
    unknown. Even False does not assert diagnostic coverage or a clean assembly.

    Relevant dependencies share caller-supplied affected IDs, caller-supplied
    dependency steps, or IDs named by current non-AABB findings. There is no
    inferred connector graph or invented cross-source correspondence. Resolved
    and dismissed records remain hashed/counted but are not repair targets.

    Exact semantic records are grouped across step/provenance occurrences;
    differing messages, alternatives, source crops and diagnostic values remain
    distinct. Original ordering is bound by input.sha256, while group IDs and
    selection do not depend on list order. Over-limit/malformed input raises
    ValueError instead of returning an apparently complete sampled receipt.
    """
    if type(max_groups) is not int or not 1 <= max_groups <= MAX_GROUPS:
        raise ValueError(f"max_groups must be an integer in 1..{MAX_GROUPS}")
    if type(max_bytes) is not int or not 4096 <= max_bytes <= MAX_BYTES:
        raise ValueError(f"max_bytes must be an integer in 4096..{MAX_BYTES}")
    if input_truncated is not None and type(input_truncated) is not bool:
        raise ValueError("input_truncated must be True, False, or None")
    if type(findings) not in (list, tuple) or len(findings) > MAX_INPUT_FINDINGS:
        raise ValueError(f"findings requires at most {MAX_INPUT_FINDINGS} JSON objects")
    current = _ids(current_step_ids, "current_step_ids")
    affected = _ids(affected_instance_ids, "affected_instance_ids")
    dependencies = _ids(dependency_step_ids, "dependency_step_ids")
    copied = _JsonBudget().copy(findings)
    groups, record_hashes = {}, set()
    inferred = set()
    for value in copied:
        if type(value) is not dict:
            raise ValueError("Each feedback finding must be a JSON object")
        for key in ("category", "code", "domain", "severity", "resolution"):
            if value.get(key) is not None and type(value[key]) is not str:
                raise ValueError(f"finding.{key} must be a string or null")
        steps = _steps(value)
        instances = _ids(value.get("instance_ids", []) if value.get("instance_ids") is not None else [], "finding.instance_ids")
        semantic = {key: item for key, item in value.items() if key not in _SCOPE_FIELDS}
        group_id = digest({"finding": semantic, "instance_ids": sorted(instances)})
        record_hash = digest(value)
        record_hashes.add(record_hash)
        if group_id not in groups:
            kind = _kind(value)
            groups[group_id] = {"group_id": group_id, "semantic": semantic, "instances": instances,
                "kind": kind, "uncertainty": _uncertainty(value, kind), "category": _category(value),
                "resolved": value.get("resolution") in {"resolved", "dismissed"},
                "steps": set(), "count": 0, "records": Counter(), "pages": set(), "ordinals": set(), "jobs": set()}
        group = groups[group_id]
        group["steps"].update(steps)
        group["count"] += 1
        group["records"][record_hash] += 1
        for field, target in (("page_index", "pages"), ("ordinal", "ordinals")):
            if type(value.get(field)) is int:
                group[target].add(value[field])
        if type(value.get("inherited_from_job")) is str:
            group["jobs"].add(value["inherited_from_job"])
        if steps & current and group["kind"] != "broad_phase" and not group["resolved"]:
            inferred.update(instances)
    relevant_ids = affected | inferred
    for group in groups.values():
        if group["steps"] & current:
            group["relevance"] = "current_step"
        elif group["steps"] & dependencies or group["instances"] & relevant_ids:
            group["relevance"] = "dependency"
        else:
            group["relevance"] = "historical" if group["steps"] else "unscoped"
    context = {"current_step_ids": sorted(current), "affected_instance_ids": sorted(affected),
               "dependency_step_ids": sorted(dependencies)}
    base = {
        "version": VERSION, "grouping_version": GROUPING_VERSION,
        "config": {"max_groups": max_groups, "max_bytes": max_bytes, "max_group_bytes": MAX_GROUP_BYTES,
                   "max_input_findings": MAX_INPUT_FINDINGS, "max_input_bytes": MAX_INPUT_BYTES,
                   "max_input_nodes": MAX_INPUT_NODES, "max_input_depth": MAX_INPUT_DEPTH,
                   "max_input_string_chars": MAX_INPUT_STRING_CHARS, "max_context_ids": MAX_CONTEXT_IDS},
        "input": {"sha256": digest(copied), "count": len(copied), "canonical_bytes": len(canonical(copied)),
                  "upstream_truncated": input_truncated,
                  "completeness": "truncated" if input_truncated else "unknown" if input_truncated is None else "supplied_list_only"},
        "context": {"sha256": digest(context), "current_step_ids_count": len(current),
                    "affected_instance_ids_count": len(affected), "dependency_step_ids_count": len(dependencies),
                    "inferred_dependency_ids_count": len(inferred - affected)},
        "scope": "Prompt prioritization only. Counts are supplied findings, not verified defects. Omitted or absent findings do not establish a clean assembly. Caller must retain full evidence.",
    }
    ordered = sorted(groups.values(), key=_rank)
    by_category = {}
    for group in ordered:
        by_category.setdefault(group["category"], []).append(group)
    category_order = sorted(by_category, key=lambda name: (-sum(g["count"] for g in by_category[name]), name))
    resolved = [group for group in ordered if group["resolved"]]
    category_counts = [{"category": name, "occurrences": sum(g["count"] for g in by_category[name]),
                        "groups": len(by_category[name])} for name in category_order]
    category_counts_hash = digest(category_counts)
    relevance_counts = Counter(group["relevance"] for group in ordered)
    uncertainty_counts = Counter(group["uncertainty"] for group in ordered)
    resolved_occurrences = sum(group["count"] for group in resolved)
    other_category_occurrences = sum(row["occurrences"] for row in category_counts[8:])

    def receipt(selected):
        selected_categories = Counter(groups[value["group_id"]]["category"] for value in selected)
        selected_scopes = Counter(value["relevance"] for value in selected)
        selected_uncertainties = Counter(value["uncertainty"] for value in selected)
        # Detailed category counts have their own bound; their complete hash and
        # aggregate omitted-category counts remain available in every receipt.
        category_rows = []
        for entry in category_counts[:8]:
            short, trimmed = _short(entry["category"], 96)
            row = dict(entry, category=short, included_groups=selected_categories[entry["category"]],
                       omitted_groups=entry["groups"] - selected_categories[entry["category"]])
            if trimmed:
                row["category_sha256"] = digest(entry["category"])
            category_rows.append(row)
        value = {**base, "findings": selected, "selection": {
            "available_groups": len(groups), "included_groups": len(selected),
            "omitted_groups": len(groups) - len(selected),
            "represented_occurrences": sum(group["occurrence_count"] for group in selected),
            "omitted_occurrences": len(copied) - sum(group["occurrence_count"] for group in selected),
            "exact_duplicate_occurrences": len(copied) - len(record_hashes),
            "grouped_repeated_occurrences": len(copied) - len(groups),
            "resolved_groups_not_selected": len(resolved),
            "resolved_occurrences_not_selected": resolved_occurrences,
            "preview_truncated_groups": sum(group["preview"]["truncated"] for group in selected),
            "category_counts": category_rows, "category_counts_sha256": category_counts_hash,
            "other_category_count": max(0, len(category_counts) - len(category_rows)),
            "other_category_occurrences": other_category_occurrences,
            "relevance_counts": {scope: {"groups": relevance_counts[scope],
                "included_groups": selected_scopes[scope],
                "omitted_groups": relevance_counts[scope] - selected_scopes[scope]} for scope in _SCOPES},
            "uncertainty_counts": {kind: {"groups": uncertainty_counts[kind],
                "included_groups": selected_uncertainties[kind],
                "omitted_groups": uncertainty_counts[kind] - selected_uncertainties[kind]} for kind in _UNCERTAINTIES},
        }}
        value["receipt_sha256"] = digest(value)
        return value

    selected = []
    result = receipt(selected)
    if len(canonical(result)) > max_bytes:
        raise ValueError("Feedback receipt metadata exceeds requested byte limit")
    for group in ordered:
        if group["resolved"] or len(selected) == max_groups:
            continue
        shown = _group_preview(group, current, dependencies)
        if shown is None:
            continue
        proposed = receipt([*selected, shown])
        if len(canonical(proposed)) <= max_bytes:
            selected.append(shown)
            result = proposed
    return result


def prompt_feedback(receipt):
    """Detach a model-facing view from a hash-validated full feedback receipt.

    Archive the full receipt before using this view. Selection does not change:
    only opaque per-group hashes and resource configuration are removed. Source
    bindings, original semantic fields, scope/uncertainty, and omission counts
    stay visible. The whole canonical view has its own <=16 KiB size check.
    """
    if type(receipt) is not dict:
        raise ValueError("Feedback prompt view requires a receipt object")
    # A receipt wraps the original source binding in a group and evidence view.
    saved = _JsonBudget(depth_allowance=4).copy(receipt)
    try:
        supplied_hash = saved.pop("receipt_sha256")
        if type(supplied_hash) is not str or supplied_hash != digest(saved):
            raise ValueError("Feedback receipt hash mismatch")
        if saved["version"] != VERSION or saved["grouping_version"] != GROUPING_VERSION:
            raise ValueError("Unsupported feedback receipt version")
        if len(canonical(receipt)) > MAX_BYTES:
            raise ValueError("Feedback receipt exceeds archive byte limit")
        findings, selection = saved["findings"], saved["selection"]
        if type(findings) is not list or len(findings) > MAX_GROUPS:
            raise ValueError("Feedback receipt exceeds group limit")
        for key in ("included_groups", "represented_occurrences", "omitted_occurrences", "omitted_groups", "available_groups"):
            if type(selection[key]) is not int or selection[key] < 0:
                raise ValueError("Feedback receipt has invalid selection counts")
        if (selection["included_groups"] != len(findings)
                or selection["represented_occurrences"] + selection["omitted_occurrences"] != saved["input"]["count"]
                or selection["included_groups"] + selection["omitted_groups"] != selection["available_groups"]
                or sum(group["occurrence_count"] for group in findings) != selection["represented_occurrences"]):
            raise ValueError("Feedback receipt has inconsistent selection counts")
        shown = []
        for group in findings:
            for field in ("step_ids", "instance_ids"):
                identities = _ids(group[field], f"feedback.{field}")
                count = group["evidence"][f"{field}_count"]
                if type(count) is not int or count < len(group[field]) or len(identities) != len(group[field]):
                    raise ValueError("Feedback receipt has inconsistent scope counts")
            view = {key: group[key] for key in ("finding", "relevance", "priority_class", "occurrence_count",
                                               "step_ids", "instance_ids", "uncertainty", "preview")}
            view["preview"] = {**view["preview"],
                "omitted_step_ids": group["evidence"]["step_ids_count"] - len(group["step_ids"]),
                "omitted_instance_ids": group["evidence"]["instance_ids_count"] - len(group["instance_ids"])}
            shown.append(view)
        counts = {key: value for key, value in selection.items() if key != "category_counts_sha256"}
        counts["category_counts"] = [{**{key: value for key, value in row.items() if key != "category_sha256"},
                                      **({"category_label_truncated": True} if "category_sha256" in row else {})}
                                     for row in counts["category_counts"]]
        result = {"version": PROMPT_VERSION, "receipt_sha256": supplied_hash,
            "input": {key: saved["input"][key] for key in ("sha256", "count", "completeness", "upstream_truncated")},
            "findings": shown, "selection": counts, "scope": saved["scope"]}
    except (KeyError, TypeError) as error:
        raise ValueError("Malformed feedback receipt") from error
    if len(canonical(result)) > MAX_BYTES:
        raise ValueError("Feedback prompt view exceeds byte limit")
    return result
