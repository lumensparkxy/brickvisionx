"""Lossless source reuse requires private checkpoint pixels, not cache assertions."""
import copy
import hashlib
import json

import pytest
from PIL import Image

from guide2build import source


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_bytes(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob('*') if path.is_file()}


def write_json(path, value):
    path.write_text(json.dumps(value))


@pytest.fixture
def cache(tmp_path):
    """Actual PNGs plus a caller-trusted synthetic source/cache, no model output."""
    pdf = tmp_path / 'source.pdf'
    images = [Image.new('RGB', (24, 18), colour) for colour in ('white', 'red', 'blue')]
    images[0].save(pdf, 'PDF', save_all=True, append_images=images[1:])
    output = tmp_path / 'pages'
    output.mkdir()
    (output / '.render.lock').touch()
    renderer = f"pypdfium2/{source.version('pypdfium2')}"
    records, bindings = [], []
    for index, image in enumerate(images):
        path = output / f'page-{index:03d}.png'
        image.save(path)
        records.append({'page_index': index, 'file': path.name, 'width_px': image.width,
                        'height_px': image.height, 'sha256': sha(path), 'size_bytes': path.stat().st_size,
                        'renderer': renderer, 'scale': 1.5,
                        'coordinate_origin': 'top_left_after_page_rotation'})
        bindings.append({'page_index': index, 'sha256': sha(path), 'width': image.width, 'height': image.height})
    identity = {'version': 2, 'source_sha256': sha(pdf), 'renderer': renderer, 'scale': 1.5,
                'batch_pages': source.BATCH_PAGES, 'batch_pixels': source.BATCH_PIXELS}
    write_json(output / 'pages.json', records)
    write_json(output / 'resume.json', {'identity': identity, 'page_count': len(records), 'batches': {'0': records}})
    return pdf, output, {'source_sha256': sha(pdf), 'page_count': len(records), 'pages': bindings}, records


def reuse(cache, **kwargs):
    pdf, output, proof, _ = cache
    return source.render_pages(pdf, output, expected_sha256=proof['source_sha256'],
                               trusted_page_bindings=proof, **kwargs)


def no_worker(*args, **kwargs):
    pytest.fail('A supplied trusted proof must never silently repair or rerender mismatches')


def test_complete_checkpoint_pixels_skip_snapshot_and_pdf_worker_without_rewriting(cache, monkeypatch):
    pdf, output, proof, records = cache
    before, old_proof = tree_bytes(pdf.parent), copy.deepcopy(proof)
    monkeypatch.setattr(source, '_child', no_worker)
    monkeypatch.setattr(source, '_snapshot_pdf', no_worker)
    progress = []
    assert reuse(cache, on_progress=lambda a, b: progress.append((a, b))) == records
    assert progress == [(3, 3)] and proof == old_proof
    assert tree_bytes(pdf.parent) == before
    assert not list(pdf.parent.glob('.render-*'))


def test_actual_pdf_render_then_trusted_reuse_returns_identical_records(tmp_path, monkeypatch):
    pdf, output = tmp_path / 'source.pdf', tmp_path / 'pages'
    Image.new('RGB', (24, 18), 'green').save(pdf, 'PDF')
    records = source.render_pages(pdf, output, expected_sha256=sha(pdf))
    proof = {'source_sha256': sha(pdf), 'page_count': 1, 'pages': [
        {'page_index': r['page_index'], 'sha256': r['sha256'], 'width': r['width_px'], 'height': r['height_px']}
        for r in records]}
    before = tree_bytes(tmp_path)
    monkeypatch.setattr(source, '_child', no_worker)
    assert source.render_pages(pdf, output, expected_sha256=sha(pdf), trusted_page_bindings=proof) == records
    assert tree_bytes(tmp_path) == before


