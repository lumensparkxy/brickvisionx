"""Offline smoke-command protocol checks; never assert live LLM wording."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from guide2build.engine.provider import ProviderFailure
from guide2build.engine.runtime import ModelCallBudgetExhausted


@pytest.fixture
def smoke(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / 'tools'))
    spec = importlib.util.spec_from_file_location('adk_smoke_under_test', root / 'tools/adk_smoke.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'load_local_environment', lambda root: None)
    monkeypatch.setenv('GOOGLE_API_KEY', 'synthetic-key-not-a-credential')
    image = tmp_path / 'page.png'
    image.write_bytes(b'synthetic image; provider is stubbed')
    monkeypatch.setattr(module, 'verified_input', lambda data, page: (
        {'sha256': 'a' * 64}, image, hashlib.sha256(image.read_bytes()).hexdigest()))
    return module


class FakeProvider:
    calls = 0

    def __init__(self, **kwargs):
        self.config = kwargs

    def call(self, prompt, images, schema, evidence):
        type(self).calls += 1
        return {'panels': [{'section': 'synthetic-main', 'number': 1, 'label': 'Synthetic panel',
                            'bbox': [0, 0, 1, 1], 'kind': 'main'}], 'uncertainty': []}


def test_smoke_reuses_hash_bound_validated_response_without_new_request(smoke, tmp_path):
    FakeProvider.calls = 0
    first = smoke.run_smoke(tmp_path, provider_factory=FakeProvider)
    second = smoke.run_smoke(tmp_path, provider_factory=FakeProvider)
    assert first['requests_reserved'] == 1 and second['reused'] is True
    assert FakeProvider.calls == 1
    assert first['automatic_reconstruction'] == 'not_run'
    assert 'synthetic-key-not-a-credential' not in ''.join(p.read_text() for p in (tmp_path / 'adk-smoke').rglob('*.json'))


def test_failed_calls_remain_charged_across_restarts_and_stop_at_three(smoke, tmp_path):
    class Unavailable(FakeProvider):
        def call(self, *args):
            raise ProviderFailure('rate_limited', 'Synthetic bounded failure')
    for _ in range(3):
        with pytest.raises(ProviderFailure, match='Synthetic'):
            smoke.run_smoke(tmp_path, provider_factory=Unavailable)
    with pytest.raises(ModelCallBudgetExhausted):
        smoke.run_smoke(tmp_path, provider_factory=Unavailable)
    checkpoint = json.loads(next((tmp_path / 'adk-smoke').rglob('checkpoint.json')).read_text())
    assert checkpoint['model_calls_used'] == 3
    assert len(checkpoint['model_requests']) == 3


def test_cancelled_invocation_does_not_reset_lifetime_budget(smoke, tmp_path):
    class Cancelled(FakeProvider):
        def call(self, *args):
            raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        smoke.run_smoke(tmp_path, provider_factory=Cancelled)
    result = smoke.run_smoke(tmp_path, provider_factory=FakeProvider)
    assert result['requests_reserved'] == 2


def test_missing_key_fails_before_budget_or_inference(smoke, monkeypatch, tmp_path):
    monkeypatch.delenv('GOOGLE_API_KEY')
    with pytest.raises(ProviderFailure) as failure:
        smoke.run_smoke(tmp_path, provider_factory=FakeProvider)
    assert failure.value.code == 'authentication_required'
    assert not (tmp_path / 'adk-smoke').exists()


def test_changed_saved_response_is_rejected_without_inference(smoke, tmp_path):
    result = smoke.run_smoke(tmp_path, provider_factory=FakeProvider)
    (Path(result['evidence']) / 'response.json').write_text('{}')
    with pytest.raises(ValueError, match='changed'):
        smoke.run_smoke(tmp_path, provider_factory=FakeProvider)


def test_invalid_panel_bounds_are_retained_as_failed_attempt(smoke, tmp_path):
    class Invalid(FakeProvider):
        def call(self, *args):
            return {'panels': [{'section': 'main', 'number': 1, 'label': 'x',
                                'bbox': [1, 0, 0, 1], 'kind': 'main'}], 'uncertainty': []}
    with pytest.raises(ValueError):
        smoke.run_smoke(tmp_path, provider_factory=Invalid)
    cp = json.loads(next((tmp_path / 'adk-smoke').rglob('checkpoint.json')).read_text())
    assert cp['model_calls_used'] == 1 and not cp.get('complete')
