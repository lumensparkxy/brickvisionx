# Guide2Build 3D — Version I

**Set number → official instruction booklet → reconstructed assembly → interactive Three.js tutorial.**

This is an implementation starter and a Codex build contract, not a completed PDF-to-3D converter.
No finished community models, extracted app models, or invented aeroplane assemblies are included.
Individual LDraw parts may be used as geometry; the assembly must be derived from the official PDF.

## Start in Codex

Open this folder as the project root and paste the prompt in **[docs/prompts/BUILD_V1.md](docs/prompts/BUILD_V1.md)**.
For a shorter launch, use:

> Read AGENTS.md and docs/00_START_HERE.md, then execute docs/prompts/BUILD_V1.md end to end. Implement, test, and verify Version I. Continue beyond planning and the four-step checkpoint to the full selected booklet, unless a concrete blocker prevents it. Preserve source provenance and never claim automatic reconstruction or human verification without evidence.

[Start here](docs/00_START_HERE.md) · [Specification](docs/01_PRODUCT_SPEC.md) · [Architecture](docs/02_ARCHITECTURE.md) · [Current status](docs/14_SCAFFOLD_STATUS.md)

## Local starter

Prerequisites: Python 3.11+, Node 22.12+ (or a compatible newer LTS), npm, and uv.
The JavaScript versions are starter compatibility ranges, not a claim about the latest releases.
The first dependency installation must generate and commit `uv.lock` and `package-lock.json`.

```bash
uv sync --extra dev
npm install
uv run python tools/doctor.py
uv run python tools/dev.py
```

Frontend: http://127.0.0.1:5173 · API: http://127.0.0.1:8000/api/v1/health

```bash
uv run python tools/check.py          # local unit/API/schema and frontend checks
npm run test:e2e                      # install Playwright Chromium first
uv run python tools/fetch_guide.py --set 30669 --guide alt-02
```

Fetching requires external network access. No PDF is bundled. The starter's set lookup works,
but its tutorial reports **reconstruction not available** until real reviewed scene data is created.
That is intentional: a missing model is not replaced with a fake one.

## Docs-only installation

Copy the supplied `docs/` directory into an empty repository. The same launch prompt works:
it first runs `python3 docs/bootstrap/materialize.py` to create missing project files.
The materializer never overwrites an existing file and reports conflicts. Reopen Codex after
materialization when needed for newly created project-local agents/configuration to be discovered.
The build can still proceed in the current session by reading the role and skill files explicitly.

## Boundaries

- First supported source: set 30669, official alternate booklet `30669_02_BI_Build_Alt.pdf`.
- First geometry checkpoint: main steps 1–4. Final V1 target: all main steps in that booklet.
- No PDF-upload requirement, RAG requirement, text-to-new-design, shopping, accounts or public hosting.
- Local development only by default. Public hosting requires authentication, job isolation and a rights review.
- Codex uses `.codex/config.toml`; `project.toml` is this repository's own project manifest.
