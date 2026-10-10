"""Deployment safety checks do not contact Google or simulate a successful deployment."""
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('cloud_tool', ROOT / 'tools/cloud.py')
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


def test_database_role_is_scoped_and_never_default(monkeypatch):
    calls = []
    monkeypatch.setattr(cloud, 'gcloud', lambda *args, **kwargs: calls.append(args))
    cloud.project_role('serviceAccount:portal', 'roles/datastore.viewer', cloud.CFG['database'])
    cloud.project_role('serviceAccount:portal', 'roles/datastore.user', cloud.CFG['request_database'])
    assert len(calls) == 2
    assert '/databases/guide2build"' in calls[0][-1]
    assert '/databases/guide2build-requests"' in calls[1][-1]
    assert all('(default)' not in str(call) for call in calls)


def test_account_gate_rejects_other_account(monkeypatch):
    monkeypatch.setattr(cloud, 'gcloud', lambda *a, **k: [{'account': 'someone@example.org', 'status': 'ACTIVE'}])
    with pytest.raises(RuntimeError, match='Sign in'):
        cloud.account_gate()


def test_rollback_restores_recorded_revision_without_deleting(monkeypatch, tmp_path):
    import json
    monkeypatch.setattr(cloud, 'EVIDENCE', tmp_path)
    monkeypatch.setattr(cloud, 'account_gate', lambda: None)
    calls = []
    monkeypatch.setattr(cloud, 'gcloud', lambda *a, **k: calls.append(a) or {})
    path = tmp_path / (cloud.CFG['public_service'] + '-before.json')
    path.write_text(json.dumps({'status': {'traffic': [{'revisionName': 'guide2build-web-00001', 'percent': 100}]}}))
    cloud.rollback()
    assert '--to-revisions=guide2build-web-00001=100' in calls[0]
    assert 'delete' not in calls[0]


def test_container_uses_public_entrypoint_and_excludes_var():
    docker = (ROOT / 'Dockerfile').read_text()
    assert 'guide2build.public:app' in docker
    assert 'guide2build.main:app' not in docker
    assert 'USER 10001' in docker
    for filename in ('.dockerignore', '.gcloudignore'):
        text = (ROOT / filename).read_text()
        assert text.startswith('**\n')
        assert '!var' not in text
        assert '!config/**' not in text


def test_absent_new_cloud_run_service_is_resumable(monkeypatch):
    from types import SimpleNamespace
    result = SimpleNamespace(returncode=1, stdout='',
        stderr='ERROR: (gcloud.run.services.describe) Cannot find service [guide2build-preview]')
    monkeypatch.setattr(cloud.subprocess, 'run', lambda *a, **k: result)
    assert cloud.gcloud('run', 'services', 'describe', 'guide2build-preview', check=False) is None
    with pytest.raises(RuntimeError):
        cloud.gcloud('run', 'services', 'describe', 'guide2build-preview')


def test_permission_denial_is_not_treated_as_missing_service(monkeypatch):
    from types import SimpleNamespace
    result = SimpleNamespace(returncode=1, stdout='', stderr='PERMISSION_DENIED: access denied')
    monkeypatch.setattr(cloud.subprocess, 'run', lambda *a, **k: result)
    with pytest.raises(RuntimeError, match='PERMISSION_DENIED'):
        cloud.gcloud('run', 'services', 'describe', 'guide2build-preview', check=False)


def service_metadata(name='guide2build-web'):
    """Synthetic provider metadata: no cloud resources are created by these tests."""
    canonical = f'https://{name}-synthetic-ew.a.run.app'
    numeric = f'https://{name}-123456.europe-west1.run.app'
    return {'metadata': {'name': name, 'annotations': {
                'run.googleapis.com/urls': json.dumps([numeric, canonical])}},
            'status': {'url': canonical, 'traffic': []}}


def test_asset_origins_include_both_aliases_and_verification_tag():
    service = service_metadata()
    tag = 'https://verify-synthetic---guide2build-web-synthetic-ew.a.run.app'
    service['status']['traffic'].append({'tag': 'verify-synthetic', 'url': tag})
    service['metadata']['annotations']['run.googleapis.com/urls'] = json.dumps([
        *json.loads(service['metadata']['annotations']['run.googleapis.com/urls']), tag])
    assert cloud.service_origins(service) == sorted([
        'https://guide2build-web-synthetic-ew.a.run.app',
        'https://guide2build-web-123456.europe-west1.run.app', tag])


@pytest.mark.parametrize('value', [
    '*', 'http://guide2build-web-synthetic-ew.a.run.app',
    'https://guide2build-web-synthetic-ew.a.run.app.evil.example',
    'https://other-service-synthetic-ew.a.run.app',
    'https://user:password@guide2build-web-synthetic-ew.a.run.app',
    'https://guide2build-web-synthetic-ew.a.run.app/path',
    'https://guide2build-web-synthetic-ew.a.run.app?origin=*',
    'https://guide2build-web-synthetic-ew.a.run.app#fragment', None])
def test_asset_origins_reject_unsafe_metadata(value):
    service = service_metadata()
    service['metadata']['annotations']['run.googleapis.com/urls'] = json.dumps([value])
    with pytest.raises(RuntimeError, match='origin'):
        cloud.service_origins(service)


@pytest.mark.parametrize('value', ['not json', '{}', 'null'])
def test_asset_origins_reject_malformed_provider_metadata(value):
    service = service_metadata()
    service['metadata']['annotations']['run.googleapis.com/urls'] = value
    with pytest.raises(RuntimeError, match='URL metadata'):
        cloud.service_origins(service)


