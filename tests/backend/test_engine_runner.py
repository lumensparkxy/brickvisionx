import json
from types import SimpleNamespace
import pytest
from guide2build.engine.contracts import PageIndex, strict_schema
from guide2build.engine.provider import ProviderFailure
from guide2build.engine.runner import run_once, validate_candidate
from guide2build.engine.store import EngineStore


@pytest.fixture
def source(monkeypatch, tmp_path):
    import guide2build.engine.runner as runner
    import guide2build.engine.connectors as connectors
    from PIL import Image
    digest = "a" * 64
    monkeypatch.setattr(runner, "cached_receipt", lambda *args: {"sha256": digest})
    monkeypatch.setattr(runner, "render_pages", lambda *args, **kwargs: [{}]*8)
    monkeypatch.setattr(connectors, "connector_context", lambda *args: {"synthetic_control_flow_test": True})
    pages = tmp_path / 'public/pages' / digest
    pages.mkdir(parents=True)
    for index in range(8):
        Image.new('RGB', (64, 64), 'white').save(pages / f'page-{index:03d}.png')
    return tmp_path, digest


class Unavailable:
    def call(self, *args):
        raise ProviderFailure("authentication_required", "login required")


def test_provider_auth_pauses_all_jobs_and_keeps_source_checkpoint(source):
    root, digest = source
    store = EngineStore(root)
    job = store.enqueue("30669", "alt-02", {"model": "test"})
    assert run_once(store, Unavailable())
    result = store.get(job["id"])
    assert result["state"] == "blocked"
    assert result["checkpoint"]["source_sha256"] == digest
    assert result["error"]["code"] == "authentication_required"
    assert store.claim("another") is None
    assert (store.root / "jobs" / job["id"] / "source-receipt.json").is_file()


class BadOutput:
    def __init__(self):
        self.calls = 0

    def call(self, *args):
        self.calls += 1
        return {"panels": "invalid", "uncertainty": []}


def test_malformed_output_has_three_attempts_and_never_candidate(source):
    root, _ = source
    store = EngineStore(root)
    job = store.enqueue("30669", "alt-02", {"model": "test"})
    provider = BadOutput()
    run_once(store, provider)
    assert provider.calls == 3
    assert store.get(job["id"])["error"]["code"] == "proposal_rejected"
    assert "candidate" not in store.get(job["id"])["checkpoint"]
    assert store.provider_pause() is None


def test_default_strict_budget_is_durable_after_rejected_retry(source):
    root, _ = source
    store = EngineStore(root)
    job = store.enqueue("30669", "alt-02", {})
    provider = BadOutput()
    assert run_once(store, provider, job_id=job["id"])
    first = store.get(job["id"])
    assert first["checkpoint"]["model_calls_used"] == provider.calls == 3
    store.retry(job["id"])
    assert run_once(store, provider, job_id=job["id"])
    resumed = store.get(job["id"])
    assert resumed["state"] == "paused" and resumed["error"]["code"] == "model_call_budget_exhausted"
    assert resumed["checkpoint"]["model_calls_used"] == provider.calls == 3
    assert resumed["checkpoint"]["attempts"] == first["checkpoint"]["attempts"]


@pytest.mark.parametrize("code", ["authentication_required", "rate_limited", "quota_exceeded", "unsupported_model"])
def test_adk_fatal_failures_do_not_retry_or_fallback(source, code):
    root, _ = source
    store = EngineStore(root)
    job = store.enqueue("30669", "alt-02", {})
    class Failure:
        calls = 0
        def call(self, *args):
            self.calls += 1
            raise ProviderFailure(code, "Synthetic classified ADK failure")
    provider = Failure()
    assert run_once(store, provider, job_id=job["id"])
    latest = store.get(job["id"])
    assert latest["error"]["code"] == code
    assert latest["checkpoint"]["model_calls_used"] == provider.calls == 1
    assert latest["checkpoint"]["runtime_choice"]["provider"] == "google_adk"


def test_invalid_provider_schema_does_not_pause_unrelated_jobs(source):
    root, _ = source
    store = EngineStore(root)
    job = store.enqueue('30669', 'alt-02', {'model': 'test'})
    class InvalidSchema:
        calls = 0
        def call(self, *args):
            self.calls += 1
            raise ProviderFailure('invalid_schema', 'Synthetic provider schema rejection')
    provider = InvalidSchema()
    assert run_once(store, provider)
    assert provider.calls == 1
    assert store.get(job['id'])['error']['code'] == 'invalid_schema'
    assert store.provider_pause() is None


