# Local development and operations

## Initial environment
Use Python 3.11+ and a Node release compatible with the chosen Vite version (starter target: Node 22.12+).
Use a project-local Python environment and npm workspaces. Do not install project packages system-wide.
The starter dependency ranges are conservative compatibility selections, not a claim of latest releases.
Verify package advisories and current APIs during setup; keep changes small and record exact resolved versions.

```bash
uv sync --extra dev
npm install
uv run python tools/doctor.py
uv run python tools/dev.py
```

The last command starts a loopback API on port 8000 and Vite on port 5173. It terminates both processes on exit.
On a remote development machine, use the IDE/Codex port-forwarding feature or an explicitly configured SSH
tunnel; do not make the unauthenticated server public to solve a connectivity issue.

No real source or geometry assets are bundled. Fetch the approved PDF explicitly:

```bash
uv run python tools/fetch_guide.py --set 30669 --guide alt-02
```

This produces source bytes, a receipt and rendered page assets. It does **not** produce a reconstructed model.
The next milestones map panels, resolve individual parts, solve poses and review the resulting assembly.

## Configuration
Default storage is `var/`. The API supports `GUIDE2BUILD_DATA_DIR`; CLI tools initially use the root `var/`
location. M1 should consolidate settings before custom storage is advertised as end-to-end support.
`.env.example` is documentation; environment values are not automatically loaded by every tool. For a configured
local `.env`, use `uv run --env-file .env ...` after reviewing its contents. Never commit credentials.

The default vision provider is disabled. PDF-assisted authoring during development is distinct from runtime
inference. Do not assume the browser or backend inherits the coding agent's authentication.

## Dependency reproducibility
Generate genuine `uv.lock` and `package-lock.json` on the first successful install and commit them when the
repository workflow authorizes commits. Subsequent CI/reproduction should use `uv sync --frozen --extra dev`
and `npm ci`. The initial delivery intentionally does not include fabricated lockfiles because registry access
was unavailable during packaging. Record any dependency upgrades and execute all affected checks.

## Verification
```bash
uv run python tools/check.py
npx playwright install chromium
npm run test:e2e
```

`tools/check.py --python-only` runs the explicitly smaller Python/contracts scope. It must not be described
as frontend or E2E verification. The included Playwright tests mock network responses; add real-backend tests
before claiming full integration. Optional external tests must be separately enabled and budgeted.

For routine changes, `tools/check.py --quick` runs an explicit selection of 105 backend regression cases,
schema drift, Ruff, frontend type checking and all frontend unit tests. It omits the full regression suite,
production bundle and browser checks; its output labels that smaller scope. Combine `--quick --python-only`
for a backend-only subset. The no-flag CI/release command stays full; `--quick --e2e` is rejected before startup.
`npm run check` type-checks once through the build command, alongside all frontend tests and bundling.
Neither test scope runs as part of reconstruction or saved-model playback.

## Job operations after M5
Start the worker as a separate local process using the command implemented in that milestone. Add it to the
dev runner only when its real lifecycle is available. Jobs persist in SQLite; worker restart resumes recorded
checkpoints after expired leases are recovered. Do not rely on keeping a terminal or a browser tab open.

Keep structured logs with job, set, guide, source hash, revision, stage, duration and error code. Do not log keys.
Cache retention should be a local setting with explicit cleanup, never a destructive default. Keep accepted
scene revisions and their source receipts linked even when disposable intermediate renders are removed.

## Deployment boundary
Provide a reproducible local build and runbook. Docker packaging is optional follow-up, not a reason to block
the local prototype. Production hosting, accounts and multi-user access are out of scope and require the
security/publication gate in `10_SECURITY_AND_RIGHTS.md`.
