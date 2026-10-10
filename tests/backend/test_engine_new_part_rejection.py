"""Synthetic resolver + real checkpoint/lease + actual exploration orchestration.
No model, geometry download, source retrieval, production mutation or accuracy claim.
"""

from contextlib import contextmanager
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import httpx
import pytest

from guide2build.engine import closure_publication as pub, exploration, geometry
from guide2build.engine.store import EngineStore, LeaseLost, execution_config
from guide2build.reconstruction.asset_errors import UnsupportedIndividualClosure
from guide2build.reconstruction.individual_closure import Cache, Fence, canonical, sha
from test_engine_exploration import harness as harness, SOURCE

STAGED = Path(__file__).resolve().parents[2]
REAL_PREPARE = geometry.prepare_geometry


def dat(kind="Part", refs=(), *, license=True):
    return (
        f"0 synthetic individual fixture\n0 !LDRAW_ORG {kind}\n"
        + ("0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt\n" if license else "")
        + "".join(f"1 16 0 0 0 1 0 0 0 1 0 0 0 1 {ref}\n" for ref in refs)
        + "3 16 0 0 0 1 0 0 0 1 0\n"
    ).encode()


def tree(path):
    return {str(p.relative_to(path)): sha(p.read_bytes()) for p in sorted(path.rglob("*")) if p.is_file()}


def seed(path, parts=None):
    path.mkdir(parents=True, exist_ok=True)
    mat = b"0 !LDRAW_ORG Configuration\n0 !COLOUR Synthetic CODE 4 VALUE #FF0000 EDGE #333333\n"
    (path / "LDConfig.ldr").write_bytes(mat)
    doc = {
        "library": pub.BASE,
        "scope": "synthetic test only",
        "resources": {},
        "file_map": {},
        "roots": [],
        "materials": {
            "LDConfig.ldr": {"url": pub.BASE + "LDConfig.ldr", "sha256": sha(mat), "bytes": len(mat)}
        },
    }
    for relative, data in (parts or {}).items():
        p = path / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        content = data.decode()
        classification = content.split("!LDRAW_ORG ")[1].splitlines()[0]
        notices = [
            line
            for line in content.splitlines()
            if line.startswith(("0 Author:", "0 !LICENSE", "0 !HISTORY"))
        ]
        doc["resources"][relative] = {
            "url": pub.BASE + relative,
            "sha256": sha(data),
            "bytes": len(data),
            "classification": classification,
            "notices": notices,
            "description": "synthetic individual fixture",
            "dependencies": [],
        }
        doc["file_map"][relative.removeprefix("parts/").removeprefix("p/")] = relative
        if relative.startswith("parts/") and classification == "Part":
            doc["roots"].append(Path(relative).stem)
    (path / "provenance.json").write_bytes(canonical(doc))
    return doc


@pytest.fixture
def resolver(monkeypatch):
    sys.path.insert(0, str(STAGED / "tools"))
    spec = importlib.util.spec_from_file_location("staged_resolver_test", STAGED / "tools/fetch_parts.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    bodies = {
        "parts/newa.dat": dat(refs=("a-good.dat", "b-short.dat")),
        "p/a-good.dat": dat("Primitive"),
        "p/b-short.dat": dat("Shortcut"),
        "parts/newb.dat": dat(refs=("a-good.dat",)),
        "parts/synthetic.dat": dat(),
    }
    requests = []
    statuses = {}
    headers = {}
    hooks = {}

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False and kwargs["headers"]["Accept-Encoding"] == "identity"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @contextmanager
        def stream(self, method, url):
            assert method == "GET" and url.startswith(pub.BASE)
            path = url.removeprefix(pub.BASE)
            requests.append(path)
            if path in hooks:
                hooks[path]()
            error = statuses.get(path)
            if isinstance(error, BaseException):
                raise error
            response = httpx.Response(
                error or (200 if path in bodies else 404),
                content=bodies.get(path, b"absent"),
                headers={},
                request=httpx.Request(method, url),
            )
            response.headers.update(headers.get(path, {}))
            yield response

    monkeypatch.setattr(module.httpx, "Client", Client)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    return SimpleNamespace(
        module=module, bodies=bodies, requests=requests, statuses=statuses, headers=headers, hooks=hooks
    )


