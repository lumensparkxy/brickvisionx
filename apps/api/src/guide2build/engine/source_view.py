"""Bounded orthographic image-landmark fitting, independent of assembly placement.

The inputs are correspondences, not detections: the caller must bind the named visible
landmarks to verified individual geometry and the official page image. An image fit
does not prove a connector, silhouette, occlusion, or assembly interpretation.
"""
from math import acos, cos, isfinite, pi, sin, sqrt
from typing import Literal

from pydantic import Field, model_validator

from ..core.models import StrictModel


class SourceLandmark(StrictModel):
    instance_id: str = Field(min_length=1, max_length=160)
    landmark_id: str = Field(min_length=1, max_length=160)
    image_uv: tuple[float, float]

    @model_validator(mode="after")
    def bounds(self):
        if not all(0 <= value <= 1 for value in self.image_uv):
            raise ValueError("Source landmark must use full-page normalized coordinates")
        return self


class SourceViewObservation(StrictModel):
    step_id: str = Field(min_length=1, max_length=160)
    landmarks: list[SourceLandmark] = Field(max_length=64)
    view_family: Literal["unconstrained", "upright_above"] = "unconstrained"

    @model_validator(mode="after")
    def unique_landmarks(self):
        names = [(item.instance_id, item.landmark_id) for item in self.landmarks]
        if len(set(names)) != len(names):
            raise ValueError("Source landmarks must name distinct physical locations")
        return self


class SourceCamera(StrictModel):
    projection: Literal["orthographic"]
    right: tuple[float, float, float]
    up: tuple[float, float, float]
    target_ldu: tuple[float, float, float]
    vertical_span_ldu: float = Field(ge=0.001, le=10_000_000)
    image_size: tuple[int, int]

    @model_validator(mode="after")
    def bounded_frame(self):
        if any(abs(value) > 1_000_000 for value in self.target_ldu):
            raise ValueError("Source camera target exceeds coordinate bound")
        if any(type(value) is not int or not 64 <= value <= 16_384 for value in self.image_size):
            raise ValueError("Source image dimensions exceed bounds")
        if (abs(_dot(self.right, self.right)-1) > 1e-6
                or abs(_dot(self.up, self.up)-1) > 1e-6
                or abs(_dot(self.right, self.up)) > 1e-6):
            raise ValueError("Source camera axes must be orthonormal")
        return self


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b, strict=True))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _norm(a):
    length = sqrt(_dot(a, a))
    return tuple(value/length for value in a) if length > 1e-15 else None


def _eigen(matrix):
    """Jacobi diagonalization of a 3x3 symmetric covariance; no numeric dependency."""
    a = [list(row) for row in matrix]
    vectors = [[float(i == j) for j in range(3)] for i in range(3)]
    for _ in range(40):
        p, q = max(((0, 1), (0, 2), (1, 2)), key=lambda pair: abs(a[pair[0]][pair[1]]))
        if abs(a[p][q]) <= max(1.0, max(abs(a[i][i]) for i in range(3)))*1e-14:
            break
        tau = (a[q][q]-a[p][p])/(2*a[p][q])
        tangent = (1 if tau >= 0 else -1)/(abs(tau)+sqrt(1+tau*tau))
        c = 1/sqrt(1+tangent*tangent)
        s = tangent*c
        apq = a[p][q]
        a[p][p] -= tangent*apq
        a[q][q] += tangent*apq
        a[p][q] = a[q][p] = 0.0
        for k in range(3):
            if k not in (p, q):
                akp, akq = a[k][p], a[k][q]
                a[k][p] = a[p][k] = c*akp-s*akq
                a[k][q] = a[q][k] = s*akp+c*akq
            vkp, vkq = vectors[k][p], vectors[k][q]
            vectors[k][p], vectors[k][q] = c*vkp-s*vkq, s*vkp+c*vkq
    return sorted(((max(0.0, a[j][j]), tuple(vectors[i][j] for i in range(3)))
                   for j in range(3)), reverse=True)


def project_source_points(camera: SourceCamera | dict, world_points):
    """Full-page UV projection shared by fit tests and evidence validation."""
    view = camera if isinstance(camera, SourceCamera) else SourceCamera.model_validate(camera)
    aspect = view.image_size[0]/view.image_size[1]
    return [(.5+_dot(view.right, tuple(p-t for p, t in zip(point, view.target_ldu, strict=True)))
             / (view.vertical_span_ldu*aspect),
             .5-_dot(view.up, tuple(p-t for p, t in zip(point, view.target_ldu, strict=True)))
             / view.vertical_span_ldu) for point in world_points]


