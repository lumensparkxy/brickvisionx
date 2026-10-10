"""Validate locally cached official-source evidence before reuse or scene selection."""
from pathlib import Path
from datetime import datetime
from pydantic import Field
from ..core.models import StrictModel
from ..source import MAX_BYTES, validate_pdf_url, file_sha256


class SourceReceipt(StrictModel):
    requested_url: str
    resolved_url: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(gt=0, le=MAX_BYTES)
    downloaded_at: datetime


def cached_receipt(data_dir: Path, set_number: str, guide_id: str, expected_url: str):
    directory = data_dir / "sources" / set_number / guide_id
    pdf = directory / "source.pdf"
    receipt = pdf.with_suffix(".receipt.json")
    try:
        if not pdf.is_file() or not receipt.is_file() or not 0 < pdf.stat().st_size <= MAX_BYTES:
            return None
        value = SourceReceipt.model_validate_json(receipt.read_text())
        validate_pdf_url(value.requested_url)
        validate_pdf_url(value.resolved_url)
        if value.requested_url != expected_url or value.size_bytes != pdf.stat().st_size:
            return None
        with pdf.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                return None
        if file_sha256(pdf) != value.sha256:
            return None
        return value.model_dump(mode="json")
    except (OSError, ValueError):
        return None