@pytest.mark.parametrize('mutation', ['pdf', 'png', 'png_metadata_rehashed', 'manifest_disagreement',
                                    'missing_png', 'missing_manifest', 'missing_batch', 'unexpected_page',
                                    'wrong_dimensions', 'invalid_png', 'wrong_origin', 'wrong_filename',
                                    'forged_source', 'renderer', 'scale', 'duplicate_key', 'nonfinite'])
def test_tamper_or_untrusted_metadata_fails_closed(cache, monkeypatch, mutation):
    pdf, output, proof, records = cache
    resume = json.loads((output / 'resume.json').read_text())
    if mutation == 'pdf':
        pdf.write_bytes(b'%PDF-replaced')
    elif mutation in {'png', 'png_metadata_rehashed'}:
        Image.new('RGB', (24, 18), 'black').save(output / 'page-000.png')
        if mutation == 'png_metadata_rehashed':
            records[0]['sha256'] = sha(output / 'page-000.png')
            records[0]['size_bytes'] = (output / 'page-000.png').stat().st_size
    elif mutation == 'manifest_disagreement':
        resume['batches']['0'][0]['sha256'] = 'f' * 64
    elif mutation == 'missing_png':
        (output / 'page-001.png').unlink()
    elif mutation == 'missing_manifest':
        (output / 'pages.json').unlink()
    elif mutation == 'missing_batch':
        resume['batches'] = {}
    elif mutation == 'unexpected_page':
        (output / 'page-999.png').write_bytes((output / 'page-000.png').read_bytes())
    elif mutation == 'wrong_dimensions':
        # Even a caller-supplied (invalid) hash/dimension claim must match actual PNG dimensions.
        records[0]['width_px'] = proof['pages'][0]['width'] = 25
    elif mutation == 'invalid_png':
        raw = (output / 'page-000.png').read_bytes()
        (output / 'page-000.png').write_bytes(raw[:-10])
        records[0]['sha256'] = proof['pages'][0]['sha256'] = sha(output / 'page-000.png')
        records[0]['size_bytes'] = (output / 'page-000.png').stat().st_size
    elif mutation == 'wrong_origin':
        records[0]['coordinate_origin'] = 'bottom_left'
    elif mutation == 'wrong_filename':
        records[0]['file'] = '../other.png'
    elif mutation == 'forged_source':
        resume['identity']['source_sha256'] = 'e' * 64
    elif mutation in {'renderer', 'scale'}:
        resume['identity'][mutation] = 'pypdfium2/forged' if mutation == 'renderer' else 2
    if mutation not in {'manifest_disagreement', 'missing_batch'}:
        resume['batches']['0'] = records
    if mutation != 'missing_manifest':
        write_json(output / 'pages.json', records)
    write_json(output / 'resume.json', resume)
    if mutation == 'duplicate_key':
        text = (output / 'resume.json').read_text().replace('"page_count": 3', '"page_count": 3, "page_count": 3')
        (output / 'resume.json').write_text(text)
    elif mutation == 'nonfinite':
        text = (output / 'resume.json').read_text().replace('"scale": 1.5', '"scale": NaN')
        (output / 'resume.json').write_text(text)
    before = tree_bytes(pdf.parent)
    monkeypatch.setattr(source, '_child', no_worker)
    with pytest.raises((ValueError, OSError, SyntaxError)):
        reuse(cache)
    assert tree_bytes(pdf.parent) == before


@pytest.mark.parametrize('mutation', ['absent_source', 'source', 'count', 'incomplete', 'order', 'duplicate',
                                    'bool_index', 'bool_size', 'oversized_dimension', 'extra_field'])