def validate_rendered_source_camera(camera: dict, frame: dict):
    """Check that recorded Three.js matrices project the requested full-page view.

    Verifying a copy of the input alone would allow a stale/default camera to be
    labelled as fitted. This verifies the matrix actually read by the renderer.
    """
    spec = SourceCamera.model_validate(camera)
    if not isinstance(frame, dict) or frame.get("input") != spec.model_dump(mode="json"):
        raise ValueError("Rendered source camera input mismatch")
    try:
        viewport, rect = frame["viewport"], frame["source_rect"]
        width, height = viewport["width"], viewport["height"]
        if any(not isinstance(v, (int, float)) or not isfinite(v) or v <= 0 or v > 16_384
               for v in (width, height, rect["width"], rect["height"])):
            raise ValueError("Invalid source camera screenshot bounds")
        if (not 0 <= rect["x"] <= width or not 0 <= rect["y"] <= height
                or rect["x"]+rect["width"] > width+1e-6 or rect["y"]+rect["height"] > height+1e-6
                or abs(rect["width"]/rect["height"]-spec.image_size[0]/spec.image_size[1]) > 1e-6):
            raise ValueError("Rendered source rectangle does not preserve page aspect")
        projection, inverse = frame["projection_matrix"], frame["matrix_world_inverse"]
        for matrix in (projection, inverse):
            if len(matrix) != 16 or any(not isinstance(v, (int, float)) or not isfinite(v) for v in matrix):
                raise ValueError("Invalid actual source camera matrix")

        def multiply(matrix, point):
            return tuple(sum(matrix[j*4+i]*point[j] for j in range(4)) for i in range(4))

        right, up = spec.right, spec.up
        back = _cross(right, up)
        offsets = [(0, 0, 0), tuple(v*spec.vertical_span_ldu*spec.image_size[0]/spec.image_size[1]/4 for v in right),
                   tuple(v*spec.vertical_span_ldu/4 for v in up), tuple(v*spec.vertical_span_ldu/4 for v in back)]
        for offset, expected in zip(offsets, ((.5, .5), (.75, .5), (.5, .25), (.5, .5)), strict=True):
            point = tuple(spec.target_ldu[i]+offset[i] for i in range(3))+(1,)
            projected = multiply(projection, multiply(inverse, point))
            if abs(projected[3]) < 1e-10:
                raise ValueError("Invalid actual source projection")
            u = ((projected[0]/projected[3]+1)*width/2-rect["x"])/rect["width"]
            v = ((1-projected[1]/projected[3])*height/2-rect["y"])/rect["height"]
            if abs(u-expected[0]) > 2e-5 or abs(v-expected[1]) > 2e-5:
                raise ValueError("Actual renderer matrices do not project the requested source camera")
    except (KeyError, TypeError, ZeroDivisionError) as error:
        raise ValueError("Incomplete rendered source camera evidence") from error


