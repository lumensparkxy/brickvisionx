"""Synthetic image-tolerance checks, not real-set reconstruction evidence."""
from copy import deepcopy
from math import sqrt
from types import SimpleNamespace

import pytest
from PIL import Image

from guide2build.engine.instruction import source_views_for
from guide2build.engine.quality import bind_source_view_policy, source_view_policy
from guide2build.engine.source_view import SourceViewObservation, project_source_points, fit_source_view
from guide2build.engine.store import EngineStore


def test_profiles_are_distinct_idempotent_jobs_and_invalid_profile_never_enqueues(tmp_path):
    store = EngineStore(tmp_path)
    strict = store.enqueue('30669', 'alt-02', {'quality_profile': 'strict'})
    alpha = store.enqueue('30669', 'alt-02', {'quality_profile': 'alpha'})
    assert strict['id'] != alpha['id']
    assert store.enqueue('30669', 'alt-02', {'quality_profile': 'alpha'})['id'] == alpha['id']
    for profile in ('off', '', None, True, 100):
        with pytest.raises(ValueError, match='quality_profile'):
            store.enqueue('30669', 'alt-02', {'quality_profile': profile})
    assert len(store.list()) == 2


@pytest.mark.parametrize('checkpoint', [{}, {'candidate': {'synthetic': True}}, {'panel_attempts': {'0': {'used': 3}}}])
def test_existing_job_cannot_silently_change_tolerance_or_reset_attempts(checkpoint):
    bind_source_view_policy({}, checkpoint)
    before = deepcopy(checkpoint)
    with pytest.raises(ValueError, match='new experiment revision'):
        bind_source_view_policy({'quality_profile': 'alpha'}, checkpoint)
    assert checkpoint == before


def test_legacy_checkpoint_without_policy_retains_strict_tolerance():
    checkpoint = {'panel_attempts': {'1': {'used': 2}}}
    with pytest.raises(ValueError, match='new experiment revision'):
        bind_source_view_policy({'quality_profile': 'alpha'}, checkpoint)
    assert 'source_view_policy' not in checkpoint


@pytest.fixture
def synthetic_source(tmp_path, monkeypatch):
    import guide2build.engine.connectors as connectors
    points = [(-20, 0, -10), (20, 0, -10), (-20, 0, 10), (20, 0, 10),
              (-10, 8, 20), (-10, 16, 60), (10, 8, 20), (10, 16, 40)]
    camera = {'projection': 'orthographic', 'right': [.8, 0, .6], 'up': [.3, sqrt(.75), -.4],
              'target_ldu': [5, 5, 10], 'vertical_span_ldu': 180, 'image_size': [1200, 900]}
    uv = project_source_points(camera, points)
    noisy = [(u+(8 if i % 2 else -8)/1200, v) for i, (u, v) in enumerate(uv)]
    ids = [f'synthetic-{i}' for i in range(len(points))]
    scene = SimpleNamespace(instances=[SimpleNamespace(instance_id=key, geometry_ref='synthetic') for key in ids],
        steps=[SimpleNamespace(step_id='synthetic', visible_instance_ids=ids, poses=dict(zip(ids, points, strict=True)))])
    observations = [SourceViewObservation(step_id='synthetic', landmarks=[
        {'instance_id': key, 'landmark_id': 'synthetic-tip', 'image_uv': point}
        for key, point in zip(ids, noisy, strict=True)])]
    source = tmp_path / 'source.png'
    Image.new('RGB', (1200, 900)).save(source)
    monkeypatch.setattr(connectors, 'world_landmark', lambda pose, *args: pose)
    return scene, observations, source


def test_alpha_allows_bounded_alignment_error_and_retains_strict_failure(synthetic_source, tmp_path):
    scene, observations, source = synthetic_source
    before = deepcopy(scene.steps[0].poses)
    strict, strict_cameras = source_views_for(scene, None, observations, tmp_path, source)
    alpha, alpha_cameras = source_views_for(scene, None, observations, tmp_path, source, source_view_policy('alpha'))
    assert not strict_cameras and strict['synthetic']['status'] == 'poor_fit'
    check = alpha['synthetic']
    assert 'synthetic' in alpha_cameras and check['status'] == 'fitted'
    assert 4 < check['rms_pixels'] < 8 and check['max_error_pixels'] < 12
    assert check['strict_status'] == 'poor_fit' and check['accepted_with_relaxed_tolerance']
    assert strict['synthetic']['rms_pixels'] == check['rms_pixels']
    assert scene.steps[0].poses == before


def test_alpha_retains_individual_landmark_cap(synthetic_source, tmp_path):
    scene, observations, source = synthetic_source
    # This noise is below the alpha RMS bound but above the unchanged 12 px point cap.
    for index, item in enumerate(observations[0].landmarks):
        item.image_uv = (item.image_uv[0]+(1 if index % 2 else -1)/1200, item.image_uv[1])
    fit, cameras = source_views_for(scene, None, observations, tmp_path, source, source_view_policy('alpha'))
    assert fit['synthetic']['status'] == 'poor_fit' and not cameras
    assert fit['synthetic']['rms_pixels'] < 8 and fit['synthetic']['max_error_pixels'] > 12
    assert not fit['synthetic']['accepted_with_relaxed_tolerance']


def test_alpha_does_not_choose_an_ambiguous_camera():
    points = [(-30, 0, -20), (30, 0, -20), (-30, 0, 20), (30, 0, 20), (0, 0, 0)]
    camera = {'projection': 'orthographic', 'right': [.8, 0, .6], 'up': [.3, sqrt(.75), -.4],
              'target_ldu': [5, 5, 10], 'vertical_span_ldu': 180, 'image_size': [1200, 900]}
    fit = fit_source_view(points, project_source_points(camera, points), (1200, 900), max_rms_pixels=8)
    assert fit['rms_pixels'] < .001 and fit['status'] == 'ambiguous' and fit['camera'] is None
