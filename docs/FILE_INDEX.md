# Package map

Start with `00_START_HERE.md`, then `prompts/BUILD_V1.md`.

The sixteen numbered documents cover product, architecture, reconstruction, data, API, interface,
implementation, acceptance, Codex operation, safety/rights, local operations, sources, backlog,
scaffold status and the individual-parts catalogue. `adr/` records key architectural decisions.
`execution/` is the resumable plan, progress, blocker and evidence ledger.
`assets/v1-concept.png` is the earlier design reference, not a functioning UI screenshot.

`bootstrap/` makes this entire folder independently usable: its payload restores the root configuration,
agent skills, code, tests, schema and tooling without downloading a template or overwriting existing files.
Do not separately edit the frozen bootstrap template after the working project is restored.