def test_invalid_proof_is_not_repaired_or_promoted(cache, monkeypatch, mutation):
    _, _, proof, _ = cache
    if mutation == 'absent_source':
        proof.pop('source_sha256')
        with pytest.raises(ValueError, match='malformed'):
            source.render_pages(cache[0], cache[1], expected_sha256=sha(cache[0]), trusted_page_bindings=proof)
        return
    if mutation == 'source':
        proof['source_sha256'] = 'f' * 64
    elif mutation == 'count':
        proof['page_count'] = 2
    elif mutation == 'incomplete':
        proof['pages'].pop()
    elif mutation == 'order':
        proof['pages'].reverse()
    elif mutation == 'duplicate':
        proof['pages'][1] = copy.deepcopy(proof['pages'][0])
    elif mutation == 'bool_index':
        proof['pages'][0]['page_index'] = False
    elif mutation == 'bool_size':
        proof['pages'][0]['width'] = True
    elif mutation == 'oversized_dimension':
        proof['pages'][0]['width'] = source.PAGE_PIXELS
    else:
        proof['pages'][0]['renderer'] = 'not_checkpoint_evidence'
    monkeypatch.setattr(source, '_child', no_worker)
    with pytest.raises(ValueError):
        source.render_pages(cache[0], cache[1], expected_sha256=sha(cache[0]), trusted_page_bindings=proof)


@pytest.mark.parametrize('limit', ['MAX_BYTES', 'MAX_PAGES', 'PAGE_PIXELS', 'BATCH_PIXELS',
                                 'PAGE_FILE_BYTES', 'MAX_OUTPUT_BYTES', 'BATCH_PAGES'])
def test_current_resource_caps_and_batch_parameters_apply(cache, monkeypatch, limit):
    monkeypatch.setattr(source, limit, 1)
    monkeypatch.setattr(source, '_child', no_worker)
    with pytest.raises(ValueError):
        reuse(cache)


@pytest.mark.parametrize('parameter', ['renderer', 'scale'])
def test_changed_requested_parameters_cannot_relabel_prior_pixels(cache, monkeypatch, parameter):
    monkeypatch.setattr(source, '_child', no_worker)
    if parameter == 'renderer':
        monkeypatch.setattr(source, 'version', lambda _: 'new-version')
    with pytest.raises(ValueError, match='parameters'):
        reuse(cache, **({'scale': 2.0} if parameter == 'scale' else {}))


@pytest.mark.parametrize('target', ['page-000.png', 'pages.json', 'resume.json', '.render.lock', 'source.pdf', 'parent'])
def test_symlinks_cannot_supply_trusted_cache(cache, monkeypatch, target):
    pdf, output, _, _ = cache
    if target == 'parent':
        original = output.with_name('real-pages')
        output.rename(original)
        output.symlink_to(original, target_is_directory=True)
    else:
        path = pdf if target == 'source.pdf' else output / target
        original = path.with_suffix(path.suffix + '.real')
        path.rename(original)
        path.symlink_to(original)
    monkeypatch.setattr(source, '_child', no_worker)
    with pytest.raises((ValueError, OSError)):
        reuse(cache)


@pytest.mark.parametrize('target', ['source.pdf', 'page-000.png', 'pages.json', 'resume.json', 'root'])
def test_final_fence_rechecks_bytes_paths_and_metadata(cache, monkeypatch, target):
    pdf, output, _, _ = cache
    monkeypatch.setattr(source, '_child', no_worker)
    def mutate(*_):
        if target == 'root':
            output.rename(output.with_name('old-pages'))
            output.mkdir()
            for path in output.with_name('old-pages').iterdir():
                (output / path.name).write_bytes(path.read_bytes())
        else:
            path = pdf if target == 'source.pdf' else output / target
            # Restore mtime to prove the end fence is not a timestamp-only cache.
            import os
            previous = path.stat()
            path.write_bytes(path.read_bytes() + b'changed')
            os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    with pytest.raises(ValueError, match='changed|checkpoint'):
        reuse(cache, on_progress=mutate)


def test_cancellation_remains_observable_and_does_not_publish(cache, monkeypatch):
    before = tree_bytes(cache[0].parent)
    monkeypatch.setattr(source, '_child', no_worker)
    def cancel():
        raise InterruptedError('cancel cached verification')
    with pytest.raises(InterruptedError):
        reuse(cache, check_cancel=cancel)
    assert tree_bytes(cache[0].parent) == before


