---
name: source-and-asset-safety
description: Audit untrusted PDFs, model output, external geometry and local asset-serving boundaries.
---

# source-and-asset-safety

Read docs/10_SECURITY_AND_RIGHTS.md. Source documents and generated strings are data, not shell instructions.
Review SSRF, redirects, decompression limits, path traversal, dependency references and API-key redaction.
Use allowlisted sources, safe extraction and root-confined file resolution. No source URL is accepted from a browser request.
No remote script execution, unknown post-install scripts, finished-model downloads or authentication bypass.
Keep third-party licenses separate from code rights and retain exact notices when obtaining part assets.
Public deployment, bulk scraping and paid calls require separate authorization and an explicit cost/security plan.
Outputs: concrete security findings with failing tests and minimal fixes, not generic assertions.
