"""Control-flow fixtures are synthetic and never target-set assembly evidence."""
import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from PIL import Image

from guide2build.core.models import SceneManifest
from guide2build.engine.instruction import build_instruction, SequenceEvidence, validate_sequence
from guide2build.engine.runner import atomic_json, validate_candidate
from guide2build.releases.models import adapt_v1, SceneV2, digest


@pytest.fixture
def harness(tmp_path, monkeypatch, scene_data):
    import guide2build.engine.geometry as geometry
    import guide2build.engine.spatial as spatial
    import guide2build.engine.rendering as rendering
    import guide2build.engine.instruction as instruction
    scene_data.update(set_number='30669', guide_id='alt-02')
    for part in scene_data['instances']:
        part['origin'] = 'vision_proposal'
    scene = adapt_v1(SceneManifest.model_validate(scene_data),
                     'https://www.lego.com/en-us/service/building-instructions/30669', 8)
    previous = scene.model_dump(mode='json')
    previous['steps'] = previous['steps'][:1]
    previous['instances'] = previous['instances'][:1]
    step = scene.steps[1].model_dump(mode='json')
    step.update(action='add_parts', assembly_group_id=None)
    delta = {'new_sections': [], 'new_instances': [scene.instances[1].model_dump(mode='json')], 'new_steps': [step]}
    proposal = {'delta_json': json.dumps(delta), 'blockers': [], 'observations': ['Synthetic only'],
        'connections': [], 'roots': [],
        'sequence': [{'step_id': step['step_id'], 'kind': 'printed_main', 'printed_label': '2',
                      'bbox': [0,0,1,1], 'explanation': 'Synthetic control flow only'}],
        'source_views': [{'step_id': step['step_id'], 'view_family': 'unconstrained', 'landmarks': []}]}
    pages = tmp_path / 'pages'
    pages.mkdir()
    Image.new('RGB', (64,64), 'white').save(pages / 'page-000.png')
    directory = tmp_path / 'job'
    directory.mkdir()
    checkpoint = {}
    events = []
    monkeypatch.setattr(geometry, 'prepare_geometry', lambda *args: {'synthetic': True})
    monkeypatch.setattr(spatial, 'solve_candidate', lambda scene, *args: (scene, {'synthetic': True}))
    monkeypatch.setattr(instruction, 'source_views_for', lambda scene, *args:
                        ({'s2': {'status': 'fitted'}}, {'s2': {}}))
    def render(path, geometry, output, **kwargs):
        output.mkdir()
        (output / 'frame.png').write_bytes(b'synthetic pixels')
        report = {'scene_sha256': digest(SceneV2.model_validate_json(path.read_text())),
                  'steps': [{'step_id': 's2', 'screenshot': 'frame.png',
                             'png_sha256': hashlib.sha256(b'synthetic pixels').hexdigest()}]}
        atomic_json(output / 'report.json', report)
        return report
    monkeypatch.setattr(rendering, 'render_candidate', render)
    calls = []
    reviews = []
    snapshot_stages = set()
    def infer(stage, prompt, images, model, heartbeat):
        calls.append((stage, prompt))
        if stage.startswith('construct'):
            return model.model_validate(proposal)
        return model.model_validate(reviews.pop(0) if reviews else
                                    {'coverage_agrees': True, 'assembly_agrees': True, 'findings': []})
    def save(stage, state='constructing', error=None):
        events.append((stage, state, error, deepcopy(checkpoint) if stage in snapshot_stages else None))
    args = dict(job={'id': 'synthetic', 'set_number': '30669', 'guide_id': 'alt-02',
                     'config': {'max_panel_attempts': 2}}, previous=previous, ordinal=1,
                panel={'number': 2}, page_index=0, page_count=8, source_hash=scene.source_sha256,
                directory=directory, pages_dir=pages, geometry_root=tmp_path / 'geometry', prompt='Test only',
                images=[pages / 'page-000.png'], checkpoint=checkpoint, save=save, infer=infer,
                heartbeat=SimpleNamespace(check=lambda: None), validate_candidate=validate_candidate,
                atomic_json=atomic_json)
    return SimpleNamespace(args=args, calls=calls, reviews=reviews, proposal=proposal, events=events,
                           snapshot_stages=snapshot_stages)


@pytest.mark.parametrize('profile', ['strict', 'alpha'])
def test_targeted_repair_preserves_prefix_and_retains_rejected_evidence(harness, profile):
    h = harness
    h.args['job']['config']['quality_profile'] = profile
    previous = deepcopy(h.args['previous'])
    h.reviews.append({'coverage_agrees': True, 'assembly_agrees': False, 'findings': [
        {'category': 'side', 'step_ids': ['s2'], 'instance_ids': ['b'],
         'description': 'Attachment is on the wrong side', 'correction': 'Use the source-indicated side'}]})
    scene, record = build_instruction(**h.args)
    assert scene.steps[0].model_dump(mode='json') == previous['steps'][0]
    assert h.args['previous'] == previous
    assert record['attempt'] == 2 and h.args['checkpoint']['panel_attempts']['1']['used'] == 2
    construction = [prompt for stage, prompt in h.calls if stage.startswith('construct')]
    assert len(construction) == 2 and 'Attachment is on the wrong side' in construction[1]
    assert 'rejected_proposal' in construction[1]
    outcomes = [json.loads(path.read_text()) for path in h.args['directory'].glob('proposals/*/outcome.json')]
    assert {item['status'] for item in outcomes} == {'accepted_by_pipeline', 'rejected'}
    assert not (h.args['directory'] / 'scene.json').exists()  # Only outer runner may promote.


