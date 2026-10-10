---
name: official-guide-ingestion
description: Resolve a LEGO set number to a curated official PDF and preserve safe, reproducible source evidence.
---

# official-guide-ingestion

Read docs/10_SECURITY_AND_RIGHTS.md. Accept a set number and guide ID, not arbitrary URLs.
Use config/sets.json; do not infer CDN file names or call undocumented services as if stable public APIs.
Validate download host/path, redirects, type, size and signature. Enforce timeouts and bounded retries.
Cache bytes atomically, hash them, render pages and record page dimensions and pixel coordinate conventions.
Inspect the rendered pages. Text extraction alone does not recover geometric instructions.
Separate parts boxes, callouts and main-step panels; a page is not a step. Record parser version and crops.
Retain source bytes and notices locally; do not publish official manuals by default.
Outputs: source receipt, page assets, panel manifest, any access or parsing blocker.