@pytest.fixture
def publication(tmp_path):
    store = EngineStore(tmp_path)
    job = store.enqueue(
        "30669",
        "alt-02",
        {"execution_policy": "explore", "new_part_failure_profile": pub.PROFILE, "model": "offline"},
    )
    job = store.claim("offline-owner", job_id=job["id"])
    directory = store.root / "jobs" / job["id"]
    directory.mkdir(parents=True)
    trial = directory / "exploration/instructions/0000/attempt-1"
    trial.mkdir(parents=True)
    cp = job["checkpoint"]

    def save(stage):
        cp["stage"] = stage
        store.checkpoint(job["id"], "offline-owner", cp)

    p = pub.Publications(
        job_id=job["id"],
        directory=directory,
        trial=trial,
        checkpoint=cp,
        save=save,
        check=lambda: None,
        lease_check=lambda: store.heartbeat(job["id"], "offline-owner"),
        scope={
            "source_sha256": SOURCE,
            "page_index": 0,
            "policy_sha256": "b" * 64,
            "raw_scene_sha256": "c" * 64,
        },
    )
    private = directory / "geometry"
    shared = tmp_path / "public/ldraw"
    seed(private)
    seed(shared)
    return SimpleNamespace(store=store, job=job, cp=cp, p=p, private=private, shared=shared, trial=trial)


def staged_root(env, resolver, root="newb"):
    fence = Fence()
    cache = Cache(env.private, fence)
    shared = Cache(env.shared, fence)
    stage = env.trial / "part-closures" / root
    if env.p.retained(root):
        journal = env.p.authenticate(root, stage / "publication.json")
        addition = journal["addition"] | {"roots": journal["roots"]}
    else:
        addition = resolver.module.stage_individual(root, stage, [cache, shared], env.p.check)
    pub.publish(root, stage, addition, cache, shared, env.p, resolver.module)
    return stage


def test_real_staged_closure_rejects_without_publishing_then_later_root_succeeds(publication, resolver):
    e = publication
    before = tree(e.private)
    base = tree(e.shared)
    with pytest.raises(UnsupportedIndividualClosure) as raised:
        resolver.module.stage_individual(
            "newa", e.trial / "bad", [Cache(e.private, Fence()), Cache(e.shared, Fence())]
        )
    assert raised.value.evidence[0].classification == "Shortcut"
    assert not (e.trial / "bad/p/b-short.dat").exists()
    assert (e.trial / "bad/p/a-good.dat").exists()
    assert tree(e.private) == before and tree(e.shared) == base
    stage = staged_root(e, resolver)
    assert e.p.retained("newb")["status"] == "committed"
    assert json.loads((e.private / "provenance.json").read_text())["roots"] == ["newb"]
    assert (e.private / "p/a-good.dat").read_bytes() == dat("Primitive")
    assert (stage / "publication.json").exists()
    assert e.store.get(e.job["id"])["checkpoint"]["geometry_publications"] == e.cp["geometry_publications"]


@pytest.mark.parametrize(
    "bad", ["license", "path", "encoding", "unknown", "missingclassification", "primitive_root", "too_big"]
)
def test_new_design_combined_envelope_failures_are_hard(publication, resolver, bad):
    e = publication
    before = tree(e.private)
    data = {
        "license": dat("Shortcut", license=False),
        "path": dat("Shortcut", refs=("../secret.dat",)),
        "encoding": b"\xff",
        "unknown": dat("Future_Unknown"),
        "missingclassification": b"0 !LICENSE ok\n",
        "primitive_root": dat("Primitive"),
        "too_big": dat("Shortcut") + b"x" * 1_000_001,
    }[bad]
    resolver.bodies["parts/newa.dat"] = data
    with pytest.raises((ValueError, UnicodeDecodeError)):
        resolver.module.stage_individual(
            "newa", e.trial / "bad", [Cache(e.private, Fence()), Cache(e.shared, Fence())]
        )
    assert tree(e.private) == before


