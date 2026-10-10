"""Source-bound part observations and local, individual-geometry comparisons.

Scores and thumbnails assist interpretation; they do not establish a part identity,
hidden attachment, accurate material, or independent human review.
"""
from __future__ import annotations

from collections import Counter, deque
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import re
from statistics import median

from PIL import Image, ImageChops, ImageDraw, ImageFilter
from pydantic import Field, model_validator

from ..core.models import SourcePanel, StrictModel
from ..reconstruction.checks import verify_assets
from ..releases.models import canonical

VERSION = "source-part-evidence-v1"
PART_ID = r"^[a-z0-9]{1,40}$"
MASK_POLICY_VERSION = "border-connected-background-v1"
MASK_POLICY = {
    "kind": "border_connected_background", "version": MASK_POLICY_VERSION,
    "human_reviewed": False, "colour_distance": "maximum_absolute_srgb_channel_difference",
    "border_width_pixels": 2, "colour_bin_width": 16, "background_cluster_radius": 12,
    "minimum_border_background_fraction": .8, "maximum_background_tolerance": 12,
    "minimum_background_tolerance": 4, "tolerance_sensitivity_delta": 2,
    "minimum_tolerance_mask_iou": .9, "minimum_foreground_fraction": .002,
    "maximum_foreground_fraction": .85, "minimum_foreground_pixels": 32,
    "minimum_valid_fraction": .2, "minimum_primary_component_fraction": .95,
    "minimum_foreground_component_pixels": 8,
    "connectivity": 4, "maximum_comparison_dimension": 512,
    "scope": "Single visible assembly on a dominant uniform background; explicit annotation exclusions required.",
}


class PartCandidate(StrictModel):
    part_id: str = Field(pattern=PART_ID)
    reason: str = Field(min_length=1, max_length=2000)
    color_codes: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def colors(self):
        if any(not re.fullmatch(r"[0-9]{1,5}", color) for color in self.color_codes):
            raise ValueError("Candidate colours must be real-format LDraw colour identifiers")
        if len(set(self.color_codes)) != len(self.color_codes):
            raise ValueError("Duplicate candidate colour")
        return self


class PartObservation(StrictModel):
    observation_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,120}$")
    source: SourcePanel
    quantity: int = Field(ge=1, le=128, strict=True)
    shape_cues: list[str] = Field(min_length=1, max_length=16)
    colour_description: str = Field(min_length=1, max_length=2000)
    candidates: list[PartCandidate] = Field(min_length=1, max_length=3)
    uncertainties: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def distinct(self):
        ids = [item.part_id for item in self.candidates]
        if len(set(ids)) != len(ids):
            raise ValueError("Part alternatives must be distinct")
        if any(not cue.strip() or len(cue) > 400 for cue in self.shape_cues):
            raise ValueError("Shape cues must be short, nonempty observations")
        if any(len(note) > 2000 for note in self.uncertainties):
            raise ValueError("Part uncertainty exceeds bound")
        return self


def _bytes(root, relative, limit=32_000_000):
    root = Path(root).absolute()
    path = root / relative
    if (root.resolve() != root or Path(relative).is_absolute() or ".." in Path(relative).parts
            or path.resolve() != path or not path.is_file() or path.stat().st_size > limit):
        raise ValueError("Unsafe or oversized perception evidence path")
    return path.read_bytes()


def _document(root):
    return json.loads(_bytes(root, "provenance.json", 10_000_000))


def _verify_part(root, reference, document):
    records = document.get("resources", {})
    if records.get(reference, {}).get("classification") != "Part":
        raise ValueError("Candidate must name an available real individual Part")
    verify_assets(root, [reference])
    pending, seen = [reference], set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        record = records[name]
        if record.get("classification") not in {"Part", "Subpart", "Primitive", "48_Primitive", "8_Primitive"}:
            raise ValueError("Individual geometry dependency is not an allowed part or primitive")
        pending.extend(record.get("dependencies", []))


def _tokens(value):
    words = re.findall(r"[a-z]+|\d+(?:\.\d+)?", value.lower())
    # Shape families are independent of file names and set-specific mappings.
    aliases = {"curved": "curve", "sloped": "slope", "studs": "stud", "plates": "plate",
               "tiles": "tile", "bricks": "brick", "rounded": "round", "inverted": "invert"}
    return {aliases.get(word, word) for word in words if word not in {"with", "and", "the", "a", "x"}}