def fit_source_view(world_points, image_uv, image_size, *, view_family="unconstrained",
                    max_rms_pixels=4.0, max_point_pixels=12.0, ambiguity_pixels=0.75):
    """Fit a similarity-scaled orthographic camera without changing any world pose.

    Four distinct, non-collinear correspondences are the minimum. Planar points
    generally have a mirrored-view ambiguity. ``upright_above`` is an explicit
    additional assumption (camera direction and screen-up both have positive Y),
    never a default inferred from a good residual. All correspondences contribute
    to the result: outliers are reported, not silently discarded.
    """
    if view_family not in ("unconstrained", "upright_above"):
        raise ValueError("Unknown declared source camera family")
    if (not isinstance(image_size, (list, tuple)) or len(image_size) != 2
            or any(type(value) is not int or not 64 <= value <= 16_384 for value in image_size)):
        raise ValueError("Source image dimensions exceed bounds")
    if len(world_points) != len(image_uv) or len(world_points) > 64:
        raise ValueError("Source camera needs paired, bounded landmarks")
    if any(not isinstance(p, (list, tuple)) or len(p) != 3
           or any(not isinstance(v, (int, float)) or not isfinite(v) or abs(v) > 1_000_000 for v in p)
           for p in world_points):
        raise ValueError("Invalid source landmark world coordinates")
    if any(not isinstance(p, (list, tuple)) or len(p) != 2
           or any(not isinstance(v, (int, float)) or not isfinite(v) or not 0 <= v <= 1 for v in p)
           for p in image_uv):
        raise ValueError("Invalid full-page source landmark coordinates")
    if any(not isfinite(v) or not 0 < v <= 100 for v in (max_rms_pixels, max_point_pixels, ambiguity_pixels)):
        raise ValueError("Invalid source camera fit thresholds")
    result = {
        "fit_version": "orthographic-landmarks-v1", "status": "insufficient", "camera": None,
        "rms_pixels": None, "normalized_error": None, "max_error_pixels": None,
        "landmark_count": len(world_points), "landmark_residuals_pixels": [], "search_evaluations": 0,
        "thresholds_pixels": {"rms": max_rms_pixels, "point": max_point_pixels, "ambiguity": ambiguity_pixels},
        "ambiguity": {"view_family": view_family, "world_rank": 0, "competing_cameras": [], "candidate_cameras": [],
                      "orthographic_distance_unobservable": True},
        "limitations": ["Named landmark agreement only; silhouette, occlusion and assembly are not certified.",
                        "Orthographic camera family; perspective artwork or inaccurate observations can fail.",
                        "Camera depth is an orthographic gauge and does not establish physical dimensions."],
    }
    if len(world_points) < 4:
        return {**result, "reason": "At least four named source landmarks are required"}
    count = len(world_points)
    center = tuple(sum(p[j] for p in world_points)/count for j in range(3))
    points = [tuple(p[j]-center[j] for j in range(3)) for p in world_points]
    covariance = [[sum(p[i]*p[j] for p in points) for j in range(3)] for i in range(3)]
    eigen = _eigen(covariance)
    rank = sum(value > max(1e-10, eigen[0][0]*1e-6) for value, _ in eigen)
    result["ambiguity"]["world_rank"] = rank
    if rank < 2 or len({tuple(p) for p in world_points}) != count:
        return {**result, "reason": "Source landmarks must be distinct and span at least a plane"}
    width, height = image_size
    pixels = [(p[0]*width, -p[1]*height) for p in image_uv]
    image_center = tuple(sum(p[j] for p in pixels)/count for j in range(2))
    observed = [tuple(p[j]-image_center[j] for j in range(2)) for p in pixels]
    if sum(_dot(p, p) for p in observed) < 4:
        return {**result, "reason": "Source landmarks have insufficient image separation"}

    def score(direction):
        result["search_evaluations"] += 1
        d = _norm(direction)
        if d is None or (view_family == "upright_above" and d[1] <= 1e-6):
            return None
        reference = (0, 1, 0) if abs(d[1]) < .99 else (1, 0, 0)
        right = _norm(_cross(reference, d))
        up = _cross(d, right)
        projected = [(_dot(p, right), _dot(p, up)) for p in points]
        denominator = sum(_dot(p, p) for p in projected)
        if denominator < 1e-10:
            return None
        a = sum(p[0]*q[0]+p[1]*q[1] for p, q in zip(projected, observed, strict=True))
        b = sum(p[0]*q[1]-p[1]*q[0] for p, q in zip(projected, observed, strict=True))
        magnitude = sqrt(a*a+b*b)
        if magnitude < 1e-10:
            return None
        r = tuple((a*right[j]-b*up[j])/magnitude for j in range(3))
        u = tuple((b*right[j]+a*up[j])/magnitude for j in range(3))
        if view_family == "upright_above" and u[1] <= 1e-6:
            return None
        scale = magnitude/denominator
        errors = [(scale*_dot(p, r)-q[0], scale*_dot(p, u)-q[1])
                  for p, q in zip(points, observed, strict=True)]
        return {"r": r, "u": u, "d": d, "scale": scale, "errors": errors,
                "sse": sum(_dot(e, e) for e in errors)}

    seeds = []
    # A full-rank least-squares camera is a useful exact seed; the sphere search
    # also covers rank-two inputs and noisy observations without a prior pose.
    affine = []
    for axis in range(2):
        cross_covariance = tuple(sum(p[j]*q[axis] for p, q in zip(points, observed, strict=True))
                                 for j in range(3))
        affine.append(tuple(sum(v[j]*_dot(v, cross_covariance)/value for value, v in eigen
                                if value > max(1e-10, eigen[0][0]*1e-6)) for j in range(3)))
    direction = _norm(_cross(*affine))
    if direction is not None:
        seeds.extend([direction, tuple(-v for v in direction)])
    for i in range(384):
        y = 1-2*(i+.5)/384
        angle = i*pi*(3-sqrt(5))
        radius = sqrt(1-y*y)
        seeds.append((radius*cos(angle), y, radius*sin(angle)))
    scored = sorted((candidate for seed in seeds if (candidate := score(seed)) is not None),
                    key=lambda candidate: candidate["sse"])
    starts = []
    for candidate in scored:
        if all(_dot(candidate["d"], other["d"]) < cos(pi/8) for other in starts):
            starts.append(candidate)
        if len(starts) == 12:
            break
    minima = []
    for candidate in starts:
        step = .2
        for _ in range(180):
            d = candidate["d"]
            right = _norm(_cross((0, 1, 0) if abs(d[1]) < .99 else (1, 0, 0), d))
            up = _cross(d, right)
            neighbors = [candidate]
            for a, b in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
                value = score(tuple(d[j]+step*(a*right[j]+b*up[j]) for j in range(3)))
                if value is not None:
                    neighbors.append(value)
            best = min(neighbors, key=lambda value: value["sse"])
            if best is candidate:
                step *= .5
                if step < 1e-7:
                    break
            candidate = best
        minima.append(candidate)
    if not minima:
        return {**result, "status": "poor_fit", "reason": "No camera satisfies the declared view family"}
    best = min(minima, key=lambda value: value["sse"])
    if rank == 2:
        # Explicitly examine the exact planar reflected solution, even if a
        # coarse direction search did not happen to start in its basin.
        normal = eigen[-1][1]
        reflected_right = tuple(best["r"][j]-2*_dot(best["r"], normal)*normal[j] for j in range(3))
        reflected_up = tuple(best["u"][j]-2*_dot(best["u"], normal)*normal[j] for j in range(3))
        reflected = score(_cross(reflected_right, reflected_up))
        if reflected is not None:
            minima.append(reflected)

    def camera_for(fit):
        r, u, scale = fit["r"], fit["u"], fit["scale"]
        target = tuple(center[j]+r[j]*(width/2-image_center[0])/scale
                       +u[j]*(-height/2-image_center[1])/scale for j in range(3))
        return SourceCamera(projection="orthographic", right=r, up=u, target_ldu=target,
                            vertical_span_ldu=height/scale, image_size=image_size).model_dump(mode="json")

    rms = sqrt(best["sse"]/count)
    result.update(rms_pixels=rms, normalized_error=rms/sqrt(width*width+height*height),
                  max_error_pixels=max(sqrt(_dot(e, e)) for e in best["errors"]),
                  landmark_residuals_pixels=[[e[0], -e[1]] for e in best["errors"]])
    if rms > max_rms_pixels or result["max_error_pixels"] > max_point_pixels:
        return {**result, "status": "poor_fit", "reason": "Named landmarks exceed reprojection error bounds"}
    try:
        camera = camera_for(best)
    except ValueError:
        return {**result, "status": "poor_fit", "reason": "Fitted camera exceeds coordinate or scale bounds"}
    competitors = []
    for alternative in sorted(minima, key=lambda value: value["sse"]):
        angle = acos(max(-1, min(1, (_dot(best["r"], alternative["r"])
                                    +_dot(best["u"], alternative["u"])
                                    +_dot(best["d"], alternative["d"])-1)/2)))
        if angle > pi/36 and sqrt(alternative["sse"]/count) <= rms+ambiguity_pixels:
            try:
                competitors.append({"camera": camera_for(alternative),
                                    "rms_pixels": sqrt(alternative["sse"]/count),
                                    "separation_degrees": angle*180/pi})
            except ValueError:
                continue
            break
    result["ambiguity"]["competing_cameras"] = competitors
    if competitors:
        result["ambiguity"]["candidate_cameras"] = [{"camera": camera, "rms_pixels": rms}, *competitors]
        return {**result, "status": "ambiguous", "reason": "Competing source views fit the named landmarks"}
    return {**result, "status": "fitted", "camera": camera}