def cors_provider(monkeypatch, tmp_path, *, owner=None, accept_update=True):
    calls = []
    bucket = {'name': cloud.CFG['assets_bucket'], 'projectNumber': owner or cloud.CFG['project_number'], 'cors': []}
    def fake_gcloud(*args, **kwargs):
        calls.append(args)
        if args[:3] == ('run', 'services', 'describe'):
            return service_metadata(args[3])
        if args[:3] == ('storage', 'buckets', 'describe'):
            assert '--raw' in args
            return dict(bucket)
        if args[:3] == ('storage', 'buckets', 'update'):
            if accept_update:
                bucket['cors'] = json.loads((tmp_path / 'cors.json').read_text())
                bucket['cors'][0]['origin'].reverse()
            return dict(bucket)
        raise AssertionError(f'Unexpected cloud mutation: {args}')
    monkeypatch.setattr(cloud, 'gcloud', fake_gcloud)
    monkeypatch.setattr(cloud, 'EVIDENCE', tmp_path)
    return calls, bucket


def test_asset_cors_updates_only_public_bucket_and_verifies_readback(monkeypatch, tmp_path):
    calls, bucket = cors_provider(monkeypatch, tmp_path)
    result = cloud.configure_asset_cors()
    assert result['changed'] is True and result['verified'] is True
    assert len(result['origins']) == 4
    assert json.loads((tmp_path / 'cors-before.json').read_text()) == []
    assert bucket['cors'][0]['method'] == ['GET', 'HEAD']
    updates = [call for call in calls if call[:3] == ('storage', 'buckets', 'update')]
    assert len(updates) == 1
    assert updates[0][3] == 'gs://' + cloud.CFG['assets_bucket']
    calls.clear()
    assert cloud.configure_asset_cors()['changed'] is False
    assert not any(call[:3] == ('storage', 'buckets', 'update') for call in calls)


def test_asset_cors_rejects_different_bucket_owner(monkeypatch, tmp_path):
    calls, _ = cors_provider(monkeypatch, tmp_path, owner='other-project')
    with pytest.raises(RuntimeError, match='not owned'):
        cloud.configure_asset_cors()
    assert not any(call[:3] == ('storage', 'buckets', 'update') for call in calls)


def test_asset_cors_refuses_metadata_without_bucket_owner(monkeypatch, tmp_path):
    calls, bucket = cors_provider(monkeypatch, tmp_path)
    del bucket['projectNumber']
    with pytest.raises(RuntimeError, match='not owned'):
        cloud.configure_asset_cors()
    assert not any(call[:3] == ('storage', 'buckets', 'update') for call in calls)


def test_asset_cors_does_not_claim_success_without_provider_readback(monkeypatch, tmp_path):
    cors_provider(monkeypatch, tmp_path, accept_update=False)
    with pytest.raises(RuntimeError, match='could not be verified'):
        cloud.configure_asset_cors()
    assert not (tmp_path / 'cors-readback.json').exists()


def test_deploy_configures_asset_origins_before_tag_smoke_and_traffic(monkeypatch, tmp_path):
    from types import SimpleNamespace
    revision = 'a' * 40
    image = f'{cloud.CFG["region"]}-docker.pkg.dev/{cloud.CFG["project"]}/{cloud.CFG["repository"]}/web:{revision}'
    services = {name: service_metadata(name) for name in (cloud.CFG['public_service'], cloud.CFG['preview_service'])}
    calls = []
    def fake_gcloud(*args, **kwargs):
        calls.append(args)
        if args[:2] == ('builds', 'describe'):
            return {'status': 'SUCCESS', 'substitutions': {'_IMAGE': image},
                    'results': {'images': [{'name': image, 'digest': 'sha256:' + 'b' * 64}]}}
        if args[:3] == ('run', 'services', 'describe'):
            return services[args[3]]
        if args[:2] == ('run', 'deploy'):
            service = services[args[2]]
            service['status']['latestReadyRevisionName'] = args[2] + '-synthetic-revision'
            if args[2] == cloud.CFG['public_service']:
                tag = 'verify-' + revision[:12]
                service['status']['traffic'] = [{'tag': tag, 'url':
                    f'https://{tag}---{args[2]}-synthetic-ew.a.run.app'}]
            return service
        if args[:3] in (('run', 'services', 'add-iam-policy-binding'), ('run', 'services', 'update-traffic')):
            return {}
        raise AssertionError(f'Unexpected provider operation: {args}')
    monkeypatch.setattr(cloud, 'EVIDENCE', tmp_path)
    monkeypatch.setattr(cloud, 'account_gate', lambda: None)
    monkeypatch.setattr(cloud, 'gcloud', fake_gcloud)
    monkeypatch.setattr(cloud.subprocess, 'check_output', lambda command, **kwargs:
                        '' if 'status' in command or 'diff' in command else revision)
    monkeypatch.setattr(cloud.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout='synthetic-token'))
    monkeypatch.setattr(cloud, 'configure_asset_cors', lambda: calls.append(('cors',)))
    monkeypatch.setattr(cloud, 'smoke', lambda base, token=None: calls.append(('smoke', base)))
    cloud.deploy(build_id='synthetic-build')
    public_deploy = next(i for i, call in enumerate(calls) if call[:3] == ('run', 'deploy', cloud.CFG['public_service']))
    cors = next(i for i in range(public_deploy + 1, len(calls)) if calls[i] == ('cors',))
    tag_smoke = next(i for i, call in enumerate(calls) if call[0] == 'smoke' and '---' in call[1])
    traffic = next(i for i, call in enumerate(calls) if call[:3] == ('run', 'services', 'update-traffic'))
    assert public_deploy < cors < tag_smoke < traffic