@pytest.mark.parametrize("bad", ["license", "unsafe", "cached_hash", "cached_receipt"])
def test_later_permitted_sibling_integrity_wins_over_shortcut(publication, resolver, bad):
    e = publication
    resolver.bodies["parts/newa.dat"] = dat(refs=("b-short.dat", "z-later.dat"))
    resolver.bodies["p/z-later.dat"] = dat(
        "Primitive", license=bad != "license", refs=("../escape.dat",) if bad == "unsafe" else ()
    )
    if bad.startswith("cached"):
        seed(e.shared, {"p/z-later.dat": dat("Primitive")})
        if bad == "cached_hash":
            (e.shared / "p/z-later.dat").write_bytes(b"changed")
        else:
            doc = json.loads((e.shared / "provenance.json").read_text())
            doc["resources"]["p/z-later.dat"]["url"] = "https://evil.invalid/p/z-later.dat"
            (e.shared / "provenance.json").write_bytes(canonical(doc))
    before = tree(e.private)
    with pytest.raises(ValueError):
        resolver.module.stage_individual(
            "newa", e.trial / "bad", [Cache(e.private, Fence()), Cache(e.shared, Fence())]
        )
    assert tree(e.private) == before


@pytest.mark.parametrize(
    "phase",
    [
        "after_checkpoint_pin",
        "after_file:p/a-good.dat",
        "after_file:parts/newb.dat",
        "after_provenance_replace",
        "before_completion_pin",
        "after_completion_pin",
    ],
)
def test_actual_leased_commit_recovers_at_each_authenticated_crash_point(publication, resolver, phase):
    class Crash(BaseException):
        pass

    e = publication
    once = []

    def crash(value):
        if value == phase and not once:
            once.append(value)
            raise Crash()

    e.p.phase_hook = crash
    with pytest.raises(Crash):
        staged_root(e, resolver)
    reserved = len(resolver.requests)
    # Rehydrate trusted state from SQLite, rather than reusing the mutated in-memory dict.
    restored = e.store.get(e.job["id"])["checkpoint"]
    e.cp.clear()
    e.cp.update(restored)
    e.p.phase_hook = lambda _: None
    staged_root(e, resolver)
    assert len(resolver.requests) == reserved and e.p.retained("newb")["status"] == "committed"
    assert (
        e.store.get(e.job["id"])["checkpoint"]["geometry_publications"][e.p.key("newb")]["status"]
        == "committed"
    )


def test_unpinned_journal_is_never_enrolled(publication, resolver):
    class Crash(BaseException):
        pass

    e = publication
    e.p.phase_hook = lambda phase: (
        (_ for _ in ()).throw(Crash()) if phase == "before_checkpoint_pin" else None
    )
    before = tree(e.private)
    with pytest.raises(Crash):
        staged_root(e, resolver)
    assert tree(e.private) == before and not e.p.retained("newb")
    e.p.phase_hook = lambda _: None
    with pytest.raises((ValueError, FileExistsError)):
        staged_root(e, resolver)
    assert tree(e.private) == before


@pytest.mark.parametrize(
    "target",
    [
        "publication.json",
        "merged-provenance.json",
        "p/a-good.dat",
        "destination",
        "shared_manifest",
        "commitment",
    ],
)
def test_pinned_recovery_rejects_tamper(publication, resolver, target):
    class Crash(BaseException):
        pass

    e = publication

    def crash(phase):
        if phase == "after_checkpoint_pin":
            raise Crash()

    e.p.phase_hook = crash
    with pytest.raises(Crash):
        staged_root(e, resolver)
    stage = e.trial / "part-closures/newb"
    e.p.phase_hook = lambda _: None
    if target == "destination":
        (e.private / "parts").mkdir()
        (e.private / "parts/newb.dat").write_bytes(b"not authorized")
    elif target == "shared_manifest":
        (e.shared / "provenance.json").write_text("{}")
    elif target == "commitment":
        e.p.checkpoint["geometry_publications"] = {}
    else:
        (stage / target).write_bytes(b"changed")
    with pytest.raises((ValueError, FileExistsError, KeyError)):
        staged_root(e, resolver)
    assert e.p.retained("newb") is None or e.p.retained("newb")["status"] == "prepared"


def test_lease_loss_prevents_any_publication(publication, resolver):
    e = publication
    with e.store.connect() as con:
        con.execute("UPDATE engine_jobs SET owner=? WHERE id=?", ("someone-else", e.job["id"]))
    before = tree(e.private)
    with pytest.raises(LeaseLost):
        staged_root(e, resolver)
    assert tree(e.private) == before


