"""Caller admits only existing checkpoint page bindings; no provider call is used."""
import copy
import hashlib
import json
import os
import stat

import pytest

from guide2build.engine import exploration, runner
from guide2build.engine.store import EngineStore
from guide2build.catalog import find_guide
from guide2build import source


HASH = 'a' * 64


def bound_checkpoint():
    return {'source_sha256': HASH, 'page_count': 8,
            'exploration_source_pages': [{'page_index': i, 'sha256': str(i) * 64,
                                           'width': 64, 'height': 64} for i in range(8)],
            'model_calls_used': 7, 'local_model_calls_used': 7}


@pytest.mark.parametrize('policy,bindings_present', [('explore', True), ('explore', False), ('strict', True)])
def test_runner_proof_uses_only_preexisting_checkpoint_fields(policy, bindings_present):
    job, cp = {'config': {'execution_policy': policy}}, bound_checkpoint()
    if not bindings_present:
        cp.pop('exploration_source_pages')
    before = copy.deepcopy(cp)
    proof = runner._trusted_exploration_pages(job, cp, HASH, 8)
    assert cp == before
    if policy == 'explore' and bindings_present:
        assert proof == {'source_sha256': HASH, 'page_count': 8, 'pages': cp['exploration_source_pages']}
        assert set(proof) == {'source_sha256', 'page_count', 'pages'}
    else:
        assert proof is None


@pytest.mark.parametrize('field,value', [('source_sha256', 'b' * 64), ('source_sha256', None),
                                       ('page_count', 7), ('page_count', None), ('page_count', True)])
def test_source_or_count_drift_cannot_be_backfilled_into_a_proof(field, value):
    cp = bound_checkpoint()
    cp[field] = value
    with pytest.raises(ValueError, match='selected source'):
        runner._trusted_exploration_pages({'config': {'execution_policy': 'explore'}}, cp, HASH, 8)


@pytest.mark.parametrize('resuming', [True, False])
def test_actual_runner_handoff_preserves_source_images_and_budget(tmp_path, monkeypatch, resuming):
    store = EngineStore(tmp_path)
    config = {'model': 'gemini-3.8-flash', 'thinking_level': 'high', 'execution_policy': 'explore',
              'max_model_calls': 100, 'max_panel_attempts': 2}
    job = store.enqueue('30669', 'alt-02', config)
    original = bound_checkpoint() if resuming else {}
    store.claim('seed', job_id=job['id'])
    store.checkpoint(job['id'], 'seed', original, 'blocked')
    store.retry(job['id'])
    monkeypatch.setattr(runner, 'cached_receipt', lambda *a: {'sha256': HASH})
    monkeypatch.setattr(runner, 'checkpoint_source_receipt', lambda *a, **k: {'sha256': HASH})
    observed = []
    def render(pdf, output, **kwargs):
        assert kwargs['expected_sha256'] == HASH
        assert str(output).endswith('/public/pages/' + HASH)
        assert ('trusted_page_bindings' in kwargs) is resuming
        if resuming:
            assert kwargs['trusted_page_bindings'] == {
                'source_sha256': HASH, 'page_count': 8, 'pages': original['exploration_source_pages']}
        observed.append('source')
        return [{}] * 8
    monkeypatch.setattr(runner, 'render_pages', render)
    def stop_after_source(**kwargs):
        cp, config = kwargs['checkpoint'], kwargs['job']['config']
        assert cp['source_sha256'] == HASH and cp['page_count'] == 8
        assert config['model'] == 'gemini-3.8-flash' and config['thinking_level'] == 'high'
        assert config['max_model_calls'] == 100 and config['max_panel_attempts'] == 2
        assert cp.get('model_calls_used', 0) == cp.get('local_model_calls_used', 0) == (7 if resuming else 0)
        if resuming:
            assert cp['exploration_source_pages'] == original['exploration_source_pages']
        observed.append('exploration')
        return True
    monkeypatch.setattr(exploration, 'run_exploration', stop_after_source)
    class NoProvider:
        def call(self, *a, **k):
            pytest.fail('This source handoff test does not invoke inference')
    assert runner.run_once(store, NoProvider(), job_id=job['id'])
    assert observed == ['source', 'exploration']


def test_actual_runner_does_not_enroll_unbound_page_cache(tmp_path, monkeypatch):
    store = EngineStore(tmp_path)
    job = store.enqueue('30669', 'alt-02', {'model': 'test', 'execution_policy': 'explore'})
    cp = bound_checkpoint()
    cp.pop('source_sha256')
    store.claim('seed', job_id=job['id'])
    store.checkpoint(job['id'], 'seed', cp, 'blocked')
    store.retry(job['id'])
    monkeypatch.setattr(runner, 'cached_receipt', lambda *a: {'sha256': HASH})
    def forbidden(*a, **k):
        pytest.fail('A cache without the original checkpoint source identity must stop before rendering')
    monkeypatch.setattr(runner, 'render_pages', forbidden)
    assert runner.run_once(store, object(), job_id=job['id'])
    result = store.get(job['id'])
    assert result['state'] == 'blocked' and 'proof' in result['error']['message']
    assert result['checkpoint']['model_calls_used'] == 7
    assert 'source_sha256' not in result['checkpoint']


