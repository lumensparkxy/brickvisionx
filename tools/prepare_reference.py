"""Prepare the shipped PDF-assisted candidate locally. This is NOT automatic conversion."""
import json
from _paths import ROOT
from fetch_parts import fetch_parts, fetch_materials
from guide2build.catalog import find_guide
from guide2build.jobs.source_cache import cached_receipt
from guide2build.reconstruction.reference import build_reference, materialize, SOURCE_HASH
from guide2build.source import download_pdf, render_pages


def main():
    guide = find_guide("30669", "alt-02")
    data = ROOT / "var"
    pdf = data / "sources/30669/alt-02/source.pdf"
    receipt = cached_receipt(data, "30669", "alt-02", guide["pdf_url"])
    if not receipt:
        receipt = download_pdf(guide["pdf_url"], pdf)
    if receipt["sha256"] != SOURCE_HASH:
        raise SystemExit("The official source has changed; the authored candidate needs review before reuse.")
    render_pages(pdf, data / "public/pages" / receipt["sha256"])
    candidate, _, _ = build_reference()
    roots = sorted({instance.part_id for instance in candidate.instances})
    fetch_parts(roots, data / "public/ldraw")
    fetch_materials(data / "public/ldraw")
    report = materialize(ROOT)
    print(json.dumps({"artifact": "PDF-assisted authored candidate; NOT automatic conversion",
                      "revision": report["revision"], "status": "needs_review",
                      "main_steps": report["main_steps_candidate"], "microsteps": report["microsteps"]}, indent=2))


if __name__ == "__main__":
    main()