@pytest.fixture
def integration(harness, resolver, monkeypatch):
    h = harness
    store = EngineStore(h.directory.parents[2])
    config = h.job["config"] | {"new_part_failure_profile": pub.PROFILE}
    job = store.enqueue("30669", "alt-02", config)
    job = store.claim("runner-owner", job_id=job["id"])
    target = store.root / "jobs" / job["id"]
    h.directory.rename(target)
    h.directory = target
    h.job = job
    h.args.update(job=job, directory=target, store=store)

    def save(stage, state="constructing", error=None):
        h.cp["stage"] = stage
        h.events.append({"stage": stage, "state": state, "error": error})
        store.checkpoint(job["id"], "runner-owner", h.cp, state, error)

    heartbeat = SimpleNamespace(check=lambda: None, store=store, owner="runner-owner")
    h.args.update(save=save, heartbeat=heartbeat)
    h.save = save
    h.store = store
    seed(target / "geometry")
    seed(target.parents[2] / "public/ldraw")
    monkeypatch.setattr(geometry, "prepare_geometry", REAL_PREPARE)
    original = h.provider.call

    def call(*args, **kwargs):
        result = original(*args, **kwargs)
        if isinstance(result, dict) and result.get("delta_json"):
            delta = json.loads(result["delta_json"])
            if delta["new_steps"][0]["main_step_number"] == 1:
                for part in delta["new_instances"]:
                    part.update(part_id="newa", geometry_ref="parts/newa.dat")
                result["delta_json"] = json.dumps(delta)
        return result

    h.provider.call = call
    return h


def test_actual_exploration_two_rejections_then_next_instruction_and_resume(integration):
    h = integration
    assert exploration.run_exploration(**h.args)
    assert h.cp["processed_panels"] == 2 and h.cp["reconstructed_panels"] == 1
    first, second = h.cp["instruction_results"]
    assert first["outcome"] == "unresolved" and first["attempt_count"] == 2 and not first["step_ids"]
    assert second["step_ids"] == ["synthetic-step-2"]
    assert h.cp["model_calls_used"] == 14 and h.cp["local_model_calls_used"] == 14
    for attempt in (1, 2):
        trial = h.directory / f"exploration/instructions/0000/attempt-{attempt}"
        receipt = json.loads((trial / "part-rejection.json").read_text())
        assert (
            receipt["roots"] == ["newa"] and receipt["source_sha256"] == SOURCE and receipt["page_index"] == 0
        )
        assert not (trial / "asset-report.json").exists()
    assert not (h.directory / "geometry/parts/newa.dat").exists()
    assert "unsupported_new_individual_design" in next(
        c["prompt"] for c in h.provider.calls if c["key"] == "instruction-0001-attempt-1-proposal"
    )
    before = len(h.provider.calls)
    h.store.claim("runner-owner", job_id=h.job["id"])
    assert exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == before and h.cp["model_calls_used"] == 14


@pytest.mark.parametrize("limit,attempts,expected", [(10, 2, 10), (100, 1, 11)])
def test_attempt_and_shared_budgets_are_not_extended(integration, limit, attempts, expected):
    h = integration
    h.job["config"].update(max_model_calls=limit, max_panel_attempts=attempts)
    exploration.run_exploration(**h.args)
    assert h.cp["model_calls_used"] == expected
    assert len([c for c in h.provider.calls if c["key"].startswith("instruction-0000")]) == attempts
    assert h.cp["instruction_results"][0]["attempt_count"] == attempts


def test_policy_enable_remove_or_change_cannot_resume_before_calls(integration, monkeypatch):
    h = integration
    exploration.run_exploration(**h.args, max_panels=1)
    count = len(h.provider.calls)
    h.job["config"].pop("new_part_failure_profile")
    with pytest.raises(ValueError, match="changed on resume"):
        exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == count
    h.job["config"]["new_part_failure_profile"] = pub.PROFILE
    monkeypatch.setattr(pub, "VERSION", pub.VERSION + "-changed")
    with pytest.raises(ValueError, match="changed on resume"):
        exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == count