def source_bound_job(tmp_path):
    """Synthetic receipt/identity for caller-boundary tests; never passed to PDFium."""
    store = EngineStore(tmp_path)
    job = store.enqueue('30669', 'alt-02', {'model': 'test', 'execution_policy': 'explore'})
    pdf = tmp_path / 'sources/30669/alt-02/source.pdf'
    pdf.parent.mkdir(parents=True)
    payload = b'%PDF-1.7\nsynthetic caller identity: no model or rendering\n'
    pdf.write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()
    url = find_guide('30669', 'alt-02')['pdf_url']
    receipt = {'requested_url': url, 'resolved_url': url, 'sha256': sha, 'size_bytes': len(payload),
               'downloaded_at': '2026-10-05T00:00:00Z'}
    pdf.with_suffix('.receipt.json').write_text(json.dumps(receipt))
    cp = bound_checkpoint()
    cp['source_sha256'] = sha
    store.claim('seed', job_id=job['id'])
    store.checkpoint(job['id'], 'seed', cp, 'blocked')
    store.retry(job['id'])
    return store, job, pdf


def source_state(root):
    result = {}
    for path in root.rglob('*'):
        info = path.lstat()
        if stat.S_ISREG(info.st_mode):
            result[str(path.relative_to(root))] = path.read_bytes()
        elif not stat.S_ISDIR(info.st_mode):
            result[str(path.relative_to(root))] = {'mode': info.st_mode, 'inode': info.st_ino}
    return result


@pytest.mark.parametrize('mutation', ['missing_pdf', 'corrupt_same_size_pdf', 'missing_receipt', 'wrong_hash',
                                    'wrong_size', 'wrong_url', 'unsafe_resolved_url', 'invalid_timestamp',
                                    'extra_field', 'duplicate_key', 'invalid_json', 'oversized_receipt',
                                    'pdf_symlink', 'receipt_symlink', 'directory_receipt', 'fifo_pdf', 'fifo_receipt'])
def test_actual_runner_rejects_proof_bound_source_before_legacy_cache_or_download(tmp_path, monkeypatch, mutation):
    store, job, pdf = source_bound_job(tmp_path)
    receipt_path = pdf.with_suffix('.receipt.json')
    receipt = json.loads(receipt_path.read_text())
    if mutation == 'missing_pdf':
        pdf.unlink()
    elif mutation == 'corrupt_same_size_pdf':
        pdf.write_bytes(pdf.read_bytes().replace(b'caller', b'splice'))
    elif mutation == 'missing_receipt':
        receipt_path.unlink()
    elif mutation in {'pdf_symlink', 'receipt_symlink'}:
        target = pdf if mutation == 'pdf_symlink' else receipt_path
        other = target.with_name(target.name + '.saved')
        target.rename(other)
        target.symlink_to(other)
    elif mutation in {'directory_receipt', 'fifo_pdf', 'fifo_receipt'}:
        target = pdf if mutation == 'fifo_pdf' else receipt_path
        target.unlink()
        target.mkdir() if mutation == 'directory_receipt' else os.mkfifo(target)
    else:
        if mutation == 'wrong_hash':
            receipt['sha256'] = 'f' * 64
        elif mutation == 'wrong_size':
            receipt['size_bytes'] += 1
        elif mutation == 'wrong_url':
            receipt['requested_url'] = 'https://www.lego.com/cdn/product-assets/different.pdf'
        elif mutation == 'unsafe_resolved_url':
            receipt['resolved_url'] = 'https://untrusted.invalid/source.pdf'
        elif mutation == 'invalid_timestamp':
            receipt['downloaded_at'] = 'not-a-date'
        elif mutation == 'extra_field':
            receipt['unexpected'] = 'must not be silently dropped'
        text = json.dumps(receipt)
        if mutation == 'duplicate_key':
            text = text[:-1] + ', "size_bytes": ' + str(receipt['size_bytes']) + '}'
        elif mutation == 'invalid_json':
            text = '{invalid'
        elif mutation == 'oversized_receipt':
            text += ' ' * (64 * 1024)
        receipt_path.write_text(text)
    before = source_state(pdf.parent)
    legacy, downloads, renders, providers = [], [], [], []
    actual_cache = runner.cached_receipt
    def tracked_cache(*args):
        legacy.append(True)
        return actual_cache(*args)
    def download(*args, **kwargs):
        downloads.append(True)
        raise AssertionError('No network in this boundary test')
    def render(*args, **kwargs):
        renders.append(True)
        raise AssertionError('Invalid bound source must stop before render')
    class NoProvider:
        def call(self, *args, **kwargs):
            providers.append(True)
            raise AssertionError('No inference in this boundary test')
    monkeypatch.setattr(runner, 'cached_receipt', tracked_cache)
    monkeypatch.setattr(runner, 'download_pdf', download)
    monkeypatch.setattr(runner, 'render_pages', render)
    assert runner.run_once(store, NoProvider(), job_id=job['id'])
    result = store.get(job['id'])
    assert result['state'] == 'blocked'
    assert not legacy and not downloads and not renders and not providers
    assert result['checkpoint']['model_calls_used'] == result['checkpoint']['local_model_calls_used'] == 7
    assert source_state(pdf.parent) == before


