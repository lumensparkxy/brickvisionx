"""Bounded official-source retrieval; external network access is deliberately explicit."""
from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, unquote, urljoin
import httpx

MAX_BYTES = 20 * 1024 * 1024
ALLOWED_HOST = "www.lego.com"


def validate_pdf_url(url: str) -> None:
    parsed = urlsplit(url)
    path = unquote(parsed.path)
    if (parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST or
            parsed.username or parsed.password or parsed.port not in (None, 443) or
            parsed.query or parsed.fragment or not path.startswith("/cdn/product-assets/") or
            not path.endswith(".pdf") or ".." in path.split("/") or "%" in path):
        raise ValueError("Only allowlisted official LEGO PDF URLs are accepted")


def download_pdf(url: str, destination: Path, *, client: httpx.Client | None = None) -> dict:
    validate_pdf_url(url)
    own_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".pdf.partial")
    current = url
    try:
        for redirect in range(4):
            validate_pdf_url(current)
            with client.stream("GET", current, follow_redirects=False,
                               headers={"Accept": "application/pdf", "User-Agent": "Guide2Build-local/0.1"}) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    if redirect == 3 or "location" not in response.headers:
                        raise ValueError("Redirect limit exceeded or missing redirect location")
                    current = urljoin(current, response.headers["location"])
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";")[0].lower()
                if content_type not in ("application/pdf", "application/octet-stream"):
                    raise ValueError("Response is not a PDF content type")
                if int(response.headers.get("content-length", "0")) > MAX_BYTES:
                    raise ValueError("PDF exceeds download size limit")
                size = 0
                digest = hashlib.sha256()
                with temporary.open("wb") as output:
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise ValueError("PDF exceeds download size limit")
                        output.write(chunk)
                        digest.update(chunk)
                with temporary.open("rb") as source:
                    if source.read(5) != b"%PDF-":
                        raise ValueError("Missing PDF signature")
                os.replace(temporary, destination)
                receipt = {"requested_url": url, "resolved_url": current,
                           "sha256": digest.hexdigest(), "size_bytes": size,
                           "downloaded_at": datetime.now(timezone.utc).isoformat()}
                destination.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
                return receipt
        raise ValueError("No PDF response")
    finally:
        temporary.unlink(missing_ok=True)
        if own_client:
            client.close()


def render_pages(pdf_path: Path, output_dir: Path, *, scale: float = 1.5) -> list[dict]:
    import pypdfium2 as pdfium
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    with pdfium.PdfDocument(pdf_path) as document:
        if len(document) > 250:
            raise ValueError("PDF page-count limit exceeded")
        for index in range(len(document)):
            page = document[index]
            try:
                width, height = page.get_size()
                if width * height * scale * scale > 24_000_000:
                    raise ValueError("Page raster size exceeds limit")
                bitmap = page.render(scale=scale)
                try:
                    image = bitmap.to_pil()
                    filename = f"page-{index:03d}.png"
                    image.save(output_dir / filename)
                    records.append({"page_index": index, "file": filename,
                                    "width_px": image.width, "height_px": image.height})
                finally:
                    bitmap.close()
            finally:
                page.close()
    (output_dir / "pages.json").write_text(json.dumps(records, indent=2) + "\n")
    return records
