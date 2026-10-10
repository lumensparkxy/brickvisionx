"""Conservative whole-part coincidence evidence from verified individual meshes.

Only the 24 origin-preserving proper signed axis rotations are considered. Exact
triangle multisets, including multiplicity, must agree: equal bounds, vertex sets
or connector layouts are insufficient. Different tessellations may therefore
produce false negatives. No assembly placement or part-specific symmetry table
is used, and mesh appearance, clutch and general collision checks are outside
this diagnostic's scope.
"""
from __future__ import annotations

from collections import Counter
import itertools
import math
from pathlib import Path
import re

from ..core.models import Pose
from ..releases.models import digest
from .connectors import rotation_matrix
from .perception import _part_triangles

VERSION = "verified-whole-part-axis-symmetry-v1"
POSE_TOLERANCE = 1e-10
MAX_FACES = 20_000


def _axis_rotations():
    result = []
    for axes in itertools.permutations(range(3)):
        for signs in itertools.product((-1, 1), repeat=3):
            matrix = tuple(tuple(signs[i] if j == axes[i] else 0 for j in range(3)) for i in range(3))
            determinant = (matrix[0][0]*(matrix[1][1]*matrix[2][2]-matrix[1][2]*matrix[2][1])
                           - matrix[0][1]*(matrix[1][0]*matrix[2][2]-matrix[1][2]*matrix[2][0])
                           + matrix[0][2]*(matrix[1][0]*matrix[2][1]-matrix[1][1]*matrix[2][0]))
            if determinant == 1:
                result.append(matrix)
    return tuple(result)


AXIS_ROTATIONS = _axis_rotations()
IDENTITY = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def relative_axis_rotation(first, second):
    """Return a finite supported relative rotation only for coincident origins."""
    first, second = Pose.model_validate(first), Pose.model_validate(second)
    if math.dist(first.position_ldu, second.position_ldu) > POSE_TOLERANCE:
        return None
    a, b = rotation_matrix(first.quaternion_xyzw), rotation_matrix(second.quaternion_xyzw)
    relative = [[sum(a[k][i]*b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    for candidate in AXIS_ROTATIONS:
        if max(abs(relative[i][j]-candidate[i][j]) for i in range(3) for j in range(3)) <= POSE_TOLERANCE:
            return candidate
    return None


def _signature(faces, matrix=IDENTITY):
    # Signed permutations perform no approximate coordinate arithmetic. Never
    # round vertices: tiny asymmetric geometry must not become a symmetry proof.
    axes = [(next(j for j, v in enumerate(row) if v), next(v for v in row if v)) for row in matrix]
    return Counter(tuple(sorted(tuple(point[axis]*sign for axis, sign in axes) for point in face))
                   for face in faces)


def verified_origin_symmetries(geometry_root: Path, geometry_ref: str, *, max_faces=MAX_FACES):
    """Verify current bytes on every request; callers may cache within one audit.

    Integrity, path, classification and parsing failures propagate. A triangle
    budget exhaustion is an explicit unsupported diagnostic, never a proof.
    """
    if (type(max_faces) is not int or not 1 <= max_faces <= MAX_FACES
            or not re.fullmatch(r"parts/[a-z0-9]+\.dat", geometry_ref)):
        raise ValueError("Invalid whole-part symmetry scope or face budget")
    root = Path(geometry_root).absolute()
    try:
        faces, pins = _part_triangles(root, Path(geometry_ref).stem, max_faces=max_faces)
    except ValueError as error:
        if str(error) != "Individual thumbnail face budget exceeded":
            raise
        return {"version": VERSION, "geometry_ref": geometry_ref, "status": "unknown_face_limit",
                "max_faces": max_faces, "rotations": [], "reason": str(error)}
    signature = _signature(faces)
    rotations = [matrix for matrix in AXIS_ROTATIONS if _signature(faces, matrix) == signature]
    return {"version": VERSION, "geometry_ref": geometry_ref, "status": "checked_finite_rotations",
            "triangle_count": len(faces), "max_faces": max_faces,
            "geometry_files": dict(sorted(pins.items())), "geometry_closure_sha256": digest(pins),
            "triangle_multiset_sha256": digest(sorted(signature.items())),
            "rotations_checked": len(AXIS_ROTATIONS), "rotations": rotations,
            "mesh_comparison": "exact_triangle_multiset_including_multiplicity_no_rounding",
            "pose_tolerance": POSE_TOLERANCE,
            "limitations": ["Only origin-preserving proper signed axis rotations were examined.",
                            "Equivalent surfaces with different triangulations may be missed.",
                            "Appearance/materials, general intersections and physical clutch are not checked."]}