def source_relevant_catalogue(geometry_root: Path, *, shape_cues=(), part_ids=(), max_parts=24,
                              max_bytes=100_000):
    """Rank the entire local Part index before applying a context budget.

    Explicit IDs and shape cues are source observations, not an accepted assembly.
    A no-cue request returns descriptions for diversity, not lexical raw-geometry truncation.
    """
    if not 1 <= max_parts <= 64 or not 1000 <= max_bytes <= 400_000:
        raise ValueError("Invalid part context budget")
    if len(part_ids) > 64 or len(shape_cues) > 64:
        raise ValueError("Source part hints exceed bound")
    root = Path(geometry_root).absolute()
    if not (root / "provenance.json").is_file():
        return {"parts": [], "retrieval": {"status": "missing_geometry", "candidate_count": 0}}
    document = _document(root)
    wanted = set(part_ids)
    if any(not re.fullmatch(PART_ID, value) for value in wanted):
        raise ValueError("Invalid explicit source part identity")
    query = _tokens(" ".join(shape_cues))
    ranked = []
    for reference, record in document.get("resources", {}).items():
        if record.get("classification") != "Part" or not re.fullmatch(r"parts/[a-z0-9]+\.dat", reference):
            continue
        identity = Path(reference).stem
        description = str(record.get("description", ""))[:1000]
        terms = _tokens(description)
        matches = sorted(query & terms)
        # Exact dimensions count more than a broad family word. Explicit IDs remain first.
        score = (1000 if identity in wanted else 0) + sum(3 if word[0].isdigit() else 1 for word in matches)
        ranked.append((score, len(matches), reference, description, matches))
    ranked.sort(key=lambda row: (-row[0], -row[1], row[2]))
    selected, used, skipped = [], 0, []
    for score, _, reference, description, matches in ranked:
        if len(selected) >= max_parts:
            break
        # With source hints, do not fill the context with unrelated lexical neighbours.
        if (query or wanted) and score == 0:
            continue
        _verify_part(root, reference, document)
        data = _bytes(root, reference, 1_000_000)
        record = document["resources"][reference]
        entry = {"part_id": Path(reference).stem, "geometry_ref": reference,
                 "description": description, "sha256": hashlib.sha256(data).hexdigest(),
                 "retrieval_score": score, "matched_shape_terms": matches,
                 "raw_ldraw_part_geometry": data.decode("utf-8-sig")[:6000],
                 "geometry_truncated": len(data.decode("utf-8-sig")) > 6000,
                 "dependency_count": len(record.get("dependencies", []))}
        size = len(canonical(entry))
        if used + size > max_bytes:
            # Keep the ranked identity/description even if a long mesh does not fit.
            entry.pop("raw_ldraw_part_geometry")
            entry["geometry_truncated"] = True
            size = len(canonical(entry))
        if used + size > max_bytes:
            continue
        selected.append(entry)
        used += size
    return {"parts": selected, "retrieval": {"version": VERSION, "status": "ranked",
            "candidate_count": len(ranked), "selected_count": len(selected), "bytes": used,
            "shape_cues": list(shape_cues), "explicit_part_ids": sorted(wanted), "skipped": skipped,
            "limitation": "Description/shape ranking is a shortlist, not a source-verified identity."}}


def _immutable(path, data):
    path = Path(path).absolute()
    if path.parent.resolve() != path.parent or path.is_symlink():
        raise ValueError("Unsafe perception output path")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Perception evidence is immutable; use a new trial directory")
    else:
        with path.open("xb") as stream:
            stream.write(data)
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def _png(image):
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _image(path):
    path = Path(path).absolute()
    data = _bytes(path.parent, path.name)
    image = Image.open(BytesIO(data))
    if image.format != "PNG" or image.width * image.height > 16_777_216:
        raise ValueError("Perception requires a bounded PNG")
    image.load()
    return image, hashlib.sha256(data).hexdigest()