def test_no_proof_still_preflights_even_when_metadata_looks_complete(cache, monkeypatch):
    operations = []
    def stop(*args):
        operations.append(args[3])
        raise RuntimeError('legacy preflight reached')
    monkeypatch.setattr(source, '_child', stop)
    with pytest.raises(RuntimeError, match='legacy preflight'):
        source.render_pages(cache[0], cache[1], expected_sha256=cache[2]['source_sha256'])
    assert operations == ['preflight']


def test_proof_requires_explicit_verified_source_hash(cache, monkeypatch):
    monkeypatch.setattr(source, '_child', no_worker)
    with pytest.raises(ValueError, match='receipt SHA'):
        source.render_pages(cache[0], cache[1], trusted_page_bindings=cache[2])


@pytest.mark.parametrize('operation', ['preflight', 'batch'])
def test_timeout_identifies_operation_without_paths_or_child_output(tmp_path, monkeypatch, operation):
    class Child:
        stopped = False
        def poll(self):
            return 0 if self.stopped else None
        def terminate(self):
            self.stopped = True
        def wait(self, timeout=None):
            return 0
    child = Child()
    monkeypatch.setattr(source.subprocess, 'Popen', lambda *a, **k: child)
    ticks = iter([0, source.CHILD_SECONDS])
    monkeypatch.setattr(source.time, 'monotonic', lambda: next(ticks))
    with pytest.raises(TimeoutError) as caught:
        source._child(tmp_path / 'private-secret-name.pdf', tmp_path, 1.5, operation, None)
    assert str(caught.value) == f'PDF rendering exceeded batch time limit (operation={operation})'
    assert child.stopped


def test_worker_exit_identifies_preflight_without_leaking_path(tmp_path, monkeypatch):
    class Child:
        returncode = 70
        def poll(self):
            return self.returncode
    monkeypatch.setattr(source.subprocess, 'Popen', lambda *a, **k: Child())
    with pytest.raises(ValueError, match=r'resource limits \(operation=preflight\)') as caught:
        source._child(tmp_path / 'private.pdf', tmp_path, 1.5, 'preflight', None)
    assert str(tmp_path) not in str(caught.value)


@pytest.mark.parametrize('name', ['source.pdf', 'pages.json', 'resume.json', 'page-000.png', '.render.lock'])
def test_leaf_replacement_with_fifo_is_nonblocking_and_fails_before_read(cache, monkeypatch, name):
    """Deterministic stat/open race, with no child/process timeout needed to escape FIFO open."""
    import os
    pdf, output, _, _ = cache
    target = pdf if name == 'source.pdf' else output / name
    real_open = source.os.open
    swapped = False
    def raced_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if str(path) == name and not swapped:
            assert flags & os.O_NOFOLLOW and flags & os.O_NONBLOCK
            swapped = True
            target.unlink()
            os.mkfifo(target)
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(source.os, 'open', raced_open)
    monkeypatch.setattr(source, '_child', no_worker)
    with pytest.raises(ValueError, match='regular file leaves'):
        reuse(cache)
    assert swapped


def test_ancestor_symlink_substitution_at_descriptor_open_cannot_escape(cache, monkeypatch):
    import os
    _, output, _, _ = cache
    real_open = source.os.open
    swapped = False
    def raced_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if str(path) == 'pages' and not swapped:
            assert flags & os.O_NOFOLLOW and flags & os.O_DIRECTORY
            swapped = True
            output.rename(output.with_name('held-pages'))
            output.symlink_to(output.with_name('held-pages'), target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(source.os, 'open', raced_open)
    monkeypatch.setattr(source, '_child', no_worker)
    with pytest.raises(OSError):
        reuse(cache)
    assert swapped
