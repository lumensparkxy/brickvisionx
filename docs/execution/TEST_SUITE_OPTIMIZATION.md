# Test-suite optimization — 4 October 2026

Routine work now has an explicit 105-case backend check, instead of rerunning the entire backend suite
for every small change. All 52 frontend unit tests and type checking remain in the normal quick command.
The existing no-flag CI/release check still runs the complete backend suite, schema, Ruff, all frontend
tests, TypeScript and build. Browser checks remain separately opt-in. Model generation and saved-model
playback never run these test suites.

```sh
.venv/bin/python tools/check.py --quick
.venv/bin/python tools/check.py --quick --python-only
.venv/bin/python tools/check.py
```

The quick selection is explicit in `tools/check.py`: source/API/schema validity, append-only scenes,
durable and legacy checkpoints, corrupt artifacts, claims/queue bounds, whole/nested groups, cache
integrity, immutable corrections, exploration continuation/resume and alpha continuation/resume.
It is representative regression coverage, not full verification. Full stress, PDF rendering, all
proposal/input permutations and release/security regressions remain in the full suite. Quick output
labels its scope and does not run the production bundle; `--quick --e2e` is rejected before startup.

## Consolidated work

- Three baseline exploration prompt-contract tests shared the same workflow. One run now checks their
  schema, baseline-profile absence, visibility contract, frozen versions and no-call policy-drift rejection.
  This removes two standalone test cases while retaining their assertions. All distinct parameter cases remain.
- Exploration test saves no longer deep-copy checkpoints nobody reads. Alpha and instruction recovery
  tests explicitly request copies at the stages they inspect; their interruption/resume assertions remain.
- Six pure score/reference tests create an equivalent in-memory SceneV2 instead of seeding unrelated
  SQLite, source images and geometry. Durable evaluation/integration tests still use their real isolated stores.
- Sixteen malformed correction-request cases retain their inputs and expected rejection, and additionally
  prove rejection before accessing job/source state. Source-page bounds, source hashes, cap widening,
  revision lineage, tampering and real correction forks retain integration coverage.
- `npm run check` no longer invokes TypeScript twice. It runs all tests then builds; the existing build
  command still runs `tsc --noEmit` before Vite. The standalone type-check command remains available.

The audit found no exact duplicated test bodies or duplicated imported test collection. Most of the
large reported count consists of distinct parameterized input/contract cases. No inputs were removed,
stress fixtures reduced or parameter cases hidden to make the number smaller. No testing dependency
or parallel runner was introduced.

## Measurements and evidence

The baseline passed 1,043 backend cases in 31.76 seconds. The initial quick run passed 105 backend cases
in 3.31 seconds, followed by all 52 frontend tests and type checking. These are observed local runs
of different scopes, not a guaranteed throughput improvement or model-generation speed measurement.
Final full results and case mappings are retained in `PROGRESS.json`, `VALIDATION_REPORT.md` and
`var/evidence/test-suite-optimization-20261004/`.

The final no-flag check passed **1,041 backend cases in 28.06 seconds**, **52 frontend tests**, schema,
Ruff, TypeScript and build. Independent collection confirms all 105 quick cases are unique and belong
to that full suite. Its additional backend-only quick run passed in 1.75 seconds. Two standalone cases
were consolidated; the eight moved/renumbered context cases retain their original values and outcomes.
Full-run timings are single observations, not a controlled causal benchmark.

Evidence includes baseline/final JUnit and command logs, exact case/assertion mappings, before/after
test bytes, source pins, independent review and the quick/browser argument-rejection probe. Earlier
engine/model evidence remains unchanged. No provider calls, live-job modifications, production changes,
browser/server starts, publication or human/physical assembly review occurred.

Preservation verification confirms all 40 pinned saved scene/source files, all 24 live job rows and
all 14 previously pinned engine/command files are unchanged. The known local app ports remain closed.
