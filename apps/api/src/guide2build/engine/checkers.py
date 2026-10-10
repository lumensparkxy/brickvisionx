"""Closed registry of deterministic assembly checks.

The existing authored first-four-step connector helper is not a general geometry/collision checker.
It is deliberately NOT registered for automatic releases. Adding a checker requires code review,
explicit supported scope and regression tests; a validation JSON cannot register executable code.
"""
from typing import Callable

# Empty until an independently tested checker can certify a declared complete assembly scope.
_CHECKERS: dict[tuple[str, str], Callable] = {}


def run_registered_checks(scene, geometry_root, checker_id, checker_version):
    checker = _CHECKERS.get((checker_id, checker_version))
    if checker is None:
        raise ValueError("Unsupported deterministic assembly checker; geometry/connector correctness remains unverified")
    actual = checker(scene, geometry_root)
    from ..releases.models import digest
    if (actual.get("scene_sha256") != digest(scene) or actual.get("geometry_check") != "pass"
            or actual.get("connector_check") != "pass"
            or set(actual.get("supported_instance_ids", [])) != {part.instance_id for part in scene.instances}):
        raise ValueError("Registered checker did not pass the complete exact candidate scope")
    return actual