def test_legacy_explicit_absence_normalizes_identically_and_strict_alpha_reject():
    for config in ({}, {"execution_policy": "strict"}, {"execution_policy": "explore"}):
        assert execution_config(config) == execution_config(config | {"new_part_failure_profile": "legacy"})
    for config in (
        {},
        {"execution_policy": "strict"},
        {"execution_policy": "explore", "generation_mode": "alpha_fast", "quality_profile": "alpha"},
    ):
        with pytest.raises(ValueError, match="requires the exploration engine"):
            execution_config(config | {"new_part_failure_profile": pub.PROFILE})


def test_reidentification_uses_remaining_attempt_without_failed_stage_pollution(integration):
    h = integration
    original = h.provider.call

    def call(prompt, images, schema, evidence, check):
        result = original(prompt, images, schema, evidence, check)
        if evidence.parent.name == "instruction-0000-attempt-2-proposal":
            d = json.loads(result["delta_json"])
            d["new_instances"][0].update(part_id="newb", geometry_ref="parts/newb.dat")
            result["delta_json"] = json.dumps(d)
        return result

    h.provider.call = call
    exploration.run_exploration(**h.args)
    assert h.cp["reconstructed_panels"] == 2 and h.cp["model_calls_used"] == 15
    assert {p["part_id"] for p in h.cp["candidate"]["instances"]} == {"newb", "synthetic"}
    assert (h.directory / "geometry/p/a-good.dat").exists()
    assert not (h.directory / "geometry/p/b-short.dat").exists()
    assert (h.directory / "exploration/instructions/0000/attempt-1/part-closures/newa/p/a-good.dat").exists()


@pytest.mark.parametrize(
    "mutation", ["old_hash", "old_notice", "old_missing", "old_shortcut", "old_material"]
)
def test_old_design_or_material_failure_remains_fatal_before_new_rejection(integration, resolver, mutation):
    h = integration
    resolver.bodies["parts/newa.dat"] = dat()
    exploration.run_exploration(**h.args, max_panels=1)
    assert h.cp["reconstructed_panels"] == 1
    before = deepcopy(h.cp["candidate"])
    root = h.directory / "geometry"
    manifest = json.loads((root / "provenance.json").read_text())
    if mutation == "old_hash":
        (root / "parts/newa.dat").write_bytes(b"bad")
    elif mutation == "old_missing":
        (root / "parts/newa.dat").unlink()
    elif mutation == "old_material":
        (root / "LDConfig.ldr").write_bytes(b"bad")
    else:
        body = dat("Shortcut") if mutation == "old_shortcut" else dat(license=False)
        (root / "parts/newa.dat").write_bytes(body)
        manifest["resources"]["parts/newa.dat"].update(sha256=sha(body), bytes=len(body))
        if mutation == "old_shortcut":
            manifest["resources"]["parts/newa.dat"]["classification"] = "Shortcut"
        (root / "provenance.json").write_bytes(canonical(manifest))
    resolver.bodies["parts/synthetic.dat"] = dat("Shortcut")
    h.store.claim("runner-owner", job_id=h.job["id"])
    with pytest.raises(ValueError):
        exploration.run_exploration(**h.args)
    assert h.cp["candidate"] == before
    assert not list((h.directory / "exploration/instructions/0001").glob("*/part-rejection.json"))


def test_new_instance_of_old_design_is_not_reidentified(integration, resolver):
    h = integration
    resolver.bodies["parts/newa.dat"] = dat()
    exploration.run_exploration(**h.args, max_panels=1)
    original = h.provider.call

    def call(*args):
        result = original(*args)
        if result.get("delta_json"):
            d = json.loads(result["delta_json"])
            d["new_instances"][0].update(part_id="newa", geometry_ref="parts/newa.dat")
            result["delta_json"] = json.dumps(d)
        return result

    h.provider.call = call
    resolver.bodies["parts/newa.dat"] = dat("Shortcut")
    # An already accepted root is read from its original immutable cache, never re-fetched.
    requests = len(resolver.requests)
    h.store.claim("runner-owner", job_id=h.job["id"])
    exploration.run_exploration(**h.args)
    assert len(resolver.requests) == requests and h.cp["reconstructed_panels"] == 2
    assert not list(h.directory.glob("exploration/instructions/*/attempt-*/part-rejection.json"))