def test_strict_index_rejects_bad_bounds():
    with pytest.raises(ValueError):
        PageIndex.model_validate({"panels": [{"section": "main", "number": 1, "label": "one",
            "bbox": [0, 0, 2, 1], "kind": "main"}], "uncertainty": []})
    schema = strict_schema(PageIndex)
    assert schema["additionalProperties"] is False
    assert "number" in schema["$defs"]["Panel"]["required"]


def test_spatial_proposal_schema_has_supported_bounded_arrays():
    from guide2build.engine.instruction import proposal_type
    schema = strict_schema(proposal_type())
    def check(node):
        if isinstance(node, dict):
            if node.get('type') == 'array':
                assert 'items' in node and 'prefixItems' not in node
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)
    check(schema)
    bbox = schema['$defs']['SequenceEvidence']['properties']['bbox']
    assert bbox['minItems'] == bbox['maxItems'] == 4 and bbox['items']['type'] == 'number'


def test_model_cannot_self_certify_or_rewrite_prior_checkpoint(monkeypatch):
    import guide2build.engine.runner as runner
    digest = "a"*64
    source = SimpleNamespace(source_sha256=digest, page_index=0)
    scene = SimpleNamespace(set_number="30669", guide_id="alt-02", source_sha256=digest,
        sources=[source], status="candidate", geometry_check="not_run", connector_check="pass",
        physical_build_check="not_run", instances=[], steps=[])
    monkeypatch.setattr(runner, "scene_type", lambda: SimpleNamespace(model_validate_json=lambda _: scene))
    with pytest.raises(ValueError, match="self-certify"):
        validate_candidate(json.dumps({}), {"set_number": "30669", "guide_id": "alt-02"}, digest, 8)


def test_continuation_booklet_blocks_without_validated_predecessor(tmp_path):
    store = EngineStore(tmp_path)
    job = store.enqueue("10316", "booklet-02", {"model": "test", "revision": "campaign"})
    provider = BadOutput()
    assert run_once(store, provider)
    result = store.get(job["id"])
    assert result["state"] == "blocked"
    assert result["error"]["code"] == "prior_booklet_required"
    assert provider.calls == 0


def test_exact_panel_provenance_rejects_in_range_wrong_page(scene_data):
    from guide2build.core.models import SceneManifest
    from guide2build.releases.models import adapt_v1
    scene = adapt_v1(SceneManifest.model_validate(scene_data),
                     "https://www.lego.com/en-us/service/building-instructions/30669", 10)
    for part in scene.instances:
        part.origin = "vision_proposal"
        part.mapping_status = "candidate"
    scene.geometry_check = scene.connector_check = scene.physical_build_check = "not_run"
    with pytest.raises(ValueError, match="exact requested"):
        validate_candidate(scene.model_dump_json(), {"set_number": scene.set_number, "guide_id": scene.guide_id},
                           scene.source_sha256, 10, panel={"number": 1}, page_index=9)


def test_resumed_cross_page_panel_receives_target_preceding_page_and_alignment(source, monkeypatch):
    import guide2build.engine.alignment_context as alignment_context
    root, digest = source
    # Synthetic transport probe; the context reader has separate integrity/geometry tests.
    monkeypatch.setattr(alignment_context, 'accepted_alignment_context',
                        lambda *args: {'step_id': 'synthetic-prior-alignment', 'source_page': 0})
    store = EngineStore(root)
    job = store.enqueue('30669', 'alt-02', {'model': 'test'})
    store.claim('seed')
    def panel(number):
        return {'section': 'main', 'number': number, 'label': str(number), 'bbox': [0,0,1,1], 'kind': 'main'}
    indexes = [{'panels': [panel(1)], 'uncertainty': []},
               {'panels': [panel(n) for n in range(2,13)], 'uncertainty': []}] + [{'panels': [], 'uncertainty': []} for _ in range(6)]
    store.checkpoint(job['id'], 'seed', {'page_indexes': indexes, 'completed_panels': 1}, 'blocked')
    store.retry(job['id'])
    class Inspect:
        def call(self, prompt, images, *args):
            assert [p.name for p in images] == ['page-001.png', 'page-000.png']
            assert 'target page' in prompt and 'page_index must equal the exact' in prompt
            assert 'synthetic-prior-alignment' in prompt and 'do not copy old pixel coordinates' in prompt
            return {'delta_json': None, 'blockers': ['Test only; no assembly evidence'], 'observations': []}
    assert run_once(store, Inspect())
    assert store.get(job['id'])['state'] == 'blocked'
    assert store.get(job['id'])['checkpoint']['total_panels'] == 12


