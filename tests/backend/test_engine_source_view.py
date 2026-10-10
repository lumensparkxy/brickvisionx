from math import sqrt

import pytest
from pydantic import ValidationError

from guide2build.engine.source_view import (
    SourceCamera, SourceViewObservation, fit_source_view, project_source_points, validate_rendered_source_camera,
)


@pytest.fixture
def source_camera():
    return {"projection": "orthographic", "right": [.8, 0, .6],
            "up": [.3, sqrt(.75), -.4], "target_ldu": [5, 5, 10],
            "vertical_span_ldu": 180, "image_size": [1200, 900]}


@pytest.fixture
def asymmetric_points():
    # Original synthetic geometry: varied-height landmarks prevent the planar
    # view reflection. These points are not assembly evidence for the booklet.
    return [(-20, 0, -10), (20, 0, -10), (-20, 0, 10), (20, 0, 10),
            (-10, 8, 20), (-10, 16, 60), (10, 8, 20), (10, 16, 40)]


def test_recovers_asymmetric_orthographic_camera_without_moving_points(source_camera, asymmetric_points):
    before = list(asymmetric_points)
    observations = project_source_points(source_camera, asymmetric_points)
    result = fit_source_view(asymmetric_points, observations, (1200, 900))
    assert result["status"] == "fitted"
    assert result["rms_pixels"] < 1e-6
    assert result["ambiguity"]["world_rank"] == 3
    assert result["ambiguity"]["competing_cameras"] == []
    assert result["search_evaluations"] < 20_000
    assert result["camera"]["right"] == pytest.approx(source_camera["right"], abs=1e-6)
    assert result["camera"]["up"] == pytest.approx(source_camera["up"], abs=1e-6)
    for actual, expected in zip(project_source_points(result["camera"], asymmetric_points), observations, strict=True):
        assert actual == pytest.approx(expected)
    assert asymmetric_points == before


def test_reports_planar_reflection_and_accepts_only_explicit_upright_family(source_camera):
    points = [(-30, 0, -20), (30, 0, -20), (-30, 0, 20), (30, 0, 20), (0, 0, 0)]
    uv = project_source_points(source_camera, points)
    ambiguous = fit_source_view(points, uv, (1200, 900))
    assert ambiguous["status"] == "ambiguous"
    assert ambiguous["camera"] is None
    assert ambiguous["rms_pixels"] < .001
    assert ambiguous["ambiguity"]["world_rank"] == 2
    assert ambiguous["ambiguity"]["competing_cameras"][0]["separation_degrees"] > 5
    assert len(ambiguous["ambiguity"]["candidate_cameras"]) == 2
    fitted = fit_source_view(points, uv, (1200, 900), view_family="upright_above")
    assert fitted["status"] == "fitted"
    assert fitted["ambiguity"]["view_family"] == "upright_above"
    assert fitted["camera"]["up"][1] > 0
    assert fitted["rms_pixels"] < .001


def test_requires_four_distinct_noncollinear_correspondences(source_camera):
    for points in ([(0, 0, 0)]*4, [(i, 0, 0) for i in range(4)], [(0, 0, 0)]*3):
        result = fit_source_view(points, project_source_points(source_camera, points), (1200, 900))
        assert result["status"] == "insufficient"
        assert result["camera"] is None


def test_outlier_is_not_silently_dropped(source_camera, asymmetric_points):
    uv = project_source_points(source_camera, asymmetric_points)
    uv[-1] = (uv[-1][0]+.1, uv[-1][1]-.1)
    result = fit_source_view(asymmetric_points, uv, (1200, 900))
    assert result["status"] == "poor_fit"
    assert result["camera"] is None
    assert result["rms_pixels"] > 4
    assert result["max_error_pixels"] > 12
    assert len(result["landmark_residuals_pixels"]) == len(asymmetric_points)


def test_subpixel_observation_noise_is_measured(source_camera, asymmetric_points):
    uv = project_source_points(source_camera, asymmetric_points)
    noisy = [(u+(.2 if i % 2 else -.2)/1200, v+.15/900) for i, (u, v) in enumerate(uv)]
    result = fit_source_view(asymmetric_points, noisy, (1200, 900))
    assert result["status"] == "fitted"
    assert 0 < result["rms_pixels"] < 1
    assert result["normalized_error"] == pytest.approx(result["rms_pixels"]/1500)


@pytest.mark.parametrize("points,uv,size", [
    ([(float("nan"), 0, 0)], [(.5, .5)], (1200, 900)),
    ([(1_000_001, 0, 0)], [(.5, .5)], (1200, 900)),
    ([(0, 0, 0)], [(1.01, .5)], (1200, 900)),
    ([(0, 0, 0)], [(float("inf"), .5)], (1200, 900)),
    ([(0, 0, 0)], [(.5, .5)], (0, 900)),
    ([(0, 0, 0)], [(.5, .5)], (True, 900)),
    ([(0, 0, 0)]*65, [(.5, .5)]*65, (1200, 900)),
    ([(0, 0, 0)], [], (1200, 900)),
])
def test_rejects_unbounded_or_invalid_fit_input(points, uv, size):
    with pytest.raises(ValueError):
        fit_source_view(points, uv, size)


def test_observation_requires_unique_named_full_page_landmarks():
    landmark = {"instance_id": "a", "landmark_id": "stud-0-cap", "image_uv": [.2, .3]}
    valid = SourceViewObservation(step_id="step-1", landmarks=[landmark])
    assert valid.landmarks[0].landmark_id == "stud-0-cap"
    with pytest.raises(ValidationError, match="distinct"):
        SourceViewObservation(step_id="step-1", landmarks=[landmark, landmark])
    with pytest.raises(ValidationError):
        SourceViewObservation(step_id="step-1", landmarks=[{**landmark, "image_uv": [1.1, .3]}])


def test_camera_contract_rejects_scale_reflection_axes_and_nonfinite_values(source_camera):
    for patch in ({"right": [2, 0, 0]}, {"up": source_camera["right"]},
                  {"target_ldu": [float("nan"), 0, 0]}, {"vertical_span_ldu": 0},
                  {"image_size": [40, 900]}):
        with pytest.raises(ValidationError):
            SourceCamera.model_validate({**source_camera, **patch})


def test_rendered_receipt_checks_actual_projection_not_only_claimed_input():
    from copy import deepcopy
    camera = {"projection": "orthographic", "right": [1., 0., 0.], "up": [0., 1., 0.],
              "target_ldu": [0., 0., 0.], "vertical_span_ldu": 100., "image_size": [800, 600]}
    frame = {"input": camera, "viewport": {"width": 1000, "height": 800},
             "source_rect": {"x": 0, "y": 25, "width": 1000, "height": 750},
             "projection_matrix": [.015, 0, 0, 0, 0, .01875, 0, 0, 0, 0, -.01, 0, 0, 0, 0, 1],
             "matrix_world_inverse": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, -100, 1]}
    validate_rendered_source_camera(camera, frame)
    changed = deepcopy(frame)
    changed["matrix_world_inverse"][12] = 10
    with pytest.raises(ValueError, match="Actual renderer matrices"):
        validate_rendered_source_camera(camera, changed)
    changed = deepcopy(frame)
    changed["projection_matrix"][0] *= 2
    with pytest.raises(ValueError, match="Actual renderer matrices"):
        validate_rendered_source_camera(camera, changed)
    changed = deepcopy(frame)
    changed["source_rect"]["height"] = 700
    with pytest.raises(ValueError, match="aspect"):
        validate_rendered_source_camera(camera, changed)
