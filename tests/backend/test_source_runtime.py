"""Exercise actual PDF rendering and cache writes without network or target fixtures."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from PIL import Image

from guide2build.source import download_pdf, render_pages

URL = "https://www.lego.com/cdn/product-assets/example.pdf"


def test_render_real_pdf_records_pixels_and_renderer(tmp_path):
    pdf = tmp_path / "synthetic.pdf"
    Image.new("RGB", (100, 60), "white").save(pdf, "PDF")
    output = tmp_path / "pages"
    records = render_pages(pdf, output)
    assert len(records) == 1
    image = output / records[0]["file"]
    assert records[0]["sha256"] == hashlib.sha256(image.read_bytes()).hexdigest()
    assert records[0]["renderer"].startswith("pypdfium2/")
    assert json.loads((output / "pages.json").read_text()) == records


def test_malformed_render_does_not_publish_manifest(tmp_path):
    pdf = tmp_path / "bad.pdf"
    pdf.write_bytes(b"%PDF-broken")
    with pytest.raises(ValueError, match="rendering failed"):
        render_pages(pdf, tmp_path / "pages")
    assert not (tmp_path / "pages/pages.json").exists()
    assert not list(tmp_path.glob(".render-*"))


@pytest.mark.parametrize("scale", [0, -1, float("nan"), float("inf"), 5])
def test_render_scale_bound(tmp_path, scale):
    with pytest.raises(ValueError, match="scale"):
        render_pages(tmp_path / "missing.pdf", tmp_path / "pages", scale=scale)


def test_concurrent_changed_source_preserves_both_versions(tmp_path):
    destination = tmp_path / "source.pdf"
    payloads = [b"%PDF-1.7\nfirst test", b"%PDF-1.7\nsecond test"]

    def download(payload):
        with httpx.Client(transport=httpx.MockTransport(lambda request:
                httpx.Response(200, content=payload, headers={"content-type": "application/pdf"}))) as client:
            return download_pdf(URL, destination, client=client)

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(download, payloads))
    receipt = json.loads(destination.with_suffix(".receipt.json").read_text())
    assert receipt["sha256"] == hashlib.sha256(destination.read_bytes()).hexdigest()
    for payload, item in zip(payloads, receipts):
        assert (tmp_path / item["sha256"] / "source.pdf").read_bytes() == payload
    assert not list(tmp_path.glob("*.partial"))


def test_failed_download_preserves_previous_source(tmp_path):
    destination = tmp_path / "source.pdf"
    destination.write_bytes(b"previous valid cached content")
    with httpx.Client(transport=httpx.MockTransport(lambda request:
            httpx.Response(200, content=b"html", headers={"content-type": "application/pdf"}))) as client:
        with pytest.raises(ValueError, match="signature"):
            download_pdf(URL, destination, client=client)
    assert destination.read_bytes() == b"previous valid cached content"


def test_encoded_download_rejected_before_read(tmp_path):
    class NeverRead(httpx.SyncByteStream):
        def __iter__(self):
            raise AssertionError("Compressed body must never be read")
    with httpx.Client(transport=httpx.MockTransport(lambda request:
            httpx.Response(200, stream=NeverRead(), headers={"content-type": "application/pdf",
                                                           "content-encoding": "gzip"}))) as client:
        with pytest.raises(ValueError, match="Encoded PDF"):
            download_pdf(URL, tmp_path / "source.pdf", client=client)


def make_pdf(path, pages=3):
    images = [Image.new("RGB", (20, 10), (index % 255, 100, 200)) for index in range(pages)]
    images[0].save(path, "PDF", save_all=True, append_images=images[1:])


def test_cancel_resume_and_tamper_repair_real_batches(tmp_path, monkeypatch):
    from guide2build import source
    monkeypatch.setattr(source, "BATCH_PAGES", 2)
    pdf, output = tmp_path / "test.pdf", tmp_path / "pages"
    make_pdf(pdf)

    def cancel_after_committed_batch(completed, total):
        assert total == 3
        if completed == 2:
            raise InterruptedError("cancel test")

    with pytest.raises(InterruptedError):
        render_pages(pdf, output, on_progress=cancel_after_committed_batch)
    assert not (output / "pages.json").exists()
    assert len(json.loads((output / "resume.json").read_text())["batches"]["0"]) == 2
    first_mtime = (output / "page-000.png").stat().st_mtime_ns
    operations = []
    actual_child = source._child

    def tracked_child(*args):
        operations.append((args[3], args[5:] if len(args) > 5 else ()))
        return actual_child(*args)

    monkeypatch.setattr(source, "_child", tracked_child)
    progress = []
    records = render_pages(pdf, output, on_progress=lambda done, total: progress.append((done, total)))
    assert len(records) == 3 and progress == [(2, 3), (3, 3)]
    assert (output / "page-000.png").stat().st_mtime_ns == first_mtime
    assert operations == [("preflight", ()), ("batch", (2, 3))]

    last_mtime = (output / "page-002.png").stat().st_mtime_ns
    (output / "page-000.png").write_bytes(b"tampered image")
    operations.clear()
    repaired = render_pages(pdf, output)
    assert repaired == records
    assert (output / "page-002.png").stat().st_mtime_ns == last_mtime
    assert operations == [("preflight", ()), ("batch", (0, 2))]
    assert not list(output.parent.glob(".render-*"))


def test_source_identity_change_cannot_reuse_batches(tmp_path, monkeypatch):
    from guide2build import source
    pdf, output = tmp_path / "test.pdf", tmp_path / "pages"
    make_pdf(pdf, 1)
    render_pages(pdf, output)
    first_identity = json.loads((output / "resume.json").read_text())["identity"]
    # Same page count, different actual source and pixels.
    Image.new("RGB", (20, 10), "red").save(pdf, "PDF")
    operations = []
    actual_child = source._child

    def tracked_child(*args):
        operations.append(args[3])
        return actual_child(*args)

    monkeypatch.setattr(source, "_child", tracked_child)
    render_pages(pdf, output)
    identity = json.loads((output / "resume.json").read_text())["identity"]
    assert identity["source_sha256"] != first_identity["source_sha256"]
    assert operations == ["preflight", "batch"]


def test_over_250_pages_render_with_bounded_batches(tmp_path):
    pdf, output = tmp_path / "large.pdf", tmp_path / "pages"
    make_pdf(pdf, 251)
    progress = []
    records = render_pages(pdf, output, on_progress=lambda done, total: progress.append((done, total)))
    assert len(records) == 251
    assert progress[0] == (0, 251) and progress[-1] == (251, 251)
    assert all(b[0] - a[0] <= 25 for a, b in zip(progress, progress[1:]))
    assert records[-1]["file"] == "page-250.png"


def test_preflight_enforces_configured_page_limit_in_child(tmp_path, monkeypatch):
    monkeypatch.setenv("GUIDE2BUILD_PDF_MAX_PAGES", "2")
    pdf, output = tmp_path / "large.pdf", tmp_path / "pages"
    make_pdf(pdf, 3)
    with pytest.raises(ValueError, match="resource limits"):
        render_pages(pdf, output)
    assert not (output / "pages.json").exists()


def test_render_output_quota_does_not_publish_complete_manifest(tmp_path, monkeypatch):
    from guide2build import source
    monkeypatch.setattr(source, "MAX_OUTPUT_BYTES", 1)
    pdf, output = tmp_path / "test.pdf", tmp_path / "pages"
    make_pdf(pdf, 1)
    with pytest.raises(ValueError, match="disk quota"):
        render_pages(pdf, output)
    assert not (output / "pages.json").exists()
    assert not list(tmp_path.glob(".render-*"))


def test_batch_planner_enforces_pixels_and_pages():
    from guide2build.source import _batches
    dimensions = [{"width_px": 4000, "height_px": 6000}] * 26
    batches = _batches(dimensions)
    assert batches == [(0, 6), (6, 12), (12, 18), (18, 24), (24, 26)]


def test_cancel_during_child_terminates_process(tmp_path, monkeypatch):
    from guide2build import source
    pdf, output = tmp_path / "test.pdf", tmp_path / "pages"
    make_pdf(pdf)
    output.mkdir()
    children = []
    actual_popen = source.subprocess.Popen

    def remember_child(*args, **kwargs):
        child = actual_popen(*args, **kwargs)
        children.append(child)
        return child

    def cancel():
        raise InterruptedError("cancel active child")

    monkeypatch.setattr(source.subprocess, "Popen", remember_child)
    with pytest.raises(InterruptedError):
        source._child(pdf, output, 1.5, "preflight", cancel)
    assert len(children) == 1 and children[0].poll() is not None
    assert not (output / "result.json").exists()


def test_cancel_while_waiting_for_source_lock(tmp_path):
    import fcntl
    from guide2build import source
    checks = []

    def cancel():
        checks.append(True)
        if len(checks) == 2:
            raise InterruptedError("cancel lock wait")

    with (tmp_path / "source.lock").open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(InterruptedError):
            with source._locked(tmp_path / "source.lock", cancel):
                pytest.fail("Must not acquire occupied lock")
    assert len(checks) == 2


def test_cancel_download_removes_partial_and_preserves_previous(tmp_path):
    destination = tmp_path / "source.pdf"
    destination.write_bytes(b"previous version")
    cancelling = False

    class CancellingStream(httpx.SyncByteStream):
        def __iter__(self):
            nonlocal cancelling
            yield b"%PDF-1.7\n" + b"x" * (64 * 1024)
            cancelling = True
            yield b"x" * (64 * 1024)

    def check():
        if cancelling:
            raise InterruptedError("cancel streaming download")

    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, stream=CancellingStream(), headers={"content-type": "application/pdf"}))) as client:
        with pytest.raises(InterruptedError):
            download_pdf(URL, destination, client=client, check_cancel=check)
    assert destination.read_bytes() == b"previous version"
    assert not list(tmp_path.glob("*.partial"))


def test_download_accepts_actual_payload_larger_than_old_limit(tmp_path):
    payload = b"%PDF-1.7\n" + b"x" * (21 * 1024 * 1024)
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, content=payload, headers={"content-type": "application/pdf"}))) as client:
        receipt = download_pdf(URL, tmp_path / "source.pdf", client=client)
    assert receipt["size_bytes"] == len(payload)
    assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()
    # Retained version shares immutable bytes, avoiding a second large disk copy.
    assert (tmp_path / "source.pdf").stat().st_ino == (tmp_path / receipt["sha256"] / "source.pdf").stat().st_ino


def test_render_rejects_replaced_pdf_before_any_child_or_batch(tmp_path, monkeypatch):
    from guide2build import source
    pdf, output = tmp_path / "test.pdf", tmp_path / "pages"
    make_pdf(pdf, 1)
    expected = source.file_sha256(pdf)
    Image.new("RGB", (20, 10), "red").save(pdf, "PDF")

    def unexpected_child(*args, **kwargs):
        pytest.fail("A mismatched PDF must not reach preflight or rendering")

    monkeypatch.setattr(source, "_child", unexpected_child)
    with pytest.raises(ValueError, match="expected receipt"):
        render_pages(pdf, output, expected_sha256=expected)
    assert not (output / "pages.json").exists()
    assert not (output / "resume.json").exists()
    assert not list(output.glob("page-*.png"))


@pytest.mark.parametrize("expected", ["", "a" * 63, "A" * 64, "g" * 64, "../source"])
def test_render_validates_expected_hash_format(tmp_path, expected):
    with pytest.raises(ValueError, match="Expected source SHA-256"):
        render_pages(tmp_path / "missing.pdf", tmp_path / "pages", expected_sha256=expected)
    assert not (tmp_path / "pages").exists()


def test_render_accepts_verified_expected_hash(tmp_path):
    from guide2build import source
    pdf, output = tmp_path / "test.pdf", tmp_path / "pages"
    make_pdf(pdf, 1)
    expected = source.file_sha256(pdf)
    records = render_pages(pdf, output, expected_sha256=expected)
    assert len(records) == 1
    assert json.loads((output / "resume.json").read_text())["identity"]["source_sha256"] == expected


def test_mid_render_source_replacement_cannot_poison_retry(tmp_path, monkeypatch):
    from guide2build import source
    pdf, output = tmp_path / "source.pdf", tmp_path / "pages"
    make_pdf(pdf, 1)
    original_bytes = pdf.read_bytes()
    expected = source.file_sha256(pdf)
    original_records = render_pages(pdf, tmp_path / "baseline-a", expected_sha256=expected)
    alternate = tmp_path / "alternate.pdf"
    Image.new("RGB", (20, 10), "red").save(alternate, "PDF")
    alternate_records = render_pages(alternate, tmp_path / "baseline-b")
    assert original_records[0]["sha256"] != alternate_records[0]["sha256"]
    actual_child = source._child
    child_paths = []

    def replace_after_preflight(*args):
        child_paths.append(args[0])
        assert args[0] != pdf
        assert args[0].stat().st_ino != pdf.stat().st_ino
        result = actual_child(*args)
        if args[3] == "preflight":
            # Reproduce an in-place mutation too; a hardlinked snapshot is unsafe.
            pdf.write_bytes(alternate.read_bytes())
        return result

    monkeypatch.setattr(source, "_child", replace_after_preflight)
    with pytest.raises(ValueError, match="Source PDF changed during rendering"):
        render_pages(pdf, output, expected_sha256=expected)
    assert len(child_paths) == 2 and child_paths[0] == child_paths[1]
    assert not (output / "resume.json").exists()
    assert not (output / "pages.json").exists()
    assert source.file_sha256(output / "page-000.png") == original_records[0]["sha256"]
    pdf.write_bytes(original_bytes)
    monkeypatch.setattr(source, "_child", actual_child)
    retried = render_pages(pdf, output, expected_sha256=expected)
    assert retried == original_records
    assert retried[0]["sha256"] != alternate_records[0]["sha256"]
    assert not list(tmp_path.glob(".render-*"))


def test_cancelled_snapshot_render_keeps_only_original_source_batches(tmp_path, monkeypatch):
    from guide2build import source
    monkeypatch.setattr(source, "BATCH_PAGES", 1)
    pdf, output = tmp_path / "source.pdf", tmp_path / "pages"
    make_pdf(pdf, 2)
    original = pdf.read_bytes()
    expected = source.file_sha256(pdf)
    baseline = render_pages(pdf, tmp_path / "baseline", expected_sha256=expected)
    actual_child = source._child

    def mutate_after_preflight(*args):
        result = actual_child(*args)
        if args[3] == "preflight":
            make_pdf(pdf, 3)
        return result

    def cancel_after_first_batch(done, total):
        if done == 1:
            raise InterruptedError("cancel after mutation")

    monkeypatch.setattr(source, "_child", mutate_after_preflight)
    with pytest.raises(InterruptedError):
        render_pages(pdf, output, expected_sha256=expected, on_progress=cancel_after_first_batch)
    resume = json.loads((output / "resume.json").read_text())
    assert resume["identity"]["source_sha256"] == expected
    assert resume["batches"]["0"][0]["sha256"] == baseline[0]["sha256"]
    pdf.write_bytes(original)
    monkeypatch.setattr(source, "_child", actual_child)
    assert render_pages(pdf, output, expected_sha256=expected) == baseline