@pytest.mark.parametrize('artifact_kind', [None, 'assisted_alpha_continuation'])
def test_validation_retains_assistance_lineage_without_granting_approval(source, monkeypatch, artifact_kind):
    """Synthetic completed checkpoint exercises reporting only, not reconstruction accuracy."""
    import guide2build.engine.rendering as rendering
    from guide2build.engine.store import PIPELINE
    root, digest = source
    store = EngineStore(root)
    config = {'model': 'test', 'max_model_calls': 100}
    if artifact_kind:
        config['artifact_kind'] = artifact_kind
    job = store.enqueue('30669', 'alt-02', config)
    store.claim('seed', job_id=job['id'])
    indexes = [{'panels': [{'section': 'main', 'number': n, 'label': str(n),
        'bbox': [0, 0, 1, 1], 'kind': 'main'} for n in range(1, 13)], 'uncertainty': []}]
    indexes += [{'panels': [], 'uncertainty': []} for _ in range(7)]
    lineage = {'parent_job_id': 'synthetic-parent', 'inherited_main_steps': 1}
    store.checkpoint(job['id'], 'seed', {'runner_version': PIPELINE, 'page_indexes': indexes,
        'completed_panels': 12, 'candidate': {'instances': [], 'steps': []},
        'reused_evidence': lineage if artifact_kind else None}, 'paused')
    def synthetic_render(path, geometry, output, **kwargs):
        output.mkdir(parents=True)
        report = {'steps': []}
        (output / 'report.json').write_text(json.dumps(report))
        return report
    monkeypatch.setattr(rendering, 'render_candidate', synthetic_render)
    class SyntheticReview:
        def call(self, prompt, images, *args):
            return {'coverage_agrees': True, 'assembly_agrees': True, 'findings': []}
    assert run_once(store, SyntheticReview(), job_id=job['id'])
    report = json.loads((store.root / 'jobs' / job['id'] / 'validation.json').read_text())
    assert report['artifact_kind'] == (artifact_kind or 'automatic_reconstruction')
    assert report['reused_evidence'] == (lineage if artifact_kind else None)
    assert report['human_review'] == report['physical_build'] == report['connector_check'] == 'not_run'
    result = store.get(job['id'])
    assert result['state'] == 'blocked'
    assert result['error']['code'] == 'assembly_validation_required'