def crop_callout(observation: PartObservation | dict, pages_dir: Path, output_dir: Path):
    observation = PartObservation.model_validate(observation)
    # This prevents crops being silently sourced from a different cached booklet.
    if Path(pages_dir).name != observation.source.source_sha256:
        raise ValueError("Callout page directory does not match its source PDF hash")
    source = Path(pages_dir) / f"page-{observation.source.page_index:03d}.png"
    page, page_hash = _image(source)
    x0, y0, x1, y1 = observation.source.bbox
    rectangle = (math.floor(x0 * page.width), math.floor(y0 * page.height),
                 math.ceil(x1 * page.width), math.ceil(y1 * page.height))
    crop = page.crop(rectangle).convert("RGB")
    receipt = _immutable(Path(output_dir) / f"{observation.observation_id}-callout.png", _png(crop))
    return {**receipt, "source_sha256": observation.source.source_sha256,
            "page_index": observation.source.page_index, "source_page_sha256": page_hash,
            "bbox": list(observation.source.bbox), "pixel_bbox": list(rectangle),
            "page_size": list(page.size), "crop_size": list(crop.size)}


def _part_triangles(root, part_id, *, max_faces=80_000):
    """Flatten only the verified individual dependency closure, preserving its origin."""
    reference = f"parts/{part_id}.dat"
    document = _document(root)
    if document.get("resources", {}).get(reference, {}).get("classification") != "Part":
        raise ValueError("Candidate must name an available real individual Part")
    _verify_part(root, reference, document)
    faces, hashes, visits = [], {}, 0

    def walk(path, matrix, offset, ancestry):
        nonlocal visits
        visits += 1
        if path in ancestry or len(ancestry) > 32 or visits > 4096:
            raise ValueError("Individual thumbnail dependency expansion exceeds bound")
        data = _bytes(root, path, 1_000_000)
        hashes[path] = hashlib.sha256(data).hexdigest()

        def point(local):
            p = [offset[i] + sum(matrix[i][j] * local[j] for j in range(3)) for i in range(3)]
            if any(not math.isfinite(value) or abs(value) > 1_000_000 for value in p):
                raise ValueError("Individual geometry coordinate exceeds bound")
            return p

        for line in data.decode("utf-8-sig").splitlines():
            fields = line.split()
            if not fields or fields[0] not in {"1", "3", "4"}:
                continue
            if fields[0] == "1":
                if len(fields) != 15:
                    raise ValueError("Malformed individual geometry transform")
                name = fields[14].lower().replace("\\", "/")
                child = document.get("file_map", {}).get(name)
                if child not in document["resources"][path].get("dependencies", []):
                    raise ValueError("Individual thumbnail dependency lacks provenance")
                values = [float(value) for value in fields[2:14]]
                if not all(math.isfinite(value) for value in values):
                    raise ValueError("Nonfinite individual geometry transform")
                local = [values[3:6], values[6:9], values[9:12]]
                composed = [[sum(matrix[i][k]*local[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
                walk(child, composed, point(values[:3]), (*ancestry, path))
            else:
                count = int(fields[0])
                if len(fields) != 2 + count*3:
                    raise ValueError("Malformed individual geometry face")
                values = [float(value) for value in fields[2:]]
                vertices = [point(values[i:i+3]) for i in range(0, len(values), 3)]
                triangles = [vertices[:3]] if count == 3 else [vertices[:3], [vertices[0], vertices[2], vertices[3]]]
                # LDraw to canonical conversion exactly once, below all file transforms.
                faces.extend([[(p[0], -p[1], -p[2]) for p in triangle] for triangle in triangles])
                if len(faces) > max_faces:
                    raise ValueError("Individual thumbnail face budget exceeded")

    walk(reference, [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]], [0., 0., 0.], ())
    if not faces:
        raise ValueError("Individual candidate has no supported triangle geometry")
    return faces, hashes


def render_individual_candidate(part_id: str, geometry_root: Path, output_dir: Path, *, size=192):
    """Three diagnostic views of actual LDraw triangles, never a proxy brick.

    Painter ordering and neutral opaque shading deliberately do not claim exact
    material, BFC/texture appearance, or hidden-surface correctness.
    """
    if not re.fullmatch(PART_ID, part_id) or not 96 <= size <= 512:
        raise ValueError("Invalid individual thumbnail request")
    faces, pins = _part_triangles(Path(geometry_root).absolute(), part_id)
    sheet = Image.new("RGB", (size*3, size+22), "white")
    directions = [(1., .8, 1.), (-1., .8, -1.), (0., -1., .01)]
    def norm(v):
        length = math.sqrt(sum(x*x for x in v))
        return tuple(x/length for x in v)
    def cross(a, b):
        return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    def dot(a, b):
        return sum(x*y for x, y in zip(a, b, strict=True))
    for index, direction in enumerate(directions):
        d = norm(direction)
        right = norm(cross((0, 1, 0), d))
        up = cross(d, right)
        projected = [[(dot(p, right), dot(p, up), dot(p, d)) for p in face] for face in faces]
        points = [p for face in projected for p in face]
        low = [min(p[i] for p in points) for i in range(2)]
        high = [max(p[i] for p in points) for i in range(2)]
        scale = (size-24) / max(high[0]-low[0], high[1]-low[1], 1)
        center = [(a+b)/2 for a, b in zip(low, high)]
        pane = Image.new("RGB", (size, size), "white")
        draw = ImageDraw.Draw(pane)
        for face in sorted(projected, key=lambda triangle: sum(p[2] for p in triangle)):
            a, b, c = face
            normal = cross(tuple(b[i]-a[i] for i in range(3)), tuple(c[i]-a[i] for i in range(3)))
            length = math.sqrt(dot(normal, normal))
            shade = round(140 + 80*abs(normal[2])/length) if length else 180
            draw.polygon([(size/2+(p[0]-center[0])*scale, size/2-(p[1]-center[1])*scale) for p in face],
                         fill=(shade, shade, shade))
        sheet.paste(pane, (index*size, 0))
    ImageDraw.Draw(sheet).text((6, size+3), f"LDraw {part_id} | neutral mesh views | underside at right", fill="black")
    receipt = _immutable(Path(output_dir) / f"part-{part_id}-views.png", _png(sheet))
    return {**receipt, "part_id": part_id, "geometry_ref": f"parts/{part_id}.dat", "geometry_pins": pins,
            "renderer": "individual-triangle-painter-v1", "triangle_count": len(faces),
            "limitations": ["Neutral opaque shading; not colour/material evidence.",
                            "Diagnostic painter ordering; BFC, textures and exact occlusion are not certified."]}


def prepare_part_evidence(observations, pages_dir: Path, geometry_root: Path, output_dir: Path, *, check=lambda: None):
    observations = [PartObservation.model_validate(item) for item in observations]
    if len(observations) > 64 or len({o.observation_id for o in observations}) != len(observations):
        raise ValueError("Duplicate or excessive part observations")
    records, images, findings, thumbnails = [], [], [], {}
    for observation in observations:
        check()
        crop = crop_callout(observation, pages_dir, output_dir)
        images.append(crop["path"])
        candidates = []
        for candidate in observation.candidates:
            check()
            document = _document(geometry_root)
            reference = f"parts/{candidate.part_id}.dat"
            if reference not in document.get("resources", {}):
                findings.append({"code": "candidate_geometry_unavailable", "observation_id": observation.observation_id,
                                 "part_id": candidate.part_id, "message": "No local verified individual geometry for this candidate."})
                continue
            # Unsafe/mutated assets are hard errors. Only absence remains a quality finding.
            if candidate.part_id not in thumbnails:
                thumbnails[candidate.part_id] = render_individual_candidate(candidate.part_id, geometry_root, output_dir)
            receipt = thumbnails[candidate.part_id]
            candidates.append({**candidate.model_dump(mode="json"), "thumbnail": receipt})
            images.append(receipt["path"])
        records.append({"observation": observation.model_dump(mode="json"), "callout": crop, "candidates": candidates})
    result = {"version": VERSION, "observations": records, "image_paths": list(dict.fromkeys(images)),
              "findings": findings, "scope": "Source crops and actual individual geometry; candidate identities remain unverified."}
    receipt = _immutable(Path(output_dir) / "part-evidence.json", canonical(result))
    return {**result, "receipt": receipt}


def compare_masked_images(source: Path, rendered: Path, source_mask: Path, render_mask: Path, *, occlusion_mask: Path | None = None):
    """Rank explicitly masked, already registered images; never infer masks or truth.

    White in either foreground mask means object; white in occlusion_mask means
    exclude. All canvases must already share the source camera/crop coordinates.
    """
    source_image, source_hash = _image(source)
    rendered_image, render_hash = _image(rendered)
    a, a_hash = _image(source_mask)
    b, b_hash = _image(render_mask)
    if len({source_image.size, rendered_image.size, a.size, b.size}) != 1:
        raise ValueError("Masked comparison requires registered equal-size image canvases")
    a, b = a.convert("L").point(lambda v: 255 if v >= 128 else 0), b.convert("L").point(lambda v: 255 if v >= 128 else 0)
    valid = Image.new("L", a.size, 255)
    occlusion_hash = None
    if occlusion_mask is not None:
        occlusion, occlusion_hash = _image(occlusion_mask)
        if occlusion.size != a.size:
            raise ValueError("Occlusion mask differs from comparison canvas")
        valid = occlusion.convert("L").point(lambda v: 0 if v >= 128 else 255)
    a, b = ImageChops.multiply(a, valid), ImageChops.multiply(b, valid)
    def count(image):
        return image.histogram()[255]
    union, intersection = count(ImageChops.lighter(a, b)), count(ImageChops.darker(a, b))
    result = {"version": "explicit-mask-image-rank-v1", "status": "insufficient", "ranking_score": None,
              "silhouette_iou": None, "edge_f1": None,
              "source_sha256": source_hash, "render_sha256": render_hash,
              "source_mask_sha256": a_hash, "render_mask_sha256": b_hash, "occlusion_mask_sha256": occlusion_hash,
              "valid_pixels": count(valid), "source_foreground_pixels": count(a), "render_foreground_pixels": count(b),
              "limitations": ["Ranking only; mask quality and camera registration require source review.",
                              "Excluded or hidden surfaces and real materials are not evaluated."]}
    if not count(a) or not count(b) or not union:
        return {**result, "reason": "Both masks need visible object pixels"}
    if max(count(a), count(b))/max(1, count(valid)) > MASK_POLICY["maximum_foreground_fraction"]:
        return {**result, "reason": "Near-full foreground cannot provide a meaningful silhouette score"}
    ae = ImageChops.subtract(a.filter(ImageFilter.MaxFilter(3)), a.filter(ImageFilter.MinFilter(3)))
    be = ImageChops.subtract(b.filter(ImageFilter.MaxFilter(3)), b.filter(ImageFilter.MinFilter(3)))
    # One-pixel edge tolerance is recorded; mask boundaries at excluded regions are ignored.
    interior = valid.filter(ImageFilter.MinFilter(3))
    ae, be = ImageChops.multiply(ae, interior), ImageChops.multiply(be, interior)
    precision = count(ImageChops.darker(be, ae.filter(ImageFilter.MaxFilter(3)))) / max(1, count(be))
    recall = count(ImageChops.darker(ae, be.filter(ImageFilter.MaxFilter(3)))) / max(1, count(ae))
    f1 = 2*precision*recall/max(1e-12, precision+recall)
    iou = intersection/union
    return {**result, "status": "ranked", "silhouette_iou": iou, "edge_f1": f1, "edge_tolerance_pixels": 1,
            "ranking_score": .6*iou + .4*f1, "score_direction": "higher_is_better", "colour_comparison": "not_run"}


def _flood_background(distances, excluded, width, height, tolerance):
    """Remove only colour-compatible background connected to the canvas boundary.

    Excluded pixels are passable, so an ignored arrow cannot enclose an invented
    foreground region. They never contribute pixels to either silhouette.
    """
    allowed = bytearray(d <= tolerance or excluded[i] for i, d in enumerate(distances))
    reached, queue = bytearray(width * height), deque()
    boundary = list(range(width)) + list(range((height-1)*width, height*width))
    boundary += [y*width for y in range(height)] + [y*width+width-1 for y in range(height)]
    for index in boundary:
        if allowed[index] and not reached[index]:
            reached[index] = 1
            queue.append(index)
    while queue:
        index = queue.popleft()
        x, y = index % width, index // width
        neighbours = []
        if x:
            neighbours.append(index-1)
        if x+1 < width:
            neighbours.append(index+1)
        if y:
            neighbours.append(index-width)
        if y+1 < height:
            neighbours.append(index+width)
        for other in neighbours:
            if allowed[other] and not reached[other]:
                reached[other] = 1
                queue.append(other)
    return bytearray(255 if not reached[i] and not excluded[i] else 0 for i in range(width*height))


def _foreground_components(mask, width, height):
    remaining, components = bytearray(mask), []
    boundary_pixels = 0
    for start in range(len(remaining)):
        if not remaining[start]:
            continue
        remaining[start] = 0
        queue, count = deque([start]), 0
        while queue:
            index = queue.popleft()
            x, y = index % width, index // width
            count += 1
            boundary_pixels += x == 0 or y == 0 or x == width-1 or y == height-1
            neighbours = []
            if x:
                neighbours.append(index-1)
            if x+1 < width:
                neighbours.append(index+1)
            if y:
                neighbours.append(index-width)
            if y+1 < height:
                neighbours.append(index+width)
            for other in neighbours:
                if remaining[other]:
                    remaining[other] = 0
                    queue.append(other)
        components.append(count)
    return sorted(components, reverse=True), boundary_pixels


def _border_foreground(image, excluded_image):
    """Return a retained automatic mask, uncertainty band and fail-closed checks.

    This deliberately supports one visible assembly against a nearly uniform
    border colour. It does not choose a largest component, erase annotations,
    infer transparent surfaces, or call an automatically derived mask reviewed.
    """
    width, height = image.size
    rgb = image.convert("RGB").tobytes()
    pixels = list(zip(rgb[0::3], rgb[1::3], rgb[2::3], strict=True))
    excluded = excluded_image.tobytes()
    valid_count = sum(not value for value in excluded)
    border_width = MASK_POLICY["border_width_pixels"]
    border_indices = [y*width+x for y in range(height) for x in range(width)
        if (x < border_width or y < border_width or x >= width-border_width or y >= height-border_width)
        and not excluded[y*width+x]]
    checks = {"status": "unscorable", "reasons": [], "valid_pixels": valid_count,
        "border_sample_pixels": len(border_indices), "foreground_pixels": 0,
        "foreground_fraction": 0., "automatic_checks_only": True}
    empty = Image.new("L", image.size, 0)
    if (min(image.size) < 16 or valid_count < 64 or len(border_indices) < 32
            or valid_count/(width*height) < MASK_POLICY["minimum_valid_fraction"]):
        checks["reasons"].append("Insufficient unexcluded canvas or border pixels for background estimation")
        return empty, empty.copy(), checks
    border = [pixels[i] for i in border_indices]
    bin_width = MASK_POLICY["colour_bin_width"]
    bins = Counter(tuple(channel//bin_width for channel in pixel) for pixel in border)
    mode = sorted(bins, key=lambda key: (-bins[key], key))[0]
    cluster = [pixel for pixel in border if tuple(channel//bin_width for channel in pixel) == mode]
    centre = tuple(int(median(pixel[channel] for pixel in cluster)) for channel in range(3))
    def distance(pixel, colour):
        return max(abs(a-b) for a, b in zip(pixel, colour, strict=True))
    cluster = [pixel for pixel in border if distance(pixel, centre) <= MASK_POLICY["background_cluster_radius"]]
    colour = tuple(int(median(pixel[channel] for pixel in cluster)) for channel in range(3))
    residuals = sorted(distance(pixel, colour) for pixel in cluster)
    p95 = residuals[min(len(residuals)-1, int(.95*len(residuals)))]
    tolerance = min(MASK_POLICY["maximum_background_tolerance"],
        max(MASK_POLICY["minimum_background_tolerance"], p95+2))
    border_support = sum(distance(pixel, colour) <= tolerance for pixel in border)/len(border)
    checks.update(background_rgb=list(colour), background_tolerance=tolerance,
        border_cluster_fraction=len(cluster)/len(border), border_background_fraction=border_support,
        border_residual_p95=p95)
    if border_support < MASK_POLICY["minimum_border_background_fraction"]:
        checks["reasons"].append("Border colours do not establish one dominant uniform background")
    distances = [distance(pixel, colour) for pixel in pixels]
    delta = MASK_POLICY["tolerance_sensitivity_delta"]
    mask = _flood_background(distances, excluded, width, height, tolerance)
    lower = _flood_background(distances, excluded, width, height, max(0, tolerance-delta))
    upper = _flood_background(distances, excluded, width, height, tolerance+delta)
    foreground_count = sum(bool(value) for value in mask)
    union = sum(bool(a or b) for a, b in zip(lower, upper, strict=True))
    intersection = sum(bool(a and b) for a, b in zip(lower, upper, strict=True))
    sensitivity_iou = intersection/union if union else None
    uncertain = bytes(255 if a != b else 0 for a, b in zip(lower, upper, strict=True))
    components, boundary_pixels = _foreground_components(mask, width, height)
    primary_fraction = components[0]/foreground_count if foreground_count else 0.
    fraction = foreground_count/valid_count
    checks.update(foreground_pixels=foreground_count, foreground_fraction=fraction,
        component_count=len(components), largest_component_pixels=components[:16],
        primary_component_fraction=primary_fraction, foreground_boundary_pixels=boundary_pixels,
        tolerance_mask_iou=sensitivity_iou, uncertain_pixels=uncertain.count(255),
        uncertain_fraction_of_foreground=uncertain.count(255)/max(1, foreground_count))
    if (foreground_count < MASK_POLICY["minimum_foreground_pixels"]
            or fraction < MASK_POLICY["minimum_foreground_fraction"]):
        checks["reasons"].append("No meaningful visible foreground was separated from background")
    if fraction > MASK_POLICY["maximum_foreground_fraction"]:
        checks["reasons"].append("Near-full foreground cannot provide a meaningful silhouette score")
    if sensitivity_iou is None or sensitivity_iou < MASK_POLICY["minimum_tolerance_mask_iou"]:
        checks["reasons"].append("Foreground is ambiguous under small background-tolerance changes")
    if boundary_pixels:
        checks["reasons"].append("Foreground touches the canvas boundary; object completeness is unknown")
    if (len(components) > 1 and components[1] >= MASK_POLICY["minimum_foreground_component_pixels"]
            and primary_fraction < MASK_POLICY["minimum_primary_component_fraction"]):
        checks["reasons"].append("Multiple substantial regions may contain annotations or detached objects; explicit masks required")
    if not checks["reasons"]:
        checks["status"] = "passed"
    return Image.frombytes("L", image.size, bytes(mask)), Image.frombytes("L", image.size, uncertain), checks


def compare_source_render_images(source: Path, rendered: Path, source_bbox, output_dir: Path, *,
                                 render_source_rect, excluded_source_boxes=(), camera_registration=None):
    """Retain conservative background-aware masks for a source-camera comparison.

    Failed/ambiguous segmentation or missing camera registration is unscorable.
    A passed automatic mask sanity check is not source/assembly/human validation.
    The pilot supports a single visible assembly; arrows/labels/callouts require
    explicit source-coordinate exclusions applied equally to both images.
    """
    box = SourcePanel(page_index=0, source_sha256="0"*64, bbox=source_bbox).bbox
    if len(excluded_source_boxes) > 32:
        raise ValueError("Exclusion masks exceed bound")
    source_image, source_hash = _image(source)
    render_image, render_hash = _image(rendered)
    rect = render_source_rect
    if (not isinstance(rect, dict) or any(type(rect.get(k)) not in (int, float) or not math.isfinite(rect[k])
            for k in ("x", "y", "width", "height")) or rect["width"] <= 0 or rect["height"] <= 0
            or rect["x"] < 0 or rect["y"] < 0 or rect["x"]+rect["width"] > render_image.width+1
            or rect["y"]+rect["height"] > render_image.height+1):
        raise ValueError("Source-camera pixel rectangle is outside the actual render")
    x0, y0, x1, y1 = box
    source_crop = source_image.crop((math.floor(x0*source_image.width), math.floor(y0*source_image.height),
                                    math.ceil(x1*source_image.width), math.ceil(y1*source_image.height))).convert("RGB")
    render_crop = render_image.crop((math.floor(rect["x"]+x0*rect["width"]), math.floor(rect["y"]+y0*rect["height"]),
                                    math.ceil(rect["x"]+x1*rect["width"]), math.ceil(rect["y"]+y1*rect["height"]))).convert("RGB")
    scale = min(1., 512/max(source_crop.size))
    size = (max(1, round(source_crop.width*scale)), max(1, round(source_crop.height*scale)))
    source_crop = source_crop.resize(size, Image.Resampling.LANCZOS)
    render_crop = render_crop.resize(size, Image.Resampling.LANCZOS)
    exclude = Image.new("L", size, 0)
    draw = ImageDraw.Draw(exclude)
    for rectangle in excluded_source_boxes:
        a, b, c, d = SourcePanel(page_index=0, source_sha256="0"*64, bbox=rectangle).bbox
        a, b, c, d = max(x0, a), max(y0, b), min(x1, c), min(y1, d)
        if a < c and b < d:
            draw.rectangle(((a-x0)/(x1-x0)*size[0], (b-y0)/(y1-y0)*size[1],
                            (c-x0)/(x1-x0)*size[0], (d-y0)/(y1-y0)*size[1]), fill=255)
    source_mask, source_uncertainty, source_checks = _border_foreground(source_crop, exclude)
    render_mask, render_uncertainty, render_checks = _border_foreground(render_crop, exclude)
    registration_reasons = []
    registration = camera_registration or {}
    if registration.get("status") != "registered":
        registration_reasons.append("Verified source-camera pixel registration is required")
    else:
        # These are source/render integrity bindings, not soft segmentation failures.
        if registration.get("render_sha256") != render_hash:
            raise ValueError("Source comparison registration render hash changed")
        if registration.get("screenshot_size") != list(render_image.size):
            raise ValueError("Source comparison registration image dimensions changed")
        if registration.get("render_source_rect") != rect:
            raise ValueError("Source comparison registration rectangle changed")
        if registration.get("version") != "source-render-registration-v1":
            registration_reasons.append("Unsupported source-camera registration version")
    if source_image.mode in ("RGBA", "LA") and source_image.getchannel("A").getextrema() != (255, 255):
        registration_reasons.append("Transparent source pixels require an explicit reviewed foreground mask")
    if render_image.mode in ("RGBA", "LA") and render_image.getchannel("A").getextrema() != (255, 255):
        registration_reasons.append("Transparent render pixels require an explicit reviewed foreground mask")
    reasons = ["Source: "+reason for reason in source_checks["reasons"]]
    reasons += ["Render: "+reason for reason in render_checks["reasons"]] + registration_reasons
    scope = {"original_source_sha256": source_hash, "source_bbox": list(box),
        "source_crop_pixels": [math.floor(x0*source_image.width), math.floor(y0*source_image.height),
                               math.ceil(x1*source_image.width), math.ceil(y1*source_image.height)],
        "excluded_source_boxes": [list(item) for item in excluded_source_boxes],
        "output_size": list(size), "mask_policy": MASK_POLICY}
    output = Path(output_dir)
    receipts = {name: _immutable(output / (name+".png"), _png(image)) for name, image in
                [("source", source_crop), ("render", render_crop), ("source-mask", source_mask),
                 ("render-mask", render_mask), ("excluded", exclude),
                 ("source-uncertainty", source_uncertainty), ("render-uncertainty", render_uncertainty)]}
    comparison = {"version": "background-mask-image-rank-v2", "status": "unscorable", "ranking_score": None,
        "silhouette_iou": None, "edge_f1": None, "source_sha256": receipts["source"]["sha256"],
        "render_sha256": receipts["render"]["sha256"], "source_mask_sha256": receipts["source-mask"]["sha256"],
        "render_mask_sha256": receipts["render-mask"]["sha256"], "occlusion_mask_sha256": receipts["excluded"]["sha256"],
        "valid_pixels": source_checks["valid_pixels"], "source_foreground_pixels": source_checks["foreground_pixels"],
        "render_foreground_pixels": render_checks["foreground_pixels"],
        "limitations": ["Ranking only; automatic mask checks and camera registration do not establish assembly correctness.",
                        "Excluded or hidden surfaces and real materials are not evaluated."]}
    if not reasons:
        comparison = {**compare_masked_images(output / "source.png", output / "render.png", output / "source-mask.png",
            output / "render-mask.png", occlusion_mask=output / "excluded.png"), "version": "background-mask-image-rank-v2"}
        if comparison["status"] != "ranked":
            reasons.append(comparison.get("reason", "Explicit-mask comparison unavailable"))
    rank_eligible = not reasons and comparison["status"] == "ranked"
    result = {**comparison, "original_source_sha256": source_hash, "original_render_sha256": render_hash,
              "source_bbox": list(box), "render_source_rect": rect, "images": receipts,
              "rank_eligible": rank_eligible, "reason": "; ".join(reasons) if reasons else None,
              "comparison_scope": scope, "comparison_scope_sha256": hashlib.sha256(canonical(scope)).hexdigest(),
              "camera_registration": registration,
              "camera_registration_sha256": hashlib.sha256(canonical(registration)).hexdigest(),
              "segmentation_checks": {"source": source_checks, "render": render_checks,
                  "comparability": {"status": "passed" if rank_eligible else "unscorable", "reasons": reasons,
                      "registration_bound": not registration_reasons, "shared_exclusion_mask": True,
                      "automatic_checks_only": True}},
              "mask_policy": {**MASK_POLICY, "excluded_source_boxes": [list(item) for item in excluded_source_boxes]}}
    result["limitations"] += ["Background-colour masks may retain shadows or unexcluded annotations and miss white/transparent surfaces with background-like colour.",
        "One dominant nearly uniform border and one visible assembly are required; unsupported crops are unscorable.",
        "Threshold sensitivity is a diagnostic bound, not calibrated segmentation confidence.",
        "Only the declared source region is evaluated; missing/occluded detail cannot be certified."]
    return {**result, "receipt": _immutable(output / "comparison.json", canonical(result))}
