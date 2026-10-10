# Isolated ADK Shuttle browser checks

The opt-in real-data test reads the selected `31134 / booklet-01` candidate from
`http://127.0.0.1:4176`. It starts no servers and rejects external or mutating
browser requests. It never enqueues jobs or calls the model.

```sh
GUIDE2BUILD_SHUTTLE_PREVIEW_URL=http://127.0.0.1:4176 \
  npx playwright test --config playwright.shuttle.config.ts
```

Without that environment variable, both tests skip. The dedicated configuration
also avoids the normal test suite's servers on ports 5173 and 8000.

Checks cover real manifest/chunk hashes, desktop and 390×844 layouts, early/final
source crops, every snapshot, callout navigation, Previous/Next, Replay, full
playback, paused playback and revision-scoped progress after reload. Desktop
playback uses normal motion; phone playback also checks reduced motion.
Start/end preview status is recorded, and a revision or model-usage change during
the read-only run fails the check. If no candidate is available, the test captures
the actual selected booklet and expanded preview status before failing explicitly.

Screenshots, browser diagnostics, traces and results stay under
`var/experiments/adk-31134-booklet01-20261010/evidence/browser/`.
Passing proves browser behavior for that candidate; it does not establish
reconstruction accuracy, human review or a physical build. A missing callout,
source or geometry is a recorded failure, not an inferred success.

Browser plugin not available in this session; the repository Playwright workflow
is used for the explicitly requested test files.