def test_wrong_source_is_hard_before_asset_rejection(integration, resolver):
    h = integration
    h.provider.modes[0] = "wrong_page"
    with pytest.raises(ValueError, match="source outside"):
        exploration.run_exploration(**h.args)
    assert not resolver.requests and h.cp["model_calls_used"] == 9
    assert not list(h.directory.rglob("part-rejection.json"))


@pytest.mark.parametrize("target", ["rejection", "commitment", "journal", "raw"])
def test_completed_exploration_resume_rejects_evidence_or_commitment_tampering(integration, target):
    h = integration
    exploration.run_exploration(**h.args)
    count = len(h.provider.calls)
    if target == "rejection":
        next(h.directory.rglob("part-rejection.json")).write_text("{}")
    elif target == "commitment":
        h.cp["geometry_publications"] = {}
    elif target == "journal":
        next(h.directory.rglob("publication.json")).write_text("{}")
    else:
        (h.directory / "exploration/instructions/0001/attempt-1/raw-scene.json").write_text("{}")
    h.store.claim("runner-owner", job_id=h.job["id"])
    with pytest.raises(ValueError):
        exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == count


def test_inherited_model_budget_is_not_reset(integration):
    h = integration
    h.cp.update(model_calls_used=5, inherited_model_calls_used=5, local_model_calls_used=0)
    h.job["config"]["max_model_calls"] = 15
    exploration.run_exploration(**h.args)
    assert h.cp["model_calls_used"] == 15 and h.cp["local_model_calls_used"] == 10
    assert h.cp["inherited_model_calls_used"] == 5 and len(h.provider.calls) == 10
    assert h.cp["processed_panels"] == 1 and h.cp["instruction_results"][0]["outcome"] == "unresolved"


def test_empty_private_cache_bootstrap_is_checkpointed(integration):
    h = integration
    root = h.directory / "geometry"
    (root / "provenance.json").unlink()
    (root / "LDConfig.ldr").unlink()
    exploration.run_exploration(**h.args)
    material = [v for k, v in h.cp["geometry_publications"].items() if k.endswith("/materials")]
    assert len(material) == 1 and material[0]["status"] == "committed"
    assert (root / "LDConfig.ldr").exists()


@pytest.mark.parametrize("status", [401, 403, 429, 500, 302])
def test_http_status_failures_are_never_typed_rejections(publication, resolver, status):
    e = publication
    resolver.statuses["p/b-short.dat"] = status
    before = tree(e.private)
    with pytest.raises(httpx.HTTPStatusError):
        resolver.module.stage_individual(
            "newa", e.trial / "bad", [Cache(e.private, Fence()), Cache(e.shared, Fence())]
        )
    assert tree(e.private) == before
    assert resolver.requests.count("p/b-short.dat") == (3 if status == 429 else 1)


def test_unknown_transport_and_worker_stop_propagate_unchanged(publication, resolver):
    from guide2build.engine.runner import WorkerStopped

    e = publication
    error = WorkerStopped("offline pause")
    with pytest.raises(WorkerStopped) as found:
        resolver.module.stage_individual(
            "newa",
            e.trial / "bad",
            [Cache(e.private, Fence()), Cache(e.shared, Fence())],
            lambda: (_ for _ in ()).throw(error),
        )
    assert found.value is error and not resolver.requests


@pytest.mark.parametrize("kind", ["cycle", "depth", "files", "compressed", "missing_dependency"])
def test_resource_dependency_failures_are_hard(publication, resolver, kind):
    e = publication
    if kind == "cycle":
        resolver.bodies["parts/newa.dat"] = dat(refs=("s/loop.dat",))
        resolver.bodies["parts/s/loop.dat"] = dat("Subpart", refs=("s/loop.dat",))
    elif kind == "depth":
        resolver.bodies["parts/newa.dat"] = dat(refs=("a0.dat",))
        for i in range(26):
            resolver.bodies[f"p/a{i}.dat"] = dat("Primitive", refs=(f"a{i + 1}.dat",) if i < 25 else ())
    elif kind == "files":
        resolver.bodies["parts/newa.dat"] = dat(refs=tuple(f"a{i}.dat" for i in range(512)))
        for i in range(512):
            resolver.bodies[f"p/a{i}.dat"] = dat("Primitive")
    elif kind == "compressed":
        resolver.headers["parts/newa.dat"] = {"content-encoding": "gzip"}
    else:
        resolver.bodies["parts/newa.dat"] = dat(refs=("absent.dat",))
    before = tree(e.private)
    with pytest.raises((ValueError, httpx.HTTPStatusError)):
        resolver.module.stage_individual(
            "newa", e.trial / "bad", [Cache(e.private, Fence()), Cache(e.shared, Fence())]
        )
    assert tree(e.private) == before