@pytest.mark.parametrize("reject_visual", [False, True])
def test_guided_run_indexes_then_stops_and_resumes_one_panel(source, scene_data, monkeypatch, reject_visual):
    """Synthetic proposals test control flow only, never official build accuracy."""
    from copy import deepcopy
    import guide2build.engine.geometry as geometry
    import guide2build.engine.rendering as rendering
    import guide2build.engine.instruction as instruction
    import guide2build.engine.spatial as spatial
    import guide2build.engine.alignment_context as alignment_context
    root, digest = source
    store = EngineStore(root)
    other = store.enqueue("30669", "alt-01", {"model": "test"})
    job = store.enqueue("30669", "alt-02", {"model": "test", "max_model_calls": 100})
    monkeypatch.setattr(geometry, "prepare_geometry", lambda *args: {"synthetic_test": True})
    monkeypatch.setattr(alignment_context, "accepted_alignment_context", lambda *args: None)
    monkeypatch.setattr(spatial, "solve_candidate", lambda scene, *args: (scene, {"synthetic_test": True}))
    monkeypatch.setattr(instruction, "source_views_for", lambda scene, *args:
                        ({scene.steps[-1].step_id: {"status": "fitted"}}, {scene.steps[-1].step_id: {}}))
    def synthetic_render(path, geometry, output, *, check, first_step, source_views):
        data = json.loads(path.read_text())
        output.mkdir(parents=True)
        assert first_step == len(data['steps'])  # Only this test's new instruction.
        (output / 'test.png').write_bytes(b'synthetic control-flow fixture')
        result = {'steps': [{'step_id': data['steps'][-1]['step_id'], 'screenshot': 'test.png'}]}
        (output / 'report.json').write_text(json.dumps(result))
        return result
    monkeypatch.setattr(rendering, "render_candidate", synthetic_render)

    class SyntheticProvider:
        indexes = 0
        constructions = 0

        def call(self, prompt, images, *args):
            if "Review this single proposed instruction" in prompt:
                assert len(images) == 2 and images[-1].read_bytes() == b'synthetic control-flow fixture'
                return {'coverage_agrees': True, 'assembly_agrees': not reject_visual,
                        'findings': [{'category': 'side', 'step_ids': [], 'instance_ids': [],
                            'description': 'Wrong attachment side', 'correction': 'Use the source-indicated wing'}]
                            if reject_visual else []}
            if "Index all instruction panels" in prompt:
                panels = [{"section": "main", "number": n, "label": str(n),
                           "bbox": [0, 0, 1, 1], "kind": "main"} for n in range(1, 13)] if self.indexes == 0 else []
                self.indexes += 1
                return {"panels": panels, "uncertainty": []}
            ordinal = store.get(job['id'])['checkpoint'].get('completed_panels', 0)
            self.constructions += 1
            part = deepcopy(scene_data["instances"][ordinal])
            part["origin"] = "vision_proposal"
            part["source"]["source_sha256"] = digest
            step = deepcopy(scene_data["steps"][ordinal])
            step["section_id"] = "main"
            step['action'] = 'add_parts'
            step['assembly_group_id'] = None
            step["source"]["source_sha256"] = digest
            delta = {"new_sections": [{"section_id": "main", "source_sha256": digest,
                      "label": "Synthetic test"}] if ordinal == 0 else [],
                     "new_instances": [part], "new_steps": [step]}
            return {"delta_json": json.dumps(delta), "blockers": [], "observations": ["Synthetic test only"],
                    "sequence": [{"step_id": step['step_id'], "kind": "printed_main", "printed_label": str(ordinal+1),
                                  "bbox": [0,0,1,1], "explanation": "Synthetic test only"}],
                    "source_views": [{"step_id": step['step_id'], "landmarks": [], "view_family": "unconstrained"}]}

    provider = SyntheticProvider()
    assert run_once(store, provider, job_id=job["id"], max_panels=1)
    first = store.get(job["id"])
    if reject_visual:
        assert first['state'] == 'blocked'
        assert first['error']['code'] == 'instruction_repair_exhausted'
        assert 'candidate' not in first['checkpoint']
        assert not (store.root / 'jobs' / job['id'] / 'scene.json').exists()
        assert list((store.root / 'jobs' / job['id'] / 'proposals').glob('*/visual-review.json'))
        assert provider.constructions == 3
        store.retry(job['id'])
        assert run_once(store, provider, job_id=job['id'], max_panels=1)
        assert provider.constructions == 3  # Retry does not grant a fresh instruction budget.
        return
    assert first["state"] == "paused", first["error"]
    assert first['checkpoint']['panel_reviews'][0]['review']['assembly_agrees']
    assert first["owner"] is None
    assert first["checkpoint"]["completed_panels"] == 1
    assert provider.indexes == 8 and provider.constructions == 1
    assert run_once(store, provider, job_id=job["id"], max_panels=1)
    second = store.get(job["id"])
    assert second["state"] == "paused", second["error"]
    assert second["checkpoint"]["completed_panels"] == 2
    assert provider.indexes == 8 and provider.constructions == 2
    assert second["checkpoint"]["candidate"]["steps"][:1] == first["checkpoint"]["candidate"]["steps"]
    assert store.get(other["id"])["state"] == "queued"

    # An already completed construction does not accidentally enter whole-booklet review.
    store.claim("seed", job_id=job["id"])
    checkpoint = second["checkpoint"]
    checkpoint["completed_panels"] = 12
    store.checkpoint(job["id"], "seed", checkpoint, "paused")
    assert run_once(store, provider, job_id=job["id"], max_panels=1)
    assert store.get(job["id"])["checkpoint"]["stage"] == "construction_complete_needs_validation"
    assert provider.constructions == 2
