# Source register and decisions

Checked on **2026-10-01**. These references support interfaces and source facts; they are not a guarantee
that future sites or installed software remain unchanged. Prefer the current primary documentation when
implementing. URLs below are intentionally included for the coding agent to inspect.

## Primary references

| ID | Source | URL | Used for |
|---|---|---|---|
| S1 | OpenAI: AGENTS.md | https://developers.openai.com/codex/guides/agents-md/ | Project instructions. |
| S2 | OpenAI: config reference | https://developers.openai.com/codex/config-reference/ | Project `.codex/config.toml`, permissions and agent limits. |
| S3 | OpenAI: subagents | https://developers.openai.com/codex/multi-agent/ | Standalone custom agent TOML files. |
| S4 | OpenAI: skills | https://developers.openai.com/codex/skills/ | `.agents/skills` discovery and SKILL.md metadata. |
| S5 | Three.js: LDrawLoader | https://threejs.org/docs/pages/LDrawLoader.html | Individual part loading/materials/dependencies. |
| S6 | LDraw file format | https://www.ldraw.org/article/218.html | Coordinates, units and part references. |
| S7 | LDraw legal information | https://www.ldraw.org/legal-info | Asset terms and notices. |
| S8 | LEGO Fair Play | https://www.lego.com/en-us/legal/notices-and-policies/fair-play | Branding/content-use review before publication. |
| S9 | LEGO set instructions | https://www.lego.com/en-ch/service/building-instructions/30669 | Initial set/source identity. |
| S10 | Official alternate booklet 02 | https://www.lego.com/cdn/product-assets/product.bi.additional.extra.pdf/30669_02_BI_Build_Alt.pdf | Sole assembly-instruction source for the target build. |
| S11 | Vite guide | https://vite.dev/guide/ | Frontend setup; check runtime compatibility. |
| S12 | FastAPI documentation | https://fastapi.tiangolo.com/ | Python HTTP layer. |
| S13 | uv project guide | https://docs.astral.sh/uv/guides/projects/ | Python environments and real lockfiles. |
| S14 | pypdfium2 documentation | https://pypdfium2.readthedocs.io/en/stable/ | PDF rasterisation. |

Some OpenAI documentation URLs redirected to `learn.chatgpt.com` during verification. Both the original
official URL and its official redirect destination can be used. Do not replace them with an unofficial tutorial
when a configuration question can be answered from the primary reference.

## Target-source observations
The chosen official PDF has eight pages. The guide's main instructions run through 12. Page index 1 shows
main steps 1–2; page index 2 shows steps 3–4 with callout subassemblies. The first four callouts indicate new
piece quantities of 3, 2, 3 and 3 respectively: 11 physical pieces in that slice. These are observations from
source-page inspection, not a reconstructed assembly. Exact part IDs and 3D poses are not supplied here.
Re-check all observations against locally downloaded/rendered bytes before accepting the reference. [S10]

The first four steps are a validation checkpoint. The complete selected booklet remains the V1 target.
No local source hash is supplied because the packaging environment could inspect the PDF through the web
reader but could not download it into the local filesystem. `source_sha256` is deliberately null in the registry.
The fetch tool computes it only from real downloaded bytes. No PDF or completed assembly is bundled.

## Decisions and rationale

- **Source-number entry:** user requirement; no upload UI.
- **No finished community models:** user requirement; preserve PDF reconstruction as the actual task.
- **Individual parts allowed:** avoids re-modelling every primitive without importing somebody else's assembly.
- **One supported guide first:** creates a bounded, inspectable evaluation before catalogue expansion.
- **Python + React/Three.js:** separates geometric/source processing from interactive display.
- **Local SQLite/files:** supports durable jobs without premature infrastructure.
- **Vision-provider boundary:** runtime autonomy is a separately configured capability, not inherited Codex access.
- **Versioned review and evidence:** prevents assisted corrections from being misreported as automatic success.
- **Single canonical AGENTS.md:** repository-wide instructions, scoped additions and thin compatibility wrapper.

See the ADR files for the most consequential architecture choices. None of these decisions authorizes publication,
paid calls, account creation or downloading complete third-party model assemblies.