@pytest.mark.parametrize('name', ['source.pdf', 'source.receipt.json'])
def test_actual_runner_descriptor_source_entry_rejects_fifo_substitution(tmp_path, monkeypatch, name):
    store, job, pdf = source_bound_job(tmp_path)
    target = pdf if name == 'source.pdf' else pdf.with_suffix('.receipt.json')
    real_open = source.os.open
    swapped = False
    def race(path, flags, *args, **kwargs):
        nonlocal swapped
        if str(path) == name and not swapped:
            assert flags & os.O_NONBLOCK and flags & os.O_NOFOLLOW
            swapped = True
            target.unlink()
            os.mkfifo(target)
        return real_open(path, flags, *args, **kwargs)
    def forbidden(*a, **k):
        pytest.fail('Proof-bound source must not fall back to legacy cache, download or render')
    monkeypatch.setattr(source.os, 'open', race)
    monkeypatch.setattr(runner, 'cached_receipt', forbidden)
    monkeypatch.setattr(runner, 'download_pdf', forbidden)
    monkeypatch.setattr(runner, 'render_pages', forbidden)
    assert runner.run_once(store, object(), job_id=job['id'])
    result = store.get(job['id'])
    assert swapped and result['state'] == 'blocked' and 'regular file leaves' in result['error']['message']
    assert result['checkpoint']['model_calls_used'] == 7


def test_no_proof_still_uses_existing_cache_and_download_path(tmp_path, monkeypatch):
    store = EngineStore(tmp_path)
    job = store.enqueue('30669', 'alt-02', {'model': 'test', 'execution_policy': 'explore'})
    calls = []
    actual_cache = runner.cached_receipt
    def cached(*args):
        calls.append('legacy_cache')
        return actual_cache(*args)
    def download(*args, **kwargs):
        calls.append('legacy_download')
        raise ValueError('Synthetic stopped download; no network')
    monkeypatch.setattr(runner, 'cached_receipt', cached)
    monkeypatch.setattr(runner, 'download_pdf', download)
    assert runner.run_once(store, object(), job_id=job['id'])
    assert calls == ['legacy_cache', 'legacy_download']


@pytest.mark.parametrize('failure', ['missing_receipt', 'malformed_receipt', 'fifo_receipt', 'fifo_pdf'])
def test_receipt_admission_closes_all_descriptors_before_or_after_yield(tmp_path, monkeypatch, failure):
    from collections import Counter
    _, _, pdf = source_bound_job(tmp_path)
    receipt = pdf.with_suffix('.receipt.json')
    expected = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if failure in {'missing_receipt', 'fifo_receipt', 'fifo_pdf'}:
        target = pdf if failure == 'fifo_pdf' else receipt
        target.unlink()
        if failure != 'missing_receipt':
            os.mkfifo(target)
    else:
        receipt.write_text('{invalid')
    opened, closed = [], []
    actual_open, actual_close = source.os.open, source.os.close
    def track_open(*args, **kwargs):
        fd = actual_open(*args, **kwargs)
        opened.append(fd)
        return fd
    def track_close(fd):
        closed.append(fd)
        return actual_close(fd)
    monkeypatch.setattr(source.os, 'open', track_open)
    monkeypatch.setattr(source.os, 'close', track_close)
    with pytest.raises((ValueError, OSError)):
        source.checkpoint_source_receipt(pdf, find_guide('30669', 'alt-02')['pdf_url'], expected)
    assert opened and Counter(opened) == Counter(closed)


@pytest.mark.parametrize('target_name', ['source.pdf', 'source.receipt.json'])
def test_receipt_admission_final_fence_rechecks_both_inputs(tmp_path, monkeypatch, target_name):
    _, _, pdf = source_bound_job(tmp_path)
    expected = hashlib.sha256(pdf.read_bytes()).hexdigest()
    target = pdf if target_name == 'source.pdf' else pdf.with_suffix('.receipt.json')
    actual = source._cache_read
    mutated = False
    def read_then_change(path, *args, **kwargs):
        nonlocal mutated
        result = actual(path, *args, **kwargs)
        if path == pdf and not mutated:
            mutated = True
            old = target.stat()
            target.write_bytes(target.read_bytes() + b'changed after first hashes')
            os.utime(target, ns=(old.st_atime_ns, old.st_mtime_ns))
        return result
    monkeypatch.setattr(source, '_cache_read', read_then_change)
    with pytest.raises(ValueError, match='changed'):
        source.checkpoint_source_receipt(pdf, find_guide('30669', 'alt-02')['pdf_url'], expected)
    assert mutated
