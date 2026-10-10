"""Offline geometry inspection using the actual retained LDraw triangle geometry.
These orthographic previews support agent review, never certify fit or render parity.
"""

from __future__ import annotations
import json
import math
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw
from .reference import build_reference


def mv(m, v):
    return [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]


def evidence_renders(root: Path):
    assets = root / "var/public/ldraw"
    metadata = json.loads((assets / "provenance.json").read_text())
    fmap = metadata["file_map"]

    @lru_cache(None)
    def mesh(path):
        result = []
        for line in (assets / path).read_text().splitlines():
            f = line.split()
            if not f:
                continue
            if f[0] == "1":
                v = list(map(float, f[2:14]))
                t = v[:3]
                r = [v[3:6], v[6:9], v[9:12]]
                child = fmap[f[14].lower().replace("\\", "/")]
                for face in mesh(child):
                    result.append([[a + b for a, b in zip(mv(r, p), t)] for p in face])
            elif f[0] in ("3", "4"):
                v = list(map(float, f[2:]))
                result.append([v[i : i + 3] for i in range(0, len(v), 3)])
        return result

    scene, _, _ = build_reference()
    out = root / "var/evidence/reconstruction" / scene.revision
    out.mkdir(parents=True, exist_ok=True)
    colors = {
        "15": (236, 236, 226),
        "4": (185, 20, 23),
        "14": (239, 199, 15),
        "47": (150, 204, 202),
        "71": (150, 151, 154),
    }
    camera = [-0.606, 0.707, -0.364]
    right = [-0.514, 0, 0.857]
    up = [0.606, 0.707, 0.364]

    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    inst = {p.instance_id: p for p in scene.instances}
    records = []
    for step in scene.steps:
        faces = []
        for ident, p in step.poses.items():
            q = p.quaternion_xyzw
            a = 2 * math.atan2(q[1], q[3])
            c, s = math.cos(a), math.sin(a)
            r = [[c, 0, s], [0, 1, 0], [-s, 0, c]]
            for face in mesh(inst[ident].geometry_ref):
                pts = [[v[0], -v[1], -v[2]] for v in face]
                pts = [[a + b for a, b in zip(mv(r, v), p.position_ldu)] for v in pts]
                faces.append(
                    (
                        dot(camera, [sum(v[i] for v in pts) / len(pts) for i in range(3)]),
                        pts,
                        colors[inst[ident].color_code],
                    )
                )
        projected = [(dot(right, v), dot(up, v)) for _, ps, _ in faces for v in ps]
        minx, miny = min(p[0] for p in projected), min(p[1] for p in projected)
        maxx, maxy = max(p[0] for p in projected), max(p[1] for p in projected)
        scale = min(740 / (maxx - minx), 500 / (maxy - miny))
        cx = (minx + maxx) / 2
        cy = (miny + maxy) / 2
        image = Image.new("RGB", (820, 620), (229, 239, 245))
        d = ImageDraw.Draw(image)
        for _, pts, color in sorted(faces, key=lambda x: x[0]):
            a, b, c = pts[:3]
            u = [b[i] - a[i] for i in range(3)]
            v = [c[i] - a[i] for i in range(3)]
            n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
            length = math.sqrt(dot(n, n))
            shade = 0.72 + 0.28 * (abs(n[1]) / length if length else 0.5)
            xy = [(410 + (dot(right, p) - cx) * scale, 315 - (dot(up, p) - cy) * scale) for p in pts]
            d.polygon(xy, fill=tuple(int(c * shade) for c in color))
        d.text(
            (20, 15),
            f"{step.step_id} | PDF-assisted candidate | geometry/connector review pending",
            fill=(20, 30, 40),
        )
        dest = out / f"{step.step_id}-candidate.png"
        image.save(dest)
        records.append(
            {
                "step_id": step.step_id,
                "path": str(dest.relative_to(root)),
                "render_kind": "orthographic inspection, actual LDraw faces; painter occlusion artifacts; use browser for authoritative appearance",
                "revision": scene.revision,
                "source": step.source.model_dump(),
            }
        )
    (out / "render-index.json").write_text(json.dumps(records, indent=2) + "\n")
    return records