@pytest.mark.parametrize("mutation", ["same_length_hash", "file_symlink", "ancestor_symlink", "provenance"])
def test_cached_input_mutation_during_rejection_wins(publication, resolver, mutation):
    e = publication
    seed(e.shared, {"p/a-good.dat": dat("Primitive")})
    original = e.shared / "p/a-good.dat"
    before = tree(e.private)

    def mutate():
        if mutation == "same_length_hash":
            original.write_bytes(original.read_bytes().replace(b"Primitive", b"primitiVe"))
        elif mutation == "file_symlink":
            held = e.shared / "held.dat"
            original.rename(held)
            original.symlink_to(held)
        elif mutation == "ancestor_symlink":
            (e.shared / "p").rename(e.shared / "held")
            (e.shared / "p").symlink_to(e.shared / "held", target_is_directory=True)
        else:
            (e.shared / "provenance.json").write_text("{}")

    resolver.hooks["p/b-short.dat"] = mutate
    with pytest.raises(ValueError):
        resolver.module.stage_individual(
            "newa", e.trial / "bad", [Cache(e.private, Fence()), Cache(e.shared, Fence())]
        )
    assert tree(e.private) == before


def test_new_profile_does_not_change_legacy_resolver_error_semantics(publication, resolver):
    e = publication
    with pytest.raises(ValueError, match="Unapproved LDraw classification"):
        resolver.module.fetch_parts(["newa"], e.trial / "legacy")
    assert (e.trial / "legacy/p/a-good.dat").exists()  # Historical behavior remains confined to legacy.
    assert not (e.trial / "legacy/provenance.json").exists()


def test_actual_exploration_crash_after_commit_pin_replays_without_model_call(integration, monkeypatch):
    class Crash(BaseException):
        pass

    h = integration
    original = pub.Publications.pin
    once = []

    def pin(self, *args):
        original(self, *args)
        if not once:
            once.append(True)
            raise Crash()

    monkeypatch.setattr(pub.Publications, "pin", pin)
    with pytest.raises(Crash):
        exploration.run_exploration(**h.args)
    assert h.cp["model_calls_used"] == 11
    first = [c for c in h.provider.calls if c["key"] == "instruction-0001-attempt-1-proposal"]
    assert len(first) == 1
    restored = h.store.get(h.job["id"])["checkpoint"]
    h.cp.clear()
    h.cp.update(restored)
    exploration.run_exploration(**h.args)
    assert h.cp["model_calls_used"] == 14 and h.cp["reconstructed_panels"] == 1
    assert len([c for c in h.provider.calls if c["key"] == "instruction-0001-attempt-1-proposal"]) == 1


def test_stage_union_budget_is_independent_of_per_root_budget(publication, resolver):
    from guide2build.reconstruction.individual_closure import StageBudget

    e = publication
    budget = StageBudget(e.trial / "part-closures")
    budget.bytes = 256_000_000
    before = tree(e.private)
    with pytest.raises(ValueError, match="stage budget"):
        resolver.module.stage_individual(
            "newb",
            e.trial / "newb",
            [Cache(e.private, Fence()), Cache(e.shared, Fence())],
            stage_budget=budget,
        )
    assert tree(e.private) == before and not list((e.trial / "newb").rglob("*.dat"))


def test_fatal_later_new_design_does_not_become_soft_sibling_rejection(integration, resolver):
    h = integration
    original = h.provider.call

    def call(*args):
        result = original(*args)
        if result.get("delta_json"):
            d = json.loads(result["delta_json"])
            part = deepcopy(d["new_instances"][0])
            part.update(instance_id="bad-sibling", part_id="zzbad", geometry_ref="parts/zzbad.dat")
            d["new_instances"].append(part)
            step = d["new_steps"][0]
            for key in ("introduced_instance_ids", "visible_instance_ids", "active_instance_ids"):
                step[key].append("bad-sibling")
            step["poses"]["bad-sibling"] = {"position_ldu": [40, 0, 0], "quaternion_xyzw": [0, 0, 0, 1]}
            result["delta_json"] = json.dumps(d)
        return result

    h.provider.call = call
    resolver.bodies["parts/zzbad.dat"] = dat("Shortcut", license=False)
    with pytest.raises(ValueError, match="license"):
        exploration.run_exploration(**h.args)
    assert h.cp["model_calls_used"] == 9 and h.cp.get("processed_panels", 0) == 0
    assert not list(h.directory.rglob("part-rejection.json"))


