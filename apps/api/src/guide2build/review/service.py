"""Immutable scenes and append-only correction audit, with transactional stale-base checks."""
import hashlib
import json
import uuid
from ..core.models import SceneManifest
from ..jobs.store import Conflict, Store, now
from .models import CorrectionRequest, ReviewRequest, ReviewItem


class ReviewService:
    def __init__(self, store: Store):
        self.store = store

    def import_scene(self, scene: SceneManifest, items: list[dict] | None = None):
        validated = []
        for value in items or []:
            item = ReviewItem.model_validate(value)
            if (item.source.source_sha256 != scene.source_sha256 or
                    not set(item.instance_ids) <= {i.instance_id for i in scene.instances} or
                    not set(item.step_ids) <= {s.step_id for s in scene.steps}):
                raise ValueError("Review finding does not match scene evidence")
            validated.append(item.model_dump(mode="json"))
        with self.store.connect(write=True) as db:
            row = db.execute("SELECT scene,items FROM revisions WHERE revision=?", (scene.revision,)).fetchone()
            if row:
                if SceneManifest.model_validate_json(row[0]) != scene:
                    raise Conflict("An immutable revision already exists with different contents")
                # Findings may be appended; never silently erase or resolve earlier uncertainty.
                merged = {i["item_id"]: i for i in json.loads(row[1])}
                for item in validated:
                    merged.setdefault(item["item_id"], item)
                db.execute("UPDATE revisions SET items=? WHERE revision=?",
                           (json.dumps(list(merged.values())), scene.revision))
                return
            self._insert(db, scene, validated + self.default_items(scene))

    def _insert(self, db, scene, items):
        db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,?)",
                   (scene.revision, scene.set_number, scene.guide_id, scene.model_dump_json(),
                    json.dumps(items), now()))
        reviewed = scene.revision if scene.status in {"agent_reviewed", "human_reviewed"} else None
        db.execute("INSERT INTO guide_heads VALUES(?,?,?,?) ON CONFLICT(set_number,guide_id) DO UPDATE SET "
                   "latest_revision=excluded.latest_revision,reviewed_revision="
                   "COALESCE(excluded.reviewed_revision,guide_heads.reviewed_revision)",
                   (scene.set_number, scene.guide_id, scene.revision, reviewed))

    @staticmethod
    def default_items(scene):
        items = []
        for instance in scene.instances:
            if instance.mapping_status == "candidate":
                items.append({"item_id": "mapping-" + instance.instance_id, "kind": "part_mapping",
                              "message": "Candidate part mapping requires source comparison.",
                              "instance_ids": [instance.instance_id], "step_ids": [],
                              "source": instance.source.model_dump(), "status": "open"})
        if scene.status in {"candidate", "needs_review"}:
            items.append({"item_id": "assembly-review", "kind": "assembly_review",
                          "message": "Assisted assembly needs source-aligned review; physical build not verified.",
                          "instance_ids": [], "step_ids": [s.step_id for s in scene.steps],
                          "source": scene.steps[0].source.model_dump(), "status": "open"})
        return items

    def get(self, revision):
        with self.store.connect() as db:
            row = db.execute("SELECT scene FROM revisions WHERE revision=?", (revision,)).fetchone()
        if not row:
            raise KeyError(revision)
        return SceneManifest.model_validate_json(row[0])

    def items(self, revision):
        with self.store.connect() as db:
            row = db.execute("SELECT items FROM revisions WHERE revision=?", (revision,)).fetchone()
        if not row:
            raise KeyError(revision)
        return json.loads(row[0])

    def heads(self, set_number, guide_id):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM guide_heads WHERE set_number=? AND guide_id=?",
                             (set_number, guide_id)).fetchone()
        return dict(row) if row else None

    def apply(self, revision: str, request: CorrectionRequest | ReviewRequest, key: str):
        # A public local JSON assertion cannot establish that a human personally reviewed this build.
        if request.actor_type != "agent":
            raise ValueError("Human review identity is not verified by this local API; use agent provenance")
        if revision != request.expected_revision:
            raise Conflict("Expected revision does not match the addressed revision")
        payload = request.model_dump(mode="json")
        request_hash = hashlib.sha256(json.dumps({"revision": revision, **payload}, sort_keys=True).encode()).hexdigest()
        with self.store.connect(write=True) as db:
            duplicate = db.execute("SELECT * FROM review_actions WHERE operation_key=?", (key,)).fetchone()
            if duplicate:
                if duplicate["request_hash"] != request_hash:
                    raise Conflict("Idempotency key already used for a different correction")
                row = db.execute("SELECT scene FROM revisions WHERE revision=?", (duplicate["result_revision"],)).fetchone()
                return SceneManifest.model_validate_json(row[0])
            row = db.execute("SELECT * FROM revisions WHERE revision=?", (revision,)).fetchone()
            if not row:
                raise KeyError(revision)
            original = SceneManifest.model_validate_json(row["scene"])
            head = db.execute("SELECT latest_revision FROM guide_heads WHERE set_number=? AND guide_id=?",
                              (original.set_number, original.guide_id)).fetchone()
            if not head or head[0] != revision:
                raise Conflict("Scene changed; load the latest revision before editing")
            candidate = original.model_dump(mode="json")
            candidate["revision"] = "r-" + uuid.uuid4().hex
            candidate["status"] = "needs_review"
            candidate["geometry_check"] = "not_run"
            candidate["connector_check"] = "not_run"
            candidate["physical_build_check"] = "not_run"
            audit = {**payload, "before": None, "origin": "local_api_declared_" + request.actor_type}
            if isinstance(request, CorrectionRequest):
                if request.source.source_sha256 != original.source_sha256:
                    raise ValueError("Correction evidence belongs to a different source")
                self._correction(candidate, request, audit)
            else:
                for relative in request.evidence_paths:
                    evidence_root = (self.store.data_dir / "evidence").resolve()
                    target = (self.store.data_dir / relative).resolve()
                    if not target.is_relative_to(evidence_root) or not target.is_file():
                        raise ValueError("Review evidence must identify an existing local evidence file")
                candidate["reviews"].append({"actor_type": "agent", "actor_id": request.actor_id,
                    "reviewed_revision": candidate["revision"], "evidence_paths": request.evidence_paths,
                    "decision": request.decision, "recorded_at": now()})
                if request.decision == "accepted":
                    candidate["status"] = "agent_reviewed"
            scene = SceneManifest.model_validate(candidate)
            items = list({i["item_id"]: i for i in self.default_items(scene) + json.loads(row["items"])}.values())
            self._insert(db, scene, items)
            db.execute("INSERT INTO review_actions VALUES(?,?,?,?,?,?)", (key, request_hash, revision,
                       scene.revision, json.dumps(audit), now()))
            return scene

    def _correction(self, candidate, request, audit):
        command = request.command
        if command.type == "mapping":
            instance = next((i for i in candidate["instances"] if i["instance_id"] == command.instance_id), None)
            if instance is None:
                raise ValueError("Unknown physical instance")
            # Validate path lexically through the scene model before touching local geometry.
            proposed = {**instance, "part_id": command.part_id, "color_code": command.color_code,
                        "geometry_ref": command.geometry_ref, "source": request.source.model_dump(mode="json"),
                        "mapping_status": "candidate", "origin": ("human_correction" if request.actor_type == "human"
                                                               else "pdf_assisted_authoring")}
            from ..core.models import PartInstance
            PartInstance.model_validate(proposed)
            root = (self.store.data_dir / "public/ldraw").resolve()
            path = (root / command.geometry_ref).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError("Correction geometry is not in the local curated parts library")
            audit["before"] = dict(instance)
            instance.update(proposed)
        else:
            step = next((s for s in candidate["steps"] if s["step_id"] == command.step_id), None)
            if step is None:
                raise ValueError("Unknown instruction step")
            if command.type == "group":
                audit["before"] = step["assembly_group_id"]
                step["assembly_group_id"] = command.assembly_group_id
            else:
                if command.instance_id not in step["poses"]:
                    raise ValueError("Instance is not visible in the selected instruction")
                audit["before"] = step["poses"][command.instance_id]
                step["poses"][command.instance_id] = command.pose.model_dump(mode="json")
        # The full structural model is checked below; geometry/connector descendants remain explicitly unchecked.