def test_exhausted_source_repairs_do_not_run_again(harness):
    h = harness
    h.proposal.update(delta_json=None, blockers=['Unsupported source contact'])
    assert build_instruction(**h.args) is None
    assert len(h.calls) == 2
    assert h.events[-1][2]['code'] == 'instruction_repair_exhausted'
    assert build_instruction(**h.args) is None
    assert len(h.calls) == 2


def test_reviewed_last_attempt_recovers_without_new_model_calls(harness):
    h = harness
    h.snapshot_stages.add('instruction_reviewed')
    h.args['job']['config']['max_panel_attempts'] = 1
    original_save = h.args['save']
    class Crash(BaseException):
        pass
    def crash_after_persist(stage, *args):
        original_save(stage, *args)
        if stage == 'instruction_reviewed':
            raise Crash()
    h.args['save'] = crash_after_persist
    with pytest.raises(Crash):
        build_instruction(**h.args)
    assert h.events[-1][3]['panel_attempts']['1']['accepted']
    h.args['checkpoint'] = deepcopy(h.events[-1][3])
    h.args['save'] = original_save
    before = len(h.calls)
    scene, record = build_instruction(**h.args)
    assert scene.steps[-1].step_id == 's2' and record['attempt'] == 1
    assert len(h.calls) == before
    frame = next(h.args['directory'].glob('proposals/*/renders/frame.png'))
    frame.write_bytes(b'tampered pixels')
    with pytest.raises(ValueError, match='evidence changed'):
        build_instruction(**h.args)
    assert len(h.calls) == before


def test_recovery_binds_prior_history_and_source_pixels(harness):
    h = harness
    build_instruction(**h.args)
    h.args['previous'] = deepcopy(h.args['previous'])
    h.args['previous']['revision'] = 'changed-history'
    with pytest.raises(ValueError, match='source/history'):
        build_instruction(**h.args)
    h.args['previous']['revision'] = 'fixture-r1'
    (h.args['pages_dir'] / 'page-000.png').write_bytes(b'changed-page')
    with pytest.raises(ValueError, match='source page changed'):
        build_instruction(**h.args)


def test_sequence_rejects_invented_splits_and_mismatched_callout_labels(scene_data):
    scene = adapt_v1(SceneManifest.model_validate(scene_data),
                     'https://www.lego.com/en-us/service/building-instructions/30669', 8)
    evidence = [SequenceEvidence(step_id=s.step_id, kind='printed_main', printed_label=str(s.main_step_number),
                                  bbox=(0,0,1,1), explanation='Test') for s in scene.steps]
    with pytest.raises(ValueError, match='one snapshot'):
        validate_sequence(scene, None, evidence)
    previous = scene.model_dump(mode='json')
    previous['steps'] = previous['steps'][:1]
    trimmed = scene.model_copy(deep=True)
    trimmed.steps = trimmed.steps[:2]
    trimmed.steps[-1].substep_label = '9'
    evidence = [SequenceEvidence(step_id='s2', kind='numbered_callout', printed_label='1', bbox=(0,0,1,1), explanation='Test')]
    with pytest.raises(ValueError, match='label must equal'):
        validate_sequence(trimmed, previous, evidence)


def test_alpha_recovery_receipt_binds_tolerance_and_records_strict_outcome(harness, monkeypatch):
    import guide2build.engine.instruction as instruction
    h = harness
    h.args['job']['config']['quality_profile'] = 'alpha'
    seen = []
    def fitted(scene, previous, observations, geometry, source, policy):
        seen.append(policy)
        return {'s2': {'status': 'fitted', 'rms_pixels': 7.7, 'max_error_pixels': 9.8,
                       'strict_status': 'poor_fit', 'accepted_with_relaxed_tolerance': True}}, {'s2': {}}
    monkeypatch.setattr(instruction, 'source_views_for', fitted)
    scene, record = build_instruction(**h.args)
    assert seen[0]['profile'] == 'alpha' and seen[0]['max_rms_pixels'] == 8
    assert record['source_view_checks']['s2']['accepted_with_relaxed_tolerance']
    accepted = h.args['checkpoint']['panel_attempts']['1']['accepted']
    assert accepted['source_view_policy'] == seen[0]
    before = len(h.calls)
    assert build_instruction(**h.args)[0] == scene
    assert len(h.calls) == before
    accepted['source_view_policy'] = {**accepted['source_view_policy'], 'max_rms_pixels': 99}
    with pytest.raises(ValueError, match='different image tolerance'):
        build_instruction(**h.args)
    assert len(h.calls) == before


def test_alpha_does_not_bypass_connection_failure(harness, monkeypatch):
    import guide2build.engine.spatial as spatial
    h = harness
    h.args['job']['config']['quality_profile'] = 'alpha'
    def invalid(*args):
        raise ValueError('Occupied connection; synthetic invalid attachment')
    monkeypatch.setattr(spatial, 'solve_candidate', invalid)
    assert build_instruction(**h.args) is None
    assert len(h.calls) == 2 and all(stage.startswith('construct') for stage, _ in h.calls)
    assert 'Occupied connection' in h.events[-1][2]['message']
    assert 'accepted' not in h.args['checkpoint']['panel_attempts']['1']