def test_prior_receipt_and_bytes_mutation_between_root_transactions_is_fatal(
    integration, resolver, monkeypatch
):
    h = integration
    resolver.bodies["parts/newa.dat"] = dat()
    root = h.directory / "geometry"
    seed(root, {"parts/unused.dat": dat()})
    original = pub.Publications.complete

    def complete(self, *args):
        original(self, *args)
        body = dat().replace(b"synthetic", b"Synthetic")
        (root / "parts/unused.dat").write_bytes(body)
        doc = json.loads((root / "provenance.json").read_text())
        doc["resources"]["parts/unused.dat"].update(sha256=sha(body), bytes=len(body))
        (root / "provenance.json").write_bytes(canonical(doc))

    monkeypatch.setattr(pub.Publications, "complete", complete)
    with pytest.raises(ValueError, match="Cached input changed|Protected prior"):
        exploration.run_exploration(**h.args)
    assert not h.cp.get("candidate")


def test_rejection_receipt_retains_read_through_input_and_permitted_sibling_bindings(integration):
    h = integration
    exploration.run_exploration(**h.args, max_panels=1)
    receipt = json.loads(next(h.directory.rglob("part-rejection.json")).read_text())
    context = receipt["closure_contexts"][0]
    assert context["root_part_id"] == "newa"
    assert len(context["input_cache_provenance"]) == 2
    assert all(x["provenance_sha256"] for x in context["input_cache_provenance"])
    assert context["checked_permitted_resources"]["p/a-good.dat"] == {
        "url": pub.BASE + "p/a-good.dat",
        "sha256": sha(dat("Primitive")),
    }
    assert "p/b-short.dat" not in context["checked_permitted_resources"]
    assert receipt["resources"][0]["license_notices"]
    assert len(canonical(receipt)) <= 65_536


@pytest.mark.parametrize("bad", [None, "unknown", 1, True])
def test_profile_values_are_explicit_and_unknown_values_hard(bad):
    with pytest.raises(ValueError, match="Unknown new-part failure profile"):
        execution_config({"execution_policy": "explore", "new_part_failure_profile": bad})


def test_cli_only_enrolls_explicit_explore_profile_without_mutating_other_rows(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, str(STAGED / "tools"))
    spec = importlib.util.spec_from_file_location("staged_engine_cli", STAGED / "tools/engine.py")
    cli = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(cli)
    finally:
        sys.path.pop(0)
    args = ["engine.py", "--data-dir", str(tmp_path), "enqueue", "--set", "30669", "--guide", "alt-02"]
    monkeypatch.setattr(sys, "argv", args + ["--new-part-failure-profile", pub.PROFILE])
    with pytest.raises(SystemExit) as raised:
        cli.main()
    assert raised.value.code == 2
    assert not EngineStore(tmp_path).list()
    monkeypatch.setattr(
        sys, "argv", args + ["--execution-policy", "explore", "--new-part-failure-profile", pub.PROFILE]
    )
    cli.main()
    jobs = EngineStore(tmp_path).list()
    assert len(jobs) == 1 and jobs[0]["config"]["new_part_failure_profile"] == pub.PROFILE
    assert jobs[0]["state"] == "queued" and jobs[0]["checkpoint"] == {}
    before = deepcopy(jobs[0])
    monkeypatch.setattr(sys, "argv", args + ["--execution-policy", "explore", "--revision", "legacy"])
    cli.main()
    jobs = EngineStore(tmp_path).list()
    assert len(jobs) == 2 and next(j for j in jobs if j["id"] == before["id"]) == before
    assert "new_part_failure_profile" not in next(j for j in jobs if j["id"] != before["id"])["config"]
    capsys.readouterr()
