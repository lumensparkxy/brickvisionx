import hashlib
import httpx
import pytest
from guide2build.source import validate_pdf_url, download_pdf
from guide2build.providers import DisabledVisionProvider, ProviderUnavailable

URL = "https://www.lego.com/cdn/product-assets/product.bi.additional.extra.pdf/30669_02_BI_Build_Alt.pdf"


def test_curated_url_is_valid():
    validate_pdf_url(URL)


@pytest.mark.parametrize("url", [
    "http://www.lego.com/cdn/product-assets/a.pdf",
    "https://www.lego.com.evil.test/cdn/product-assets/a.pdf",
    "https://127.0.0.1/cdn/product-assets/a.pdf",
    "https://www.lego.com/cdn/product-assets/../secret.pdf",
    "https://www.lego.com/cdn/product-assets/%252e%252e/secret.pdf",
    "https://user:password@www.lego.com/cdn/product-assets/a.pdf",
])
def test_unsafe_source_urls_are_rejected(url):
    with pytest.raises(ValueError):
        validate_pdf_url(url)


def test_fake_download_receipt_hashes_actual_bytes(tmp_path):
    payload = b"%PDF-1.7\nSynthetic test bytes, not an official booklet."
    client = httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, content=payload, headers={"content-type":"application/pdf"})))
    with client:
        receipt = download_pdf(URL, tmp_path / "source.pdf", client=client)
    assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()
    assert (tmp_path / "source.pdf").read_bytes() == payload


def test_external_redirect_is_rejected(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(302, headers={"location":"https://127.0.0.1/private.pdf"}))) as client:
        with pytest.raises(ValueError, match="allowlisted"):
            download_pdf(URL, tmp_path / "source.pdf", client=client)


def test_html_disguised_as_pdf_is_rejected(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, content=b"<html>not PDF</html>", headers={"content-type":"application/pdf"}))) as client:
        with pytest.raises(ValueError, match="signature"):
            download_pdf(URL, tmp_path / "source.pdf", client=client)
    assert not (tmp_path / "source.pdf.partial").exists()


def test_disabled_provider_is_not_success():
    with pytest.raises(ProviderUnavailable):
        DisabledVisionProvider().extract_step([], {})
