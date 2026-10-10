import argparse
import json
from _paths import ROOT
from guide2build.catalog import find_guide
from guide2build.source import download_pdf, render_pages


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and render an allowlisted official guide, not a model.")
    parser.add_argument("--set", required=True, dest="set_number")
    parser.add_argument("--guide", default="alt-02")
    args = parser.parse_args()
    guide = find_guide(args.set_number, args.guide)
    directory = ROOT / "var/sources" / args.set_number / args.guide
    pdf = directory / "source.pdf"
    receipt = download_pdf(guide["pdf_url"], pdf)
    page_dir = ROOT / "var/public/pages" / receipt["sha256"]
    pages = render_pages(pdf, page_dir)
    result = {"receipt": receipt, "page_count": len(pages), "page_directory": str(page_dir.relative_to(ROOT)),
              "reconstruction_status": "not_started"}
    if len(pages) != guide["expected_page_count"]:
        result["warning"] = "Source page count changed; review guide identity before reconstruction."
    print(json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
