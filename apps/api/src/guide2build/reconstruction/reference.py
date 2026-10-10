"""PDF-assisted candidate authored solely from the selected official booklet.

Coordinates are source-constrained proposals, not automatically inferred or accepted
geometry. Reference data must never be consumed by a fresh provider evaluation.
"""

from __future__ import annotations
import hashlib
import json
import math
import re
from pathlib import Path
from guide2build.core.models import SceneManifest

SOURCE_HASH = "6cb3e669fef3662dfd498cba0e631f1d9ec082c2bf8c0fb0a0febe303680a6b6"
REVISION = "pdf-assisted-30669-alt02-v3"


def panel(n: int, bbox=None):
    # Page 1 has cover thumbnail above step 1. Crops retain quantities and arrows.
    box = (
        [0.035, 0.17, 0.64, 0.48]
        if n == 1
        else [0.035, 0.54, 0.64, 0.95]
        if n == 2
        else [0.035, 0.0, 0.65, 0.49]
        if n % 2
        else [0.035, 0.50, 0.65, 0.97]
    )
    return {"page_index": (n + 1) // 2, "bbox": bbox or box, "source_sha256": SOURCE_HASH}


def pose(x, y, z, turn=0):
    a = math.radians(turn) / 2
    return {"position_ldu": [x, y, z], "quaternion_xyzw": [0, math.sin(a), 0, math.cos(a)]}


def build_reference() -> tuple[SceneManifest, dict, dict]:
    instances, steps, poses, observations = [], [], {}, []

    def add(n, ident, part, color, xyz, turn=0, reason=""):
        instances.append(
            {
                "instance_id": ident,
                "part_id": part,
                "color_code": str(color),
                "geometry_ref": f"parts/{part}.dat",
                "source": panel(n),
                "origin": "pdf_assisted_authoring",
                "mapping_status": "candidate",
            }
        )
        poses[ident] = pose(*xyz, turn)
        observations.append(
            {
                "instance_id": ident,
                "part_candidates": [part],
                "selected_part": part,
                "source": panel(n),
                "origin": "pdf_assisted_authoring",
                "pose_constraints": reason,
                "confidence": "candidate_requires_review",
            }
        )

    def snap(n, new, instruction, suffix="", action="add_parts", group=None, active=None):
        steps.append(
            {
                "step_id": f"main-{n:02d}" + suffix,
                "main_step_number": n,
                "substep_label": suffix.strip("-") or None,
                "instruction": instruction,
                "source": panel(n),
                "introduced_instance_ids": new,
                "active_instance_ids": active if active is not None else new,
                "visible_instance_ids": list(poses),
                "poses": json.loads(json.dumps(poses)),
                "action": action,
                "assembly_group_id": group,
            }
        )

    add(
        1,
        "base",
        "3022",
        15,
        (0, 0, -10),
        reason="Two-by-two plate; uncovered front stud row at z=-20; rear row supports two curved-part front undersides.",
    )
    for side, x in [("left", -10), ("right", 10)]:
        add(
            1,
            f"keel-{side}",
            "13547",
            15,
            (x, 16, 0),
            reason="Parallel curved inverted parts, frontmost solid studs at z=0; lower front underside is 16 LDU below part origin. Hollow studs rise one plate above solid studs.",
        )
    snap(
        1, list(poses), "Join the two white curved inverted pieces to the rear row of the white 2 × 2 plate."
    )
    for side, x, rot in [("left", -40, 180), ("right", 40, 90)]:
        add(
            2,
            f"wing-{side}",
            "35044",
            15,
            (x, 8, -50),
            rot,
            reason="Quarter-circle cutouts face outwards toward the nose. Centre seam is x=0. Inner rear studs at x=±10,z=-20 mate to the exposed base-plate row; wing tops align with low keel stud bases.",
        )
    snap(
        2,
        ["wing-left", "wing-right"],
        "Add the two white curved corner plates to the exposed front studs, meeting at the centre seam.",
    )
    # The callout groups add one stud of wing span. Preserve one physical ID on attachment.
    for n, side, s in [(3, "left", 1), (4, "right", -1)]:
        ids = [f"{side}-wing-base", f"{side}-wing-strip", f"{side}-wing-tip"]
        add(
            n,
            ids[0],
            "3020",
            15,
            (s * 150, 32, -10),
            reason="Detached 2×4 callout base; presentation offset is removed by a single rigid attachment translation.",
        )
        snap(
            n,
            [ids[0]],
            "Start the white 2 × 4 wing subassembly.",
            "-callout-1",
            "build_subassembly",
            side + "-wing",
        )
        add(
            n, ids[1], "3710", 15, (s * 150, 40, 0), reason="1×4 strip occupies the rear row of the 2×4 base."
        )
        add(
            n,
            ids[2],
            "25269",
            15,
            (s * 180, 40, -20),
            90 if s == -1 else 180,
            reason="Quarter-round tile covers the outboard stud of the other row; rounded corner faces the outside of the wing.",
        )
        snap(
            n,
            ids[1:],
            "Add the 1 × 4 strip and the small rounded corner tile.",
            "-callout-2",
            "build_subassembly",
            side + "-wing",
        )
        for ident in ids:
            p = poses[ident]["position_ldu"]
            p[0] -= s * 90
            p[1] -= 32
        snap(
            n,
            [],
            "Attach the wing subassembly beneath the curved wing edge. Check the source while reviewing the hidden contacts.",
            "-attach",
            "attach_subassembly",
            side + "-wing",
            ids,
        )
    for side, x, part in [("left", -20, "78443"), ("right", 20, "78444")]:
        add(
            5,
            f"belly-{side}",
            part,
            4,
            (x, 0, -90),
            180,
            reason="Narrow ends point noseward; centre straight rows x=±10. Wide ends z=-40 support the curved wings from below.",
        )
    snap(5, ["belly-left", "belly-right"], "Add the two red tapered plates beneath the front of the wings.")
    add(
        6,
        "nose-square",
        "3022",
        15,
        (0, 8, -110),
        reason="2×2 white plate fills forward studs z=-120,-100 at wing-top height.",
    )
    add(6, "nose-end", "3023", 15, (0, 8, -140), reason="1×2 white plate fills foremost red stud row.")
    snap(6, ["nose-square", "nose-end"], "Add the white 2 × 2 and 1 × 2 plates at the nose.")
    add(
        7,
        "spine-yellow",
        "3020",
        14,
        (0, 16, -10),
        90,
        reason="2×4 yellow plate spans z=-40,-20,0,20 along the fuselage; underside mates to wing and low keel stud bases.",
    )
    for side, x in [("left", -10), ("right", 10)]:
        add(
            7,
            f"spine-yellow-{side}",
            "3623",
            14,
            (x, 16, -80),
            90,
            reason="Two parallel 1×3 plates extend yellow layer forward over z=-100,-80,-60.",
        )
    add(
        7,
        "nose-shield",
        "22385",
        4,
        (0, 16, -130),
        180,
        reason="Angled tile extends toward the nose; orientation and the part-local offset need render review.",
    )
    snap(
        7,
        ["spine-yellow", "spine-yellow-left", "spine-yellow-right", "nose-shield"],
        "Add the yellow spine plates and red angled nose tile.",
    )
    add(
        8,
        "spine-red",
        "3020",
        4,
        (0, 24, -50),
        90,
        reason="Long red 2×4 plate covers middle yellow rows z=-80,-60,-40,-20.",
    )
    add(
        8,
        "canopy-base",
        "3023",
        47,
        (0, 24, -100),
        reason="Transparent 1×2 plate spans noseward yellow row. Source alone does not establish clear versus light-blue tint.",
    )
    add(8, "rear-tile", "3068b", 4, (0, 24, 10), reason="Red 2×2 tile covers rear yellow rows z=0,20.")
    for side, x, rot in [("left", -10, 90), ("right", 10, 270)]:
        add(
            8,
            f"rear-rail-{side}",
            "32028",
            71,
            (x, 24, 50),
            rot,
            reason="Two grey 1×2 door-rail plates cover raised hollow-stud rows z=40,60; rails face outwards.",
        )
    snap(
        8,
        ["spine-red", "canopy-base", "rear-tile", "rear-rail-left", "rear-rail-right"],
        "Add the red plate, transparent plate, red tile, and two grey rail plates.",
    )
    for side, x in [("left", -10), ("right", 10)]:
        add(
            9,
            f"long-tile-{side}",
            "6636",
            4,
            (x, 32, -30),
            90,
            reason="Two 1×6 tiles cover z=-80 through20; bases remain on one plate level.",
        )
        add(
            9,
            f"tail-jumper-{side}",
            "15573",
            4,
            (0, 32, 40 if side == "left" else 60),
            0,
            reason="Two jumpers sit on grey rails; transverse plates have centre studs x=0,z=40 and60, as shown by the enlarged step9 source. They form the longitudinal tail mount. Understud variant cannot be identified from this top view.",
        )
    snap(
        9,
        ["long-tile-left", "tail-jumper-left", "long-tile-right", "tail-jumper-right"],
        "Add the long red tiles and two red centre-stud plates.",
    )
    for side, x in [("left", -10), ("right", 10)]:
        add(
            10,
            f"canopy-{side}",
            "11477",
            47,
            (x, 16, -110),
            180,
            reason="Two transparent curved slopes sit side-by-side; their raised underside socket at local canonical y=8 mounts on plate top24, making roof top32 flush with red tiles. Rear socket row at z=-100 and front overhang reaches noseward.",
        )
    snap(10, ["canopy-left", "canopy-right"], "Add the two transparent curved canopy pieces.")
    add(
        11,
        "tail-slope",
        "3040b",
        4,
        (0, 56, 60),
        180,
        reason="Enlarged source step11 shows slope pointing noseward. Two underside socket rows z=40,60 meet the transverse jumper centres; top stud at x=0,z=60.",
    )
    snap(11, ["tail-slope"], "Add the red tail slope with its sloping face pointing toward the nose.")
    add(
        12,
        "tailplane",
        "18980",
        4,
        (10, 64, 50),
        180,
        reason="Rounded 2×6 tailplane spans across the body with curved edge noseward. Half-stud x offset places a normal underside socket at x=0,z=60 over the slope stud; lateral offset sign remains ambiguous in source.",
    )
    snap(12, ["tailplane"], "Add the rounded red tailplane; compare the final candidate with the guide.")
    scene = SceneManifest.model_validate(
        {
            "set_number": "30669",
            "guide_id": "alt-02",
            "revision": REVISION,
            "source_sha256": SOURCE_HASH,
            "status": "needs_review",
            "instances": instances,
            "steps": steps,
            "geometry_check": "not_run",
            "connector_check": "not_run",
            "physical_build_check": "not_run",
            "reviews": [],
        }
    )
    issues = []
    for key, kind, message, ids, ns in [
        (
            "first-four-contacts",
            "occluded_connection",
            "Review hidden curved-keel contact, wing-to-base contacts and callout attachment; lattice alignment is not a narrow-phase geometry or connector proof.",
            [x["instance_id"] for x in instances[:11]],
            [1, 2, 3, 4],
        ),
        (
            "nose-shield-origin",
            "pose_ambiguity",
            "Angled nose tile local origin and orientation need source-render comparison.",
            ["nose-shield"],
            [7],
        ),
        (
            "canopy-color",
            "ambiguous_colour",
            "Source artwork uses a pale blue tint; clear (47), Trans_Very_Light_Blue (39), and Trans_Light_Blue (43) remain candidates. Official cover shows a cyan tint, but exact element colour is not verified.",
            ["canopy-base", "canopy-left", "canopy-right"],
            [8, 10],
        ),
        (
            "canopy-origin",
            "pose_ambiguity",
            "Canopy origin corrected from actual geometry socket offset; independently review the corrected noseward overhang.",
            ["canopy-left", "canopy-right"],
            [10],
        ),
        (
            "jumper-variant",
            "part_variant",
            "15573 is a top-view-compatible candidate; the booklet does not show enough underside detail to exclude 3794 variants.",
            ["tail-jumper-left", "tail-jumper-right"],
            [9],
        ),
        (
            "tail-contact",
            "pose_ambiguity",
            "Tail slope direction corrected against enlarged step11; tailplane half-stud lateral offset sign and hidden mounting remain under review.",
            ["tail-slope", "tailplane"],
            [11, 12],
        ),
    ]:
        issues.append(
            {
                "item_id": key,
                "kind": kind,
                "message": message,
                "instance_ids": ids,
                "step_ids": [s["step_id"] for s in steps if s["main_step_number"] in ns],
                "source": panel(ns[0]),
                "status": "open",
            }
        )
    issues.append({
        "item_id": "canopy-color-43", "kind": "ambiguous_colour",
        "message": "Cover artwork is distinctly cyan: LDraw 43 (Trans Light Blue) is another source-supported "
                   "alternative to 39 (Trans Very Light Blue) and current candidate 47 (Trans Clear). "
                   "Booklet artwork alone does not resolve the exact element tint.",
        "instance_ids": ["canopy-base", "canopy-left", "canopy-right"],
        "step_ids": ["main-08", "main-10"],
        "source": {"page_index": 0, "bbox": [0, 0, 1, 1], "source_sha256": SOURCE_HASH},
        "status": "open",
    })
    report = {
        "artifact_kind": "pdf_assisted_reference_candidate",
        "automatic_conversion": False,
        "source_sha256": SOURCE_HASH,
        "revision": REVISION,
        "main_steps_observed": 12,
        "main_steps_candidate": 12,
        "microsteps": len(steps),
        "physical_instance_count": len(instances),
        "four_step_gate": {
            "status": "needs_review",
            "physical_instances": 11,
            "main_steps": [1, 2, 3, 4],
            "blocks_extension_as_verified": True,
            "note": "Later-step hypotheses are retained independently; first four have not been accepted.",
        },
        "observations": observations,
        "part_decisions_path": "config/reference-part-decisions-30669-alt-02.json",
        "corrections": [],
        "human_review": "not_run",
        "physical_build": "not_run",
    }
    audit = Path(__file__).resolve().parents[5] / "config/reference-corrections-30669-alt-02-v2.json"
    report["corrections"] = json.loads(audit.read_text())["corrections"]
    audit3 = Path(__file__).resolve().parents[5] / "config/reference-corrections-30669-alt-02-v3.json"
    report["corrections"] += json.loads(audit3.read_text())["corrections"]
    report["corrected_instance_count"] = len(report["corrections"])
    return scene, {"items": issues}, report


def materialize(root: Path) -> dict:
    source = root / "var/sources/30669/alt-02/source.pdf"
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_HASH:
        raise ValueError("Official source differs from authored reference evidence")
    scene, issues, report = build_reference()
    assets = root / "var/public/ldraw"
    from .checks import verify_assets, four_step_connector_report

    report["asset_provenance_check"] = verify_assets(assets, [item.geometry_ref for item in scene.instances])
    pins = json.loads((root / "config/parts-30669-alt-02.json").read_text())
    for section in ("resource_sha256", "material_sha256"):
        for relative, digest in pins[section].items():
            if hashlib.sha256((assets / relative).read_bytes()).hexdigest() != digest:
                raise ValueError("Asset differs from reference-pinned geometry or materials")
    report["declared_connector_frame_check"] = four_step_connector_report(scene)
    out = root / "var/reconstructions/30669/alt-02"
    out.mkdir(parents=True, exist_ok=True)
    serialized = scene.model_dump_json(indent=2) + "\n"
    existing = out / "scene.json"
    if existing.exists():
        previous = json.loads(existing.read_text())
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", previous["revision"]):
            raise ValueError("Unsafe previous revision identifier")
        previous_dir = out / "revisions" / previous["revision"]
        previous_dir.mkdir(parents=True, exist_ok=True)
        archived = previous_dir / "scene.json"
        if archived.exists() and json.loads(archived.read_text()) != previous:
            raise ValueError("Archived revision content conflict")
        archived.write_text(existing.read_text())
        previous_items = out / "review-items.json"
        if previous_items.exists() and not (previous_dir / "review-items.json").exists():
            (previous_dir / "review-items.json").write_text(previous_items.read_text())
        if previous["revision"] == scene.revision and previous != json.loads(serialized):
            raise ValueError("A changed authored candidate requires a new revision and correction record")
    revision_dir = out / "revisions" / scene.revision
    revision_dir.mkdir(parents=True, exist_ok=True)
    (revision_dir / "scene.json").write_text(serialized)
    (revision_dir / "review-items.json").write_text(json.dumps(issues, indent=2) + "\n")
    (out / "scene.json").write_text(serialized)
    (out / "review-items.json").write_text(json.dumps(issues, indent=2) + "\n")
    evidence = root / "var/observations"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "30669-alt-02.json").write_text(json.dumps(report, indent=2) + "\n")
    (evidence / "panels.json").write_text(
        json.dumps([{"main_step": n, **panel(n)} for n in range(1, 13)], indent=2) + "\n"
    )
    return report
