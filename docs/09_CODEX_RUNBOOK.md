# Codex execution runbook

## Native files versus repository conventions
`AGENTS.md` carries repository instructions [S1]. `.codex/config.toml` is Codex configuration [S2].
Project-specific custom roles are standalone TOML files in `.codex/agents/` with `name`, `description`
and `developer_instructions` [S3]. Reusable local skills live under `.agents/skills/*/SKILL.md` [S4].

`project.toml` is our own machine-readable project manifest, not a file Codex automatically treats as
configuration. `pyproject.toml` is Python packaging/tool configuration. Do not confuse the three files.
No Codex model name is pinned: inherit a model the user's authenticated environment actually supports.

## Preflight
Open the actual execution directory in Codex, including when using a remote machine. Read root instructions
and the start document. Inspect existing files and preserve unrelated work. Run `tools/doctor.py`, establish
the installed Codex version, and verify supported config fields against official docs when necessary.
Current native configuration was checked on 2026-10-01; older clients may need adaptation.

Trust the project through the user's normal Codex flow. This repository must not modify global trust files,
authentication, telemetry routing or system-wide settings. The checked-in default permits workspace writes
but keeps command network access off until approved. Normal dependency/source downloads may prompt for approval.
Do not switch to unrestricted access to hide permission failures.

## Docs-only bootstrap
Run `python3 docs/bootstrap/materialize.py` from the project root. It copies bundled template files only
when missing, validates their checksums, and reports conflicts without overwriting them. Examine conflicts
before choosing a merge. A dry-run is available with `--dry-run`.

After creating new `.codex/` files, a fresh session may be needed for automatic configuration/agent discovery.
This does not require abandoning the one-prompt task: read AGENTS.md and role/skill files explicitly and
continue sequentially in the same session. On the next session, native discovery uses the materialized files.

## Workflow
Execute `docs/prompts/BUILD_V1.md`. The primary agent owns requirements, schema integration, final tests
and progress reporting. Use `reconstruction_engineer`, `web_engineer`, `backend_engineer` and
`quality_reviewer` only for well-scoped tasks. At most three workers are active at once. Roles do not imply
a separate deployed multi-agent architecture; they are a coding-workflow aid.

Assign file ownership before parallel work. Shared contracts are changed by the integrator or one explicitly
delegated owner. A worker returns changed files, exact test results, unresolved issues and source evidence.
The integrator verifies real execution paths rather than accepting a summary as proof.

Skills are task playbooks, not separate packages requiring online installation. Read the relevant local skill
before its task. No external marketplace plugin is required to use the starter. Use available browser/image
inspection tools for verification; record tooling limitations honestly.

## Authority and permission boundaries
Routine local implementation, tests and generated artifacts are part of the build task. New cloud accounts,
paid runtime inference, publishing, system-wide installs, modifying existing unrelated code or issuing external
messages are not automatically authorized. Keep approved network actions narrow. Do not create or expose secrets.

An available coding model can help inspect source images during development. It does not establish runtime
API credentials for the webapp. A runtime provider should remain disabled until explicitly configured.
Report that gate as unavailable rather than making up keys, model IDs or paid-call results.

## GitHub coordination
When the project already has an authenticated GitHub repository, inspect its issues and align local task IDs
with real issue identifiers. GitHub remains the durable backlog when available. Do not create a new repository,
issues, branches on a remote, pushes or pull requests without authorization. When there is no connected repository,
use `docs/13_BACKLOG.md` as the bootstrap plan and leave GitHub IDs null—not invented.

## Checkpoints and context recovery
After each milestone, update `execution/PLAN.md`, `PROGRESS.json`, `BLOCKERS.md` and the validation report.
Record the next executable action, branch/commit where available, changed files, active job and source revision.
On resumption, read those records and inspect repository state before continuing. Never infer a prior successful
test simply because an earlier note says it was planned.

The resume prompt in `prompts/RESUME.md` starts from actual state. Long-running autonomy depends on client
limits, permissions and available evidence; one initial prompt does not remove those constraints.

## Completion response
State what actually runs, exact main/microstep coverage, source provenance, commands, tests, evidence and
remaining risks. Distinguish software completeness from reconstruction validity. Do not stop at scaffolding,
a mockup or the first-four-step slice and label the complete booklet delivered.
