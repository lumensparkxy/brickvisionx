"""Original synthetic patches/pages prove alpha software boundaries, not LEGO accuracy."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import httpx
from jsonschema import Draft202012Validator
from PIL import Image
import pytest

from guide2build.engine import alpha
from guide2build.engine.contracts import strict_schema
from guide2build.engine.provider import ProviderFailure
from guide2build.releases.models import canonical, digest

SOURCE = "a" * 64


def region(page=0):
    return {"page_index": page, "bbox": [0, 0, 1, 1]}


def pose(x=0):
    return {"position_ldu": [x, 0, 0], "quaternion_xyzw": [0, 0, 0, 1]}


def part(identity="synthetic-a", page=0, colour="4"):
    return {"instance_id": identity, "part_id": "synthetic1", "color_code": colour, "source": region(page)}


def step(identity="synthetic-step-1", number=1, page=0, ids=None, introduced=None):
    ids = ids or ["synthetic-a"]
    return {"step_id": identity, "section_id": "booklet-01-main", "main_step_number": number,
        "substep_label": None, "instruction": "Place the source piece.", "source": region(page),
        "introduced_instance_ids": ids if introduced is None else introduced,
        "active_instance_ids": ids, "visibility": "all_introduced", "visible_instance_ids": [],
        "pose_updates": [{"instance_id": i, "pose": pose(n * 20)} for n, i in enumerate(ids)],
        "action": "add_parts", "assembly_group_id": None}


def patch(pages=(0, 1, 2, 3), *, number=1, identity="synthetic-a", section=True):
    page = pages[0]
    item = step(f"synthetic-step-{number}", number, page, [identity])
    return {"page_observations": [{"page_index": index, "panels": [{"section": item["section_id"],
        "number": number, "label": str(number), "bbox": [0, 0, 1, 1], "kind": "main"}] if index == page else [],
        "description": "Original synthetic instruction page." if index == page else "Original synthetic cover.",
        "uncertainties": []} for index in pages],
        "new_sections": [{"section_id": "booklet-01-main", "label": "Synthetic main"}] if section else [],
        "new_instances": [part(identity, page)], "new_steps": [item],
        "quantity_evidence": [{"step_id": item["step_id"], "source": region(page), "printed_quantity": 1,
            "unit": "part", "physical_units": [[identity]], "explanation": "Synthetic 1x callout."}],
        "uncertainties": [], "blockers": []}


@pytest.fixture
def environment(tmp_path, monkeypatch):
    guide = {"pdf_url": "https://www.lego.com/en-us/service/building-instructions/99999",
             "expected_page_count": 8, "expected_main_steps": None}
    monkeypatch.setattr(alpha, "find_guide", lambda *args: guide)
    monkeypatch.setattr(alpha, "individual_catalogue_context", lambda *args, **kwargs: [])
    pages = tmp_path / "public" / "pages" / SOURCE
    pages.mkdir(parents=True)
    for index in range(8):
        Image.new("RGB", (32, 24), "white").save(pages / f"page-{index:03d}.png")
    directory = tmp_path / "engine" / "jobs" / "synthetic-job"
    directory.mkdir(parents=True)
    job = {"id": "synthetic-job", "set_number": "99999", "guide_id": "booklet-01",
           "config": {"generation_mode": "alpha_fast", "alpha_page_batch_size": 4, "max_chunk_attempts": 5, "max_model_calls": 100}}
    checkpoint = {}
    saves = []
    snapshot_stages = set()
    def save(stage, state="constructing", error=None):
        checkpoint["stage"] = stage
        event = {"stage": stage, "state": state, "error": error}
        if stage in snapshot_stages:
            event["checkpoint"] = deepcopy(checkpoint)
        saves.append(event)
    def geometry(scene, target, shared):
        target.mkdir(parents=True, exist_ok=True)
        records = {}
        for root in {item.geometry_ref for item in scene.instances}:
            path = target / root
            path.parent.mkdir(parents=True, exist_ok=True)
            # Synthetic individual geometry is authored only for control-flow tests.
            if not path.exists():
                path.write_text("0 Original synthetic individual test part\n3 16 0 0 0 20 0 0 0 0 20\n")
            records[root] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "classification": "Part",
                             "url": "https://library.ldraw.org/library/official/" + root, "dependencies": []}
        material = target / "LDConfig.ldr"
        material.write_text("0 !COLOUR Synthetic_Red CODE 4 VALUE #FF0000 EDGE #333333\n"
                            "0 !COLOUR Synthetic_Transparent_Blue CODE 43 VALUE #FFFFFF EDGE #333333 ALPHA 128\n"
                            "0 !COLOUR Synthetic_Clear CODE 47 VALUE #FFFFFF EDGE #333333 ALPHA 128\n")
        (target / "provenance.json").write_text(json.dumps({"resources": records, "materials": {"LDConfig.ldr": {
            "sha256": hashlib.sha256(material.read_bytes()).hexdigest(),
            "url": "https://library.ldraw.org/library/official/LDConfig.ldr"}}, "file_map": {}}))
        return {"status": "synthetic_asset_test_only"}
    monkeypatch.setattr(alpha, "prepare_geometry", geometry)
    return SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path), job=job, checkpoint=checkpoint,
                           directory=directory, pages=pages, save=save, saves=saves, snapshot_stages=snapshot_stages,
                           heartbeat=SimpleNamespace(check=lambda: None), guide=guide)


def expand(h, value, pages=(0, 1, 2, 3), previous=None):
    return alpha.expand_alpha_patch(value, job=h.job, source_hash=SOURCE, page_count=8,
                                    page_indexes=pages, previous=previous)


def generate(h, provider, **kwargs):
    return alpha.generate_alpha(store=h.store, job=h.job, provider=provider, checkpoint=h.checkpoint,
        directory=h.directory, source_hash=SOURCE, pages_dir=h.pages, page_count=8,
        save=h.save, heartbeat=h.heartbeat, **kwargs)


class SequenceProvider:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []
    def call(self, prompt, images, schema, evidence, check):
        check()
        self.calls.append({"prompt": prompt, "images": images, "evidence": evidence})
        return deepcopy(next(self.values))


def test_model_schema_is_strict_and_compact():
    schema = strict_schema(alpha.AlphaPatch)
    Draft202012Validator.check_schema(schema)
    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node["required"]) == set(node["properties"])
            if node.get("type") == "array":
                assert "items" in node and "prefixItems" not in node
            for item in node.values():
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)
    visit(schema)
    assert "poses" not in schema["$defs"]["AlphaStepPatch"]["properties"]
    assert "pose_updates" in schema["$defs"]["AlphaStepPatch"]["properties"]
    for name in ("AlphaPanel", "PageRegion"):
        bbox = schema["$defs"][name]["properties"]["bbox"]
        assert bbox["minItems"] == bbox["maxItems"] == 4
        assert bbox["items"]["minimum"] == 0 and bbox["items"]["maximum"] == 1


def test_alpha_overall_request_limit_survives_retry_independently_of_chunk_attempts(environment):
    from guide2build.engine.runtime import ModelCallBudgetExhausted
    h = environment
    h.job["config"]["max_model_calls"] = 3
    provider = SequenceProvider([{}] * 5)
    for _ in range(2):
        with pytest.raises(ModelCallBudgetExhausted):
            generate(h, provider)
        assert len(provider.calls) == h.checkpoint["model_calls_used"] == 3
        assert h.checkpoint["alpha_chunks"]["0"]["used"] == 3
        assert len(h.checkpoint["model_requests"]) == 3


def explicit_panel(kind="main", number=1, *, role="build_event", key="main-1", bbox=None, parent=None):
    return {"section": "booklet-01-main", "number": number, "label": str(number) if number else "Overview",
        "bbox": bbox or [0, 0, 1, 1], "kind": kind, "region_id": key, "role": role,
        "event_key": key if role == "build_event" else None, "associated_event": parent,
        "semantic_status": "explicit", "evidence": "Original synthetic source declares this region and its role.",
        "uncertainty": []}


def normalized_regions(h, value):
    parsed = alpha.AlphaPatch.model_validate(value)
    return alpha._alpha_regions(parsed, job=h.job, checkpoint=h.checkpoint, source_hash=SOURCE,
        bindings=alpha._page_bindings(h.pages, [page.page_index for page in parsed.page_observations]))


def test_source_only_overview_is_retained_and_later_batch_builds(environment):
    h = environment
    first = patch()
    for key in ("new_sections", "new_instances", "new_steps", "quantity_evidence"):
        first[key] = []
    first["page_observations"][0]["panels"] = [explicit_panel("attachment", None, role="overview", key="overview")]
    provider = SequenceProvider([first, patch((4, 5, 6, 7))])
    scene = generate(h, provider)
    assert scene and len(scene.instances) == 1 and len(provider.calls) == 2
    assert h.checkpoint["alpha_completed_pages"] == 8
    regions = h.checkpoint["alpha_region_index"]
    assert len(regions["retained_regions"]) == 2
    assert regions["retained_regions"][0]["disposition"] == "source_only_overview"
    assert regions["summary"]["reconstruction_regions"] == 1
    assert '"source_region_associations":' in provider.calls[1]["prompt"]


@pytest.mark.parametrize("mutation", ["empty", "foreign", "queue", "patch"])
def test_semantic_index_cannot_bypass_source_coverage(environment, mutation):
    h = environment
    value = patch()
    value["page_observations"][0]["panels"] = [explicit_panel()]
    index = normalized_regions(h, value)
    if mutation == "empty":
        index = {"reconstruction_panels": []}
    elif mutation == "foreign":
        index["source"]["source_sha256"] = "b" * 64
    elif mutation == "queue":
        index["reconstruction_panels"] = []
        index["normalization_sha256"] = digest({key: val for key, val in index.items() if key != "normalization_sha256"})
    else:
        value["page_observations"][0]["panels"][0]["bbox"] = [.1, .1, .9, .9]
    with pytest.raises(ValueError, match="semantic source index"):
        alpha.expand_alpha_patch(value, job=h.job, source_hash=SOURCE, page_count=8,
                                 page_indexes=(0, 1, 2, 3), region_index=index)


def callout_patch(parent_kind="main", child_number=1):
    value = patch()
    value["page_observations"][0]["panels"] = [
        explicit_panel(parent_kind, bbox=[0, .5, 1, 1]),
        explicit_panel("substep", child_number, key="callout-1", bbox=[0, 0, 1, .4],
                       parent={"page_index": 0, "event_key": "main-1"})]
    value["new_steps"][0]["source"]["bbox"] = [0, .5, 1, 1]
    child = deepcopy(value["new_steps"][0])
    child.update(step_id="synthetic-callout-1", action="build_subassembly", assembly_group_id="synthetic-group",
                 substep_label="1", visibility="explicit", visible_instance_ids=["synthetic-a"])
    child["source"]["bbox"] = [0, 0, 1, .4]
    value["new_steps"][0].update(action="attach_subassembly", assembly_group_id="synthetic-group", introduced_instance_ids=[])
    value["new_steps"].insert(0, child)
    return value


@pytest.mark.parametrize("parent_kind", ["main", "attachment"])
def test_numbered_callouts_need_distinct_source_snapshots(environment, parent_kind):
    h = environment
    value = callout_patch(parent_kind)
    index = normalized_regions(h, value)
    scene = alpha.expand_alpha_patch(value, job=h.job, source_hash=SOURCE, page_count=8,
                                    page_indexes=(0, 1, 2, 3), region_index=index)
    assert len(scene.instances) == 1 and len(scene.steps) == 2
    value["new_steps"].pop(0)
    value["new_steps"][0].update(action="add_parts", assembly_group_id=None, introduced_instance_ids=["synthetic-a"])
    with pytest.raises(ValueError, match="panels disagree"):
        alpha.expand_alpha_patch(value, job=h.job, source_hash=SOURCE, page_count=8,
                                 page_indexes=(0, 1, 2, 3), region_index=index)


def test_distinct_main_regions_cannot_share_one_snapshot(environment):
    h = environment
    value = patch()
    value["page_observations"][0]["panels"] = [explicit_panel(bbox=[0, 0, .45, 1]),
        explicit_panel(key="another-main-1", bbox=[.55, 0, 1, 1])]
    value["new_steps"][0]["source"]["bbox"] = [0, 0, .45, 1]
    index = normalized_regions(h, value)
    fresh = alpha._alpha_fresh_region_findings(index, alpha._page_bindings(h.pages, range(4)))
    assert any(item["code"] == "source_main_number_repeated" for item in fresh)
    with pytest.raises(ValueError, match="unmatched_required_region_count"):
        alpha.expand_alpha_patch(value, job=h.job, source_hash=SOURCE, page_count=8,
                                 page_indexes=(0, 1, 2, 3), region_index=index)


@pytest.mark.parametrize("field", ["alpha_page_observations", "alpha_review_notes", "alpha_region_index"])
def test_completed_source_context_is_bound_to_accepted_receipts(environment, field):
    h = environment
    generate(h, SequenceProvider([patch()]), max_chunks=1)
    if field == "alpha_page_observations":
        h.checkpoint[field][0]["panels"][0]["role"] = "overview"
    elif field == "alpha_review_notes":
        h.checkpoint[field].append({"code": "fabricated", "message": "Unbound finding"})
    else:
        h.checkpoint[field]["summary"]["source_only_regions"] = 999
    provider = SequenceProvider([patch((4, 5, 6, 7), number=2, identity="synthetic-b", section=False)])
    with pytest.raises(ValueError, match="authenticated receipts"):
        generate(h, provider)
    assert not provider.calls


def test_latest_alpha_rejection_survives_old_quality_noise():
    candidate = {"steps": [{"step_id": "known-step", "active_instance_ids": ["known-part"]}]}
    notes = [{"code": "wrong_side", "severity": "error", "step_id": "known-step",
              "instance_ids": ["known-part"], "message": f"Earlier quality finding {index}"} for index in range(30)]
    rejected = [{"code": "invalid_alpha_patch", "message": "Current source instruction is missing."}]
    feedback = alpha._alpha_feedback({"alpha_review_notes": notes}, candidate, rejected)
    assert feedback["latest_rejection"] == rejected[-1]
    assert feedback["rejected_history_sha256"] == digest(rejected)


def test_alpha_diagnostic_findings_continue_and_survive_resume(environment, monkeypatch):
    from guide2build.engine import hypotheses
    h = environment
    def diagnostic(scene, previous, geometry, *, checked_step_ids):
        return {"findings": [{"code": "symmetric_coincident_geometry", "severity": "error",
            "step_id": checked_step_ids[-1], "instance_ids": ["synthetic-a"], "message": "Synthetic diagnostic only."}],
            "coverage": {"status": "partial"}, "findings_truncated": False}
    monkeypatch.setattr(hypotheses, "diagnose_candidate", diagnostic)
    provider = SequenceProvider([patch()])
    generate(h, provider, max_chunks=1)
    first_notes = deepcopy(h.checkpoint["alpha_review_notes"])
    assert any(item.get("code") == "symmetric_coincident_geometry" for item in first_notes)
    following = SequenceProvider([patch((4, 5, 6, 7), number=2, identity="synthetic-b", section=False)])
    scene = generate(h, following)
    assert scene and h.checkpoint["alpha_completed_pages"] == 8 and len(following.calls) == 1
    assert h.checkpoint["alpha_review_notes"][:len(first_notes)] == first_notes
    assert "Synthetic diagnostic only." in following.calls[0]["prompt"]
    region_first = [item for item in first_notes if item.get("code") == "legacy_semantics_unclassified"]
    region_all = [item for item in h.checkpoint["alpha_review_notes"] if item.get("code") == "legacy_semantics_unclassified"]
    assert len(region_first) == 1 and len(region_all) == 2  # Prior normalization is not appended twice.


def test_append_only_expansion_inherits_poses_and_preserves_previous(environment):
    h = environment
    first = expand(h, patch()).model_dump(mode="json")
    before = deepcopy(first)
    value = patch((4, 5, 6, 7), number=2, identity="synthetic-b", section=False)
    second = expand(h, value, (4, 5, 6, 7), first)
    assert first == before
    assert second.steps[0].model_dump(mode="json") == first["steps"][0]
    assert second.instances[0].model_dump(mode="json") == first["instances"][0]
    assert second.steps[-1].poses["synthetic-a"] == second.steps[0].poses["synthetic-a"]
    assert second.status == "needs_review"
    assert second.geometry_check == second.connector_check == second.physical_build_check == "not_run"
    assert len(second.instances) == 2


def test_callout_attachment_and_multiplier_reuse_physical_ids(environment):
    h = environment
    value = patch()
    value["new_instances"].append(part("synthetic-b"))
    first = value["new_steps"][0]
    first.update(action="build_subassembly", assembly_group_id="synthetic-group-a", substep_label="1",
                 visibility="explicit", visible_instance_ids=["synthetic-a"])
    second = step("synthetic-callout-b", 1, ids=["synthetic-b"])
    second.update(action="build_subassembly", assembly_group_id="synthetic-group-b", substep_label="1",
                  visibility="explicit", visible_instance_ids=["synthetic-b"])
    attached = step("synthetic-attachment", 1, ids=["synthetic-a", "synthetic-b"], introduced=[])
    attached.update(action="attach_subassembly", assembly_group_id="synthetic-group-a")
    first["source"]["bbox"] = [0, 0, .4, .4]
    second["source"]["bbox"] = [.6, 0, 1, .4]
    attached["source"]["bbox"] = [0, .5, 1, 1]
    value["page_observations"][0]["panels"][0]["bbox"] = attached["source"]["bbox"]
    value["page_observations"][0]["panels"].extend({"section": "booklet-01-main", "number": 1,
        "label": "1", "bbox": item["source"]["bbox"], "kind": "substep"} for item in [first, second])
    value["new_steps"].extend([second, attached])
    value["quantity_evidence"] = [{"step_id": attached["step_id"], "source": region(), "printed_quantity": 2,
        "unit": "assembly_group", "physical_units": [["synthetic-a"], ["synthetic-b"]],
        "explanation": "Synthetic two distinct copies, attached without recreation."}]
    scene = expand(h, value)
    assert len(scene.instances) == 2 and len(scene.steps) == 3
    assert scene.steps[-1].introduced_instance_ids == []
    assert set(scene.steps[-1].poses) == {"synthetic-a", "synthetic-b"}
    value["quantity_evidence"][0]["physical_units"] = [["synthetic-a"], ["synthetic-a"]]
    with pytest.raises(ValueError, match="distinct real physical units"):
        expand(h, value)


@pytest.mark.parametrize("mutation", ["nonfinite", "quaternion", "outside_page", "invented_review", "unsafe_part"])
def test_hard_invalid_proposals_fail(environment, mutation):
    value = patch()
    if mutation == "nonfinite":
        value["new_steps"][0]["pose_updates"][0]["pose"]["position_ldu"][0] = float("inf")
    elif mutation == "quaternion":
        value["new_steps"][0]["pose_updates"][0]["pose"]["quaternion_xyzw"] = [0, 0, 0, 2]
    elif mutation == "outside_page":
        value["new_instances"][0]["source"]["page_index"] = 7
    elif mutation == "invented_review":
        value["reviews"] = [{"actor_type": "human", "decision": "accepted"}]
    else:
        value["new_instances"][0]["part_id"] = "../finished-model.ldr"
    with pytest.raises(ValueError):
        expand(environment, value)


def test_missing_page_observation_or_indexed_instruction_is_a_hard_failure(environment):
    value = patch()
    value["page_observations"].pop()
    with pytest.raises(ValueError, match="ordered fresh observation"):
        expand(environment, value)
    value = patch()
    value["page_observations"][1]["panels"] = [{"section": "booklet-01-main", "number": 2,
        "label": "2", "bbox": [0, 0, 1, 1], "kind": "main"}]
    with pytest.raises(ValueError, match="panels disagree"):
        expand(environment, value)


def unnumbered_inset_patch():
    value = patch()
    main = value["new_steps"][0]
    main["source"]["bbox"] = [0.05, 0.3, 0.95, 0.95]
    panels = value["page_observations"][0]["panels"]
    panels[0]["bbox"] = main["source"]["bbox"]
    detail = step("synthetic-inset", 1, ids=["synthetic-b"])
    detail.update(substep_label="Unnumbered piece detail", action="inspect",
                  visibility="explicit", visible_instance_ids=["synthetic-b"],
                  source={"page_index": 0, "bbox": [0.55, 0.05, 0.75, 0.25]})
    attached = step("synthetic-inset-attachment", 1, ids=["synthetic-b"], introduced=[])
    attached.update(substep_label="Unnumbered placement arrow",
                    source={"page_index": 0, "bbox": [0.55, 0.25, 0.75, 0.45]})
    value["new_instances"].append(part("synthetic-b"))
    value["new_steps"].extend([detail, attached])
    panels.extend([{"section": "booklet-01-main", "number": None, "label": "Piece detail",
                     "bbox": detail["source"]["bbox"], "kind": "substep"},
                   {"section": "booklet-01-main", "number": None, "label": "Placement arrow",
                     "bbox": attached["source"]["bbox"], "kind": "attachment"}])
    value["quantity_evidence"].append({"step_id": detail["step_id"], "source": region(),
        "printed_quantity": 1, "unit": "part", "physical_units": [["synthetic-b"]],
        "explanation": "The inset and arrow reuse one physical source piece."})
    return value


@pytest.mark.parametrize("parent_number", [1, None])
def test_unnumbered_insets_bind_distinct_crops_with_parent_numbers_or_null(environment, parent_number):
    value = unnumbered_inset_patch()
    for item in value["new_steps"][1:]:
        item["main_step_number"] = parent_number
    scene = expand(environment, value)
    assert len(scene.steps) == 3 and len(scene.instances) == 2
    assert [item.main_step_number for item in scene.steps] == [1, parent_number, parent_number]
    assert scene.steps[-1].introduced_instance_ids == []


@pytest.mark.parametrize("mutation", ["page", "section", "crop", "label", "parent", "omitted"])
def test_unnumbered_panel_cannot_be_covered_by_unrelated_detail(environment, mutation):
    value = unnumbered_inset_patch()
    attached = value["new_steps"][-1]
    if mutation == "page":
        attached["source"]["page_index"] = 1
    elif mutation == "section":
        value["new_sections"].append({"section_id": "booklet-01-other", "label": "Other original section"})
        attached["section_id"] = "booklet-01-other"
    elif mutation == "crop":
        attached["source"]["bbox"] = [0.05, 0.3, 0.95, 0.95]
    elif mutation == "label":
        attached["substep_label"] = None
    elif mutation == "parent":
        attached["main_step_number"] = 2
    else:
        value["new_steps"].pop()
    with pytest.raises(ValueError, match="panels disagree") as failure:
        expand(environment, value)
    feedback = json.loads(str(failure.value).split("disagree: ", 1)[1])
    assert feedback["unmatched_unnumbered_count"] == 1
    assert feedback["unmatched_unnumbered_panels"][0]["label"] == "Placement arrow"


def test_unnumbered_details_do_not_silently_replace_the_printed_main_panel(environment):
    value = unnumbered_inset_patch()
    value["new_steps"].pop(0)
    value["new_instances"].pop(0)
    value["quantity_evidence"].pop(0)
    with pytest.raises(ValueError, match="panels disagree") as failure:
        expand(environment, value)
    feedback = json.loads(str(failure.value).split("disagree: ", 1)[1])
    assert feedback["missing_groups"] == [[0, "booklet-01-main", 1]]
    assert feedback["unmatched_unnumbered_count"] == 0


def test_unnumbered_panels_need_distinct_snapshots_and_report_extra_groups(environment):
    value = unnumbered_inset_patch()
    value["new_steps"][1]["action"] = "add_parts"
    value["page_observations"][0]["panels"][-1]["bbox"] = value["new_steps"][1]["source"]["bbox"]
    value["new_steps"].pop()
    with pytest.raises(ValueError, match="panels disagree") as failure:
        expand(environment, value)
    feedback = json.loads(str(failure.value).split("disagree: ", 1)[1])
    assert feedback["unmatched_unnumbered_count"] == 1
    value = patch()
    value["new_steps"].append(step("synthetic-extra", 2, page=1, introduced=[]))
    with pytest.raises(ValueError, match="panels disagree") as failure:
        expand(environment, value)
    feedback = json.loads(str(failure.value).split("disagree: ", 1)[1])
    assert feedback["extra_groups"] == [[1, "booklet-01-main", 2]]


def test_unnumbered_attachment_can_reuse_a_main_number_from_immutable_previous_chunk(environment):
    h = environment
    previous = expand(h, patch()).model_dump(mode="json")
    value = patch((4, 5, 6, 7), identity="synthetic-b", section=False)
    value["new_steps"][0]["step_id"] = "synthetic-inherited-main-attachment"
    value["quantity_evidence"][0]["step_id"] = value["new_steps"][0]["step_id"]
    value["new_steps"][0]["substep_label"] = "Previous main attachment"
    value["page_observations"][0]["panels"][0].update(number=None, kind="attachment")
    scene = expand(h, value, (4, 5, 6, 7), previous)
    assert scene.steps[-1].main_step_number == 1
    assert scene.steps[0].model_dump(mode="json") == previous["steps"][0]


def test_preparation_quantity_can_bind_another_page_snapshot_and_repeat_same_physical_units(environment):
    value = patch()
    value["new_steps"][0]["source"]["page_index"] = 1
    value["page_observations"][1]["panels"] = value["page_observations"][0]["panels"]
    value["page_observations"][0]["panels"] = []
    repeated = deepcopy(value["quantity_evidence"][0])
    repeated["source"]["page_index"] = 1
    repeated["explanation"] = "The placement repeats the preparation quantity for the same source piece."
    value["quantity_evidence"].append(repeated)
    scene = expand(environment, value)
    assert len(scene.instances) == 1 and len(scene.steps) == 1
    assert scene.instances[0].source.page_index == 0 and scene.steps[0].source.page_index == 1


@pytest.mark.parametrize("mutation", ["unknown_step", "unknown_unit", "nonvisible_unit", "duplicate_unit"])
def test_quantity_binding_errors_identify_offending_step_and_physical_units(environment, mutation):
    value = patch()
    claim = value["quantity_evidence"][0]
    if mutation == "unknown_step":
        claim["step_id"] = "synthetic-unknown-step"
    elif mutation == "unknown_unit":
        claim["physical_units"] = [["synthetic-unknown-piece"]]
    elif mutation == "nonvisible_unit":
        value["new_instances"].append(part("synthetic-b", page=1))
        value["new_steps"].append(step("synthetic-step-2", 2, page=1, ids=["synthetic-b"]))
        value["page_observations"][1]["panels"] = [{"section": "booklet-01-main", "number": 2,
            "label": "2", "bbox": [0, 0, 1, 1], "kind": "main"}]
        claim["physical_units"] = [["synthetic-b"]]
    else:
        claim.update(printed_quantity=2, physical_units=[["synthetic-a"], ["synthetic-a"]])
    with pytest.raises(ValueError) as failure:
        expand(environment, value)
    assert claim["step_id"] in str(failure.value)
    if mutation != "unknown_step":
        assert claim["physical_units"][0][0] in str(failure.value)


def exhausted_empty_batch(h):
    value = patch()
    value.update(new_sections=[], new_instances=[], new_steps=[], quantity_evidence=[])
    value["blockers"] = ["Synthetic cover batch alone cannot form a playable assembly."]
    value["uncertainties"] = [{"category": "coverage", "step_ids": [], "instance_ids": [],
        "reason": "Synthetic leading pages contain no assembly instructions.", "alternatives": ["Inspect later pages."]}]
    for observation in value["page_observations"]:
        observation["panels"] = []
    provider = SequenceProvider([value] * 5)
    assert generate(h, provider) is None
    assert len(provider.calls) == 5
    state = h.checkpoint["alpha_chunks"]["0"]
    assert state["used"] == state["limit"] == 5
    return state


def test_trailing_assisted_empty_batch_retains_semantic_index_on_second_resume(environment):
    from pathlib import Path
    h = environment
    assert generate(h, SequenceProvider([patch()]), max_chunks=1) is not None
    empty = patch((4, 5, 6, 7))
    empty.update(new_sections=[], new_instances=[], new_steps=[], quantity_evidence=[], blockers=["Synthetic trailing cover blocker."])
    for observation in empty["page_observations"]:
        observation["panels"] = []
    failed = SequenceProvider([empty] * 5)
    generate(h, failed)
    state = h.checkpoint["alpha_chunks"]["1"]
    assert len(failed.calls) == state["used"] == 5
    review = source_review(h)
    review["pages"] = [{"page_index": index, "sha256": hashlib.sha256((h.pages / f"page-{index:03d}.png").read_bytes()).hexdigest(),
        "classification": "non_instruction", "description": "Original synthetic trailing noninstruction image."}
        for index in range(4, 8)]
    receipt = alpha.accept_alpha_correction(job=h.job, checkpoint=h.checkpoint, directory=h.directory,
        source_hash=SOURCE, pages_dir=h.pages, page_count=8, rejected_trial=Path(state["trials"][-1]),
        source_review=review, save=h.save, heartbeat=h.heartbeat)
    assert {"region-index.json", "region-findings.json"} <= set(receipt["files"])
    provider = SequenceProvider([])
    first = generate(h, provider)
    before = deepcopy(h.checkpoint)
    second = generate(h, provider)
    assert first == second and not provider.calls
    assert h.checkpoint["alpha_region_index"] == before["alpha_region_index"]
    assert h.checkpoint["alpha_page_observations"] == before["alpha_page_observations"]
    assert h.checkpoint["alpha_review_notes"] == before["alpha_review_notes"]


def test_rebound_alpha_candidate_cannot_replace_immutable_accepted_history(environment):
    from pathlib import Path
    h = environment
    generate(h, SequenceProvider([patch()]), max_chunks=1)
    accepted = h.checkpoint["alpha_chunks"]["0"]["accepted"]
    original = (Path(accepted["directory"]) / "accepted.json").read_bytes()
    h.checkpoint["candidate"]["steps"][0]["poses"]["synthetic-a"]["position_ldu"][0] += 10
    accepted["scene_sha256"] = digest(h.checkpoint["candidate"])
    provider = SequenceProvider([patch((4, 5, 6, 7), number=2, identity="synthetic-b", section=False)])
    with pytest.raises(ValueError, match="immutable receipt"):
        generate(h, provider)
    assert not provider.calls
    assert (Path(accepted["directory"]) / "accepted.json").read_bytes() == original


@pytest.mark.parametrize("key,value", [("model", "synthetic-different-model"), ("thinking_level", "low")])
def test_alpha_runtime_choice_cannot_change_partway_through_frozen_run(environment, key, value):
    h = environment
    generate(h, SequenceProvider([patch()]), max_chunks=1)
    candidate = deepcopy(h.checkpoint["candidate"])
    h.job["config"][key] = value
    provider = SequenceProvider([])
    with pytest.raises(ValueError, match="Frozen alpha source, policy"):
        generate(h, provider)
    assert not provider.calls and h.checkpoint["candidate"] == candidate


def source_review(h):
    return {"actor_type": "agent", "actor_id": "synthetic-source-inspector", "source_sha256": SOURCE,
        "reason": "Original synthetic white pages contain no instruction panel; later pages remain unprocessed.",
        "pages": [{"page_index": index, "sha256": hashlib.sha256((h.pages / f"page-{index:03d}.png").read_bytes()).hexdigest(),
            "classification": "non_instruction", "description": "Original synthetic noninstruction test image."}
            for index in range(4)]}


def accept_empty_correction(h, review=None, save=None):
    from pathlib import Path
    state = h.checkpoint["alpha_chunks"]["0"]
    return alpha.accept_alpha_correction(job=h.job, checkpoint=h.checkpoint, directory=h.directory,
        source_hash=SOURCE, pages_dir=h.pages, page_count=8, rejected_trial=Path(state["trials"][-1]),
        source_review=review or source_review(h), save=save or h.save, heartbeat=h.heartbeat)


def test_agent_empty_batch_correction_preserves_exhausted_trials_and_replays_without_inference(environment):
    from pathlib import Path
    h = environment
    state = exhausted_empty_batch(h)
    history = deepcopy(state["trials"])
    original = Path(history[-1]) / "patch.json"
    original_bytes = original.read_bytes()
    receipt = accept_empty_correction(h)
    correction = Path(receipt["directory"])
    assert correction.parent == h.directory / "alpha-corrections" and str(correction) not in history
    assert state["used"] == state["limit"] == 5 and state["trials"] == history
    assert original.read_bytes() == original_bytes
    corrected = json.loads((correction / "patch.json").read_bytes())
    assert corrected == {**json.loads(original_bytes), "blockers": []}
    assert receipt["scene_sha256"] is None and receipt["artifact_kind"] == "pdf_assisted_alpha_correction"
    actor_receipt = json.loads((correction / "correction-receipt.json").read_bytes())
    assert actor_receipt["source_review"]["actor_type"] == "agent"
    assert actor_receipt["inference"] == actor_receipt["assembly_approval"] == actor_receipt["human_review"] == "not_run"
    assert h.checkpoint.get("alpha_completed_pages", 0) == 0 and h.checkpoint.get("candidate") is None
    assert h.saves[-1]["stage"] == "alpha_source_observation_corrected"
    provider = SequenceProvider([patch((4, 5, 6, 7))])
    result = generate(h, provider)
    assert len(provider.calls) == 1 and len(result.steps) == 1 and len(result.instances) == 1
    assert state["trials"] == history and state["used"] == 5
    assert h.checkpoint["alpha_completed_pages"] == 8
    assert h.checkpoint["artifact_kind"] == "automatic_alpha_with_agent_corrections"
    assert h.checkpoint["alpha_assisted_corrections"][0]["unassisted_success"] is False


def test_agent_correction_receipt_is_committed_before_promotion_and_recovers_after_interruption(environment):
    h = environment
    exhausted_empty_batch(h)
    h.snapshot_stages.add("alpha_source_observation_corrected")
    class CommittedCrash(RuntimeError):
        pass
    def committed_save(stage, state="constructing", error=None):
        h.save(stage, state, error)
        raise CommittedCrash("Original synthetic post-checkpoint interruption")
    with pytest.raises(CommittedCrash):
        accept_empty_correction(h, save=committed_save)
    saved = h.saves[-1]["checkpoint"]
    assert saved["alpha_chunks"]["0"]["accepted"]
    assert saved.get("alpha_completed_pages", 0) == 0 and saved.get("candidate") is None
    provider = SequenceProvider([patch((4, 5, 6, 7))])
    assert generate(h, provider) and len(provider.calls) == 1
    assert h.checkpoint["alpha_chunks"]["0"]["used"] == 5


@pytest.mark.parametrize("mutation", ["human_actor", "source_hash", "page_order", "page_hash", "changed_image",
                                       "parts", "other_failure", "unknown_schema"])
def test_agent_correction_rejects_unbound_or_nonempty_evidence_without_resetting_budget(environment, mutation):
    from pathlib import Path
    h = environment
    state = exhausted_empty_batch(h)
    history = deepcopy(state["trials"])
    review = source_review(h)
    trial = Path(history[-1])
    if mutation == "human_actor":
        review["actor_type"] = "human"
    elif mutation == "source_hash":
        review["source_sha256"] = "b" * 64
    elif mutation == "page_order":
        review["pages"].reverse()
    elif mutation == "page_hash":
        review["pages"][0]["sha256"] = "b" * 64
    elif mutation == "changed_image":
        Image.new("RGB", (32, 24), "red").save(h.pages / "page-000.png")
    elif mutation in {"parts", "unknown_schema"}:
        raw = json.loads((trial / "patch.json").read_bytes())
        if mutation == "parts":
            raw["new_instances"] = [part()]
        else:
            raw["human_review"] = "pass"
        (trial / "patch.json").write_bytes(canonical(raw))
    else:
        (trial / "rejected.json").write_bytes(canonical({"code": "invalid_alpha_patch", "message": "Missing actual geometry"}))
    with pytest.raises(ValueError):
        accept_empty_correction(h, review)
    assert state["used"] == state["limit"] == 5 and state["trials"] == history
    assert not state.get("accepted") and not state.get("corrections")
    assert not (h.directory / "alpha-corrections").exists()


@pytest.mark.parametrize("mutation", ["original_patch", "original_rejection", "corrected_patch", "receipt", "attempt_budget", "trial_history"])
def test_agent_correction_replay_rejects_evidence_or_budget_tampering_before_provider_call(environment, mutation):
    from pathlib import Path
    h = environment
    state = exhausted_empty_batch(h)
    receipt = accept_empty_correction(h)
    correction = Path(receipt["directory"])
    trial = Path(state["trials"][-1])
    if mutation == "attempt_budget":
        state["used"] = 4
    elif mutation == "trial_history":
        state["trials"].pop(0)
    else:
        target = {"original_patch": trial / "patch.json", "original_rejection": trial / "rejected.json",
                  "corrected_patch": correction / "patch.json", "receipt": correction / "correction-receipt.json"}[mutation]
        target.write_bytes(target.read_bytes() + b" ")
    provider = SequenceProvider([patch((4, 5, 6, 7))])
    with pytest.raises(ValueError):
        generate(h, provider)
    assert not provider.calls


def test_batches_resume_without_repeating_inference_and_keep_uncertain_material(environment):
    h = environment
    value = patch()
    value["new_instances"][0]["color_code"] = "43"
    value["uncertainties"] = [{"category": "material", "step_ids": ["synthetic-step-1"],
        "instance_ids": ["synthetic-a"], "reason": "Synthetic pale cyan transparent drawing.",
        "alternatives": ["Transparent clear47 remains a source-artwork alternative."]}]
    provider = SequenceProvider([value, patch((4, 5, 6, 7), number=2, identity="synthetic-b", section=False)])
    first = generate(h, provider, max_chunks=1)
    assert len(provider.calls) == 1 and h.saves[-1]["state"] == "paused"
    assert first.instances[0].color_code == "43"
    assert h.checkpoint["alpha_chunks"]["0"]["used"] == 1
    final = generate(h, provider)
    assert len(provider.calls) == 2 and len(final.steps) == 2
    assert h.checkpoint["alpha_completed_pages"] == 8
    assert len(h.checkpoint["alpha_page_observations"]) == 8
    assert [p.name for p in provider.calls[1]["images"]] == [f"page-{i:03d}.png" for i in range(4, 8)]
    assert "synthetic-a" in provider.calls[1]["prompt"]
    notes = json.loads((h.directory / "alpha-review-notes.json").read_text())
    assert notes["human_review"] == notes["physical_build"] == "not_run"
    assert notes["notes"][0]["category"] == "material" and notes["notes"][0]["review_status"] == "needs_review"
    assert notes["notes"][0]["alternatives"]
    assert generate(h, provider).model_dump(mode="json") == final.model_dump(mode="json")
    assert len(provider.calls) == 2


def test_persisted_five_attempt_ceiling_survives_retry(environment):
    h = environment
    invalid = patch()
    invalid["new_instances"][0]["color_code"] = "99999"
    provider = SequenceProvider([invalid] * 5)
    assert generate(h, provider) is None
    assert len(provider.calls) == 5 and "candidate" not in h.checkpoint
    assert h.saves[-1]["error"]["code"] == "alpha_attempt_limit"
    assert len(h.checkpoint["alpha_chunks"]["0"]["trials"]) == 5
    assert generate(h, provider) is None
    assert len(provider.calls) == 5
    h.job["config"]["max_chunk_attempts"] = 4
    with pytest.raises(ValueError, match="changed on resume"):
        generate(h, provider)


def test_crash_after_receipt_recovers_without_extra_call(environment):
    h = environment
    provider = SequenceProvider([patch(), patch((4, 5, 6, 7), number=2, identity="synthetic-b", section=False)])
    original = h.save
    def crash(stage, *args, **kwargs):
        original(stage, *args, **kwargs)
        if stage == "alpha_chunk_accepted":
            raise InterruptedError("Synthetic crash after durable receipt and before promotion")
    h.save = crash
    with pytest.raises(InterruptedError):
        generate(h, provider)
    assert len(provider.calls) == 1 and "candidate" not in h.checkpoint
    assert h.checkpoint["alpha_chunks"]["0"]["accepted"]["scene_sha256"]
    h.save = original
    scene = generate(h, provider)
    assert len(provider.calls) == 2 and len(scene.instances) == 2
    assert h.checkpoint["alpha_chunks"]["0"]["used"] == 1


@pytest.mark.parametrize("tamper", ["response", "source", "history", "trial_path"])
def test_accepted_recovery_rejects_changed_evidence(environment, tamper):
    h = environment
    provider = SequenceProvider([patch()])
    original = h.save
    def crash(stage, *args, **kwargs):
        original(stage, *args, **kwargs)
        if stage == "alpha_chunk_accepted":
            raise InterruptedError("Synthetic interrupted promotion")
    h.save = crash
    with pytest.raises(InterruptedError):
        generate(h, provider)
    h.save = original
    accepted = h.checkpoint["alpha_chunks"]["0"]["accepted"]
    if tamper == "response":
        from pathlib import Path
        target = Path(accepted["directory"]) / "patch.json"
        target.write_bytes(target.read_bytes() + b" ")
    elif tamper == "source":
        Image.new("RGB", (32, 24), "red").save(h.pages / "page-000.png")
    elif tamper == "history":
        accepted["previous_scene_sha256"] = "b" * 64
    else:
        accepted["directory"] = str(h.directory.parent / "another-job")
    with pytest.raises(ValueError):
        generate(h, provider)
    assert len(provider.calls) == 1


@pytest.mark.parametrize("code", ["authentication_required", "subscription_limit", "provider_unavailable", "invalid_schema", "unsupported_model"])
def test_provider_outage_or_configuration_error_escapes_without_more_attempts(environment, code):
    class Unavailable:
        def call(self, *args):
            raise ProviderFailure(code, "Original synthetic provider/configuration failure")
    with pytest.raises(ProviderFailure):
        generate(environment, Unavailable())
    assert environment.checkpoint["alpha_chunks"]["0"]["used"] == 1


def test_large_context_preserves_all_stable_ids_with_partial_pose_context(environment):
    value = patch()
    value["new_instances"] = [part(f"synthetic-{i:04d}") for i in range(500)]
    value["new_steps"] = [step(ids=[p["instance_id"] for p in value["new_instances"]])]
    value["new_steps"][0]["active_instance_ids"] = ["synthetic-0499"]
    value["quantity_evidence"] = []
    scene = expand(environment, value).model_dump(mode="json")
    before = deepcopy(scene)
    full = alpha.compact_alpha_context(scene)
    compact = alpha.compact_alpha_context(scene, max_bytes=20_000)
    assert full["omitted_pose_count"] == 0
    assert compact["omitted_pose_count"] > 0 and len(canonical(compact)) <= 20_000
    assert {identity for _, _, ids in compact["inventory_groups"] for identity in ids} == {
        p["instance_id"] for p in value["new_instances"]}
    assert any(row[0] == "synthetic-0499" for row in compact["instances"])
    assert scene == before


def test_multibooklet_continuation_preserves_old_source_sections_instances(environment):
    h = environment
    prior = expand(h, patch()).model_dump(mode="json")
    before = deepcopy(prior)
    h.job["guide_id"] = "booklet-02"
    h.guide["pdf_url"] = "https://www.lego.com/en-us/service/building-instructions/99999?booklet=2"
    value = patch(number=1, identity="synthetic-b")
    value["new_sections"][0]["section_id"] = "booklet-02-main"
    value["new_steps"][0]["section_id"] = "booklet-02-main"
    value["new_steps"][0]["step_id"] = "booklet-02-synthetic-1"
    value["page_observations"][0]["panels"][0]["section"] = "booklet-02-main"
    value["quantity_evidence"][0]["step_id"] = "booklet-02-synthetic-1"
    final = alpha.expand_alpha_patch(value, job=h.job, source_hash="b" * 64, page_count=8,
                                    page_indexes=(0, 1, 2, 3), previous=prior)
    assert prior == before
    assert final.source_sha256 == SOURCE and len(final.sources) == 2
    assert final.sources[0].model_dump(mode="json") == prior["sources"][0]
    assert final.sections[0].model_dump(mode="json") == prior["sections"][0]
    assert final.steps[0].model_dump(mode="json") == prior["steps"][0]
    assert final.instances[0].model_dump(mode="json") == prior["instances"][0]
    assert final.steps[-1].source.source_sha256 == "b" * 64
    assert len(final.instances) == 2


def test_curated_main_count_is_checked_without_claiming_full_coverage(environment):
    h = environment
    h.guide["expected_main_steps"] = 3
    provider = SequenceProvider([patch(), patch((4, 5, 6, 7), number=2, identity="synthetic-b", section=False)])
    assert generate(h, provider) is None
    assert h.checkpoint["alpha_completed_pages"] == 8
    assert h.saves[-1]["error"]["code"] == "alpha_source_coverage_mismatch"
    assert h.checkpoint["candidate"]["status"] == "needs_review"
    assert len(h.checkpoint["candidate"]["steps"]) == 2


def test_dedicated_alpha_geometry_cache_used_when_present(environment, monkeypatch):
    h = environment
    shared = h.store.data_dir / "public" / "alpha-ldraw"
    shared.mkdir()
    actual = []
    original = alpha.prepare_geometry
    def recorded(scene, directory, selected):
        actual.append(selected)
        return original(scene, directory, selected)
    monkeypatch.setattr(alpha, "prepare_geometry", recorded)
    generate(h, SequenceProvider([patch()]), max_chunks=1)
    assert actual == [shared]


def test_actual_page_hashes_are_retained_in_accepted_receipt(environment):
    h = environment
    h.snapshot_stages.add("alpha_constructing_chunk")
    scene = generate(h, SequenceProvider([patch()]), max_chunks=1)
    accepted = h.checkpoint["alpha_chunks"]["0"]["accepted"]
    assert accepted["scene_sha256"] == digest(scene)
    assert accepted["pages"][0]["sha256"] == hashlib.sha256((h.pages / "page-000.png").read_bytes()).hexdigest()
    reserved = next(item for item in h.saves if item["stage"] == "alpha_constructing_chunk")
    assert reserved["checkpoint"]["alpha_chunks"]["0"]["used"] == 1
    assert reserved["checkpoint"]["model_calls_used"] == 1
    assert h.saves[1]["stage"] == "model_call_reserved"


@pytest.mark.parametrize("empty_first", [True, False])
def test_genuine_noninstruction_chunks_preserve_candidate_and_coverage(environment, empty_first):
    h = environment
    pages = (0, 1, 2, 3) if empty_first else (4, 5, 6, 7)
    empty = patch(pages)
    for observation in empty["page_observations"]:
        observation["panels"] = []
        observation["description"] = "Original synthetic noninstruction page."
    empty.update(new_sections=[], new_instances=[], new_steps=[], quantity_evidence=[])
    values = [empty, patch((4, 5, 6, 7))] if empty_first else [patch(), empty]
    provider = SequenceProvider(values)
    final = generate(h, provider)
    assert len(provider.calls) == 2 and len(final.instances) == 1 and len(final.steps) == 1
    assert h.checkpoint["alpha_completed_pages"] == 8 and h.checkpoint["completed_panels"] == 1
    assert generate(h, provider).model_dump(mode="json") == final.model_dump(mode="json")
    assert len(provider.calls) == 2
    assert json.loads((h.directory / "coverage-index.json").read_text())["covered_step_keys"] == ["booklet-01-main:1"]


def test_noninstruction_pause_does_not_invent_a_candidate(environment):
    h = environment
    empty = patch()
    for observation in empty["page_observations"]:
        observation["panels"] = []
    empty.update(new_sections=[], new_instances=[], new_steps=[], quantity_evidence=[])
    assert generate(h, SequenceProvider([empty]), max_chunks=1) is None
    assert h.saves[-1]["state"] == "paused" and h.checkpoint["stage"] == "alpha_chunk_ready"
    assert "candidate" not in h.checkpoint and not (h.directory / "scene.json").exists()


def test_completed_candidate_or_source_tampering_is_rejected_on_idempotent_resume(environment):
    h = environment
    provider = SequenceProvider([patch(), patch((4, 5, 6, 7), number=2, identity="synthetic-b", section=False)])
    generate(h, provider)
    original = deepcopy(h.checkpoint["candidate"])
    h.checkpoint["candidate"]["steps"][-1]["poses"]["synthetic-a"]["position_ldu"][0] += 1
    with pytest.raises(ValueError, match="accepted receipt"):
        generate(h, provider)
    h.checkpoint["candidate"] = original
    Image.new("RGB", (32, 24), "red").save(h.pages / "page-000.png")
    with pytest.raises(ValueError, match="source page changed"):
        generate(h, provider)
    assert len(provider.calls) == 2


def test_generic_part_index_preserves_all_identities_with_bounded_descriptions(tmp_path):
    shared = tmp_path / "individual-only-cache"
    shared.mkdir()
    records = {}
    for index in range(30):
        relative = f"parts/synthetic{index}.dat"
        path = shared / relative
        path.parent.mkdir(exist_ok=True)
        path.write_text("0 Original synthetic individual shape " + "x" * 100 + "\n0 !LDRAW_ORG Part\n"
                        "0 !LICENSE Original synthetic test fixture only\n3 16 0 0 0 20 0 0 0 0 20\n")
        records[relative] = {"classification": "Part", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "url": "https://library.ldraw.org/library/official/" + relative}
    (shared / "provenance.json").write_text(json.dumps({"resources": records}))
    index = alpha.individual_part_index(shared, max_bytes=1500)
    assert len(index) == 30 and len(canonical(index)) <= 1500
    assert {row[0] for row in index} == {f"synthetic{i}" for i in range(30)}
    (shared / "parts/synthetic0.dat").write_bytes(b"changed")
    with pytest.raises(ValueError, match="individual provenance"):
        alpha.individual_part_index(shared)


def test_transparent_choice_automatically_retains_material_review_note(environment):
    value = patch()
    value["new_instances"][0]["color_code"] = "47"
    generate(environment, SequenceProvider([value]), max_chunks=1)
    notes = environment.checkpoint["alpha_review_notes"]
    assert notes[0]["category"] == "material" and notes[0]["instance_ids"] == ["synthetic-a"]
    assert notes[0]["alternatives"] and notes[0]["review_status"] == "needs_review"


def http_error(url, status=404):
    request = httpx.Request("GET", url)
    return httpx.HTTPStatusError("Original synthetic HTTP failure", request=request,
                                response=httpx.Response(status, request=request))


def test_missing_new_individual_part_repairs_with_durable_feedback(environment, monkeypatch):
    h = environment
    first = patch()
    first["new_instances"][0]["part_id"] = "synthetic404"
    second = patch()
    second["uncertainties"] = [{"category": "part_variant", "step_ids": ["synthetic-step-1"],
        "instance_ids": ["synthetic-a"], "reason": "Synthetic missing design re-identified from fixture source.",
        "alternatives": ["Missing synthetic404 was rejected; synthetic1 is an original test design."]}]
    original = alpha.prepare_geometry
    def missing(scene, directory, shared):
        if any(part.part_id == "synthetic404" for part in scene.instances):
            raise http_error("https://library.ldraw.org/library/official/parts/synthetic404.dat")
        return original(scene, directory, shared)
    monkeypatch.setattr(alpha, "prepare_geometry", missing)
    provider = SequenceProvider([first, second])
    scene = generate(h, provider, max_chunks=1)
    assert len(provider.calls) == 2 and scene.instances[0].part_id == "synthetic1"
    state = h.checkpoint["alpha_chunks"]["0"]
    assert state["used"] == 2 and len(state["trials"]) == 2
    assert state["feedback"][0]["code"] == "invalid_alpha_patch"
    assert "synthetic404" in state["feedback"][0]["message"] and "HTTP404" in state["feedback"][0]["message"]
    assert "HTTP404" in provider.calls[1]["prompt"] and "no generic substitution" in provider.calls[1]["prompt"]
    from pathlib import Path
    assert (Path(state["trials"][0]) / "rejected.json").is_file()
    assert (Path(state["trials"][0]) / "patch.json").is_file()
    assert state["accepted"]["scene_sha256"] == digest(scene)


@pytest.mark.parametrize("url,status", [
    ("https://www.lego.com/cdn/product-assets/source.pdf", 404),
    ("https://library.ldraw.org/library/official/p/missing.dat", 404),
    ("https://library.ldraw.org/library/official/parts/s/missing.dat", 404),
    ("https://library.ldraw.org/library/official/LDConfig.ldr", 404),
    ("https://untrusted.example/parts/synthetic1.dat", 404),
    ("https://library.ldraw.org/library/official/parts/synthetic1.dat?token=synthetic", 404),
    ("https://library.ldraw.org/library/official/parts/synthetic1.dat", 503),
])
def test_other_http_failures_are_not_softened(environment, monkeypatch, url, status):
    h = environment
    def fail(*args):
        raise http_error(url, status)
    monkeypatch.setattr(alpha, "prepare_geometry", fail)
    provider = SequenceProvider([patch()])
    with pytest.raises(httpx.HTTPStatusError):
        generate(h, provider, max_chunks=1)
    assert len(provider.calls) == 1 and h.checkpoint["alpha_chunks"]["0"]["used"] == 1
    assert not h.checkpoint["alpha_chunks"]["0"]["feedback"]
    assert "candidate" not in h.checkpoint


def test_missing_accepted_part_cannot_be_replaced_by_a_new_patch(environment, monkeypatch):
    h = environment
    provider = SequenceProvider([patch()])
    generate(h, provider, max_chunks=1)
    old = deepcopy(h.checkpoint["candidate"])
    value = patch((4, 5, 6, 7), number=2, identity="synthetic-b", section=False)
    value["new_instances"][0]["part_id"] = "synthetic2"
    def fail(*args):
        raise http_error("https://library.ldraw.org/library/official/parts/synthetic1.dat")
    monkeypatch.setattr(alpha, "prepare_geometry", fail)
    provider = SequenceProvider([value])
    with pytest.raises(httpx.HTTPStatusError):
        generate(h, provider)
    assert h.checkpoint["candidate"] == old and len(provider.calls) == 1
    assert h.checkpoint["alpha_chunks"]["1"]["used"] == 1
    assert not h.checkpoint["alpha_chunks"]["1"]["feedback"]


def test_partial_catalogue_does_not_prevent_host_resolving_a_source_identified_design(environment, monkeypatch):
    h = environment
    prepared = []
    original = alpha.prepare_geometry
    def record(scene, directory, shared):
        prepared.append({part.part_id for part in scene.instances})
        return original(scene, directory, shared)
    monkeypatch.setattr(alpha, "prepare_geometry", record)
    class Inspect(SequenceProvider):
        def call(self, prompt, images, schema, evidence, check):
            # The empty synthetic cache is deliberately NOT the allowed Part universe.
            assert "cache is partial" in prompt
            assert "Absence from the supplied cache alone is never a blocker" in prompt
            assert "host resolves proposed designs" in prompt
            assert '"all_verified_individual_part_id_description_rows":[]' in prompt
            assert "partial_cached_individual_geometry_not_a_design_allowlist" in prompt
            assert "FULL-PAGE normalized [left, top, right, bottom]" in prompt
            assert "NEVER emit pixel rectangles" in prompt
            assert "[64,48,320,240]" in prompt and "[0.1,0.1,0.5,0.5]" in prompt
            assert "Each call is one partial booklet batch" in prompt
            assert "absence of assembly panels" in prompt
            assert "blockers=[]" in prompt and "host advances to the next batch" in prompt
            body = json.loads(prompt[prompt.index('{"set_number"'):])
            assert body["input_image_dimensions"] == [{"page_index": index, "width_pixels": 32,
                "height_pixels": 24, "bbox_units": "full_page_normalized_left_top_right_bottom"}
                for index in range(4)]
            return super().call(prompt, images, schema, evidence, check)
    scene = generate(h, Inspect([patch()]), max_chunks=1)
    assert scene.instances[0].part_id == "synthetic1"
    assert prepared == [{"synthetic1"}]


@pytest.mark.parametrize("target", ["panel", "part", "step", "quantity"])
def test_pixel_rectangles_are_rejected_in_every_source_region(environment, target):
    value = patch()
    if target == "panel":
        source = value["page_observations"][0]["panels"][0]
    elif target == "part":
        source = value["new_instances"][0]["source"]
    elif target == "step":
        source = value["new_steps"][0]["source"]
    else:
        source = value["quantity_evidence"][0]["source"]
    source["bbox"] = [0, 0, 32, 24]
    with pytest.raises(ValueError):
        expand(environment, value)
