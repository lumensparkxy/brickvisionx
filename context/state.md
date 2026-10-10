# State (updated 2026-10-10 15:33 UTC+2)

- 15:33: Entire CLI 0.11.4 (darwin/arm64) installed via https://entire.io/install.sh to `~/.local/bin/entire` and `git-remote-entire`. Checksum verified by the script. Post-install appended Zsh completion to `~/.zshrc` (`source <(entire completion zsh)`). Hooks in `.codex/hooks.json` and `.claude/settings.json` already call `entire` when it is on PATH.
- 15:39: `entire login` completed via device-code flow (no TTY). `entire auth status`: logged in, expires in 29d, user `github:YodaGitMaster`, jurisdiction eu, token in macOS Keychain.
- 15:40: `entire enable` in brickvisionx: already enabled. `.entire/settings.json` has `enabled: true`, telemetry true, checkpoints primary `git-refs`. Agents: Antigravity, Claude Code, Codex. Cursor is not in that list. No files changed by this run.

## Last completed
- Voice/typed navigation with Gemini: screens + tutorial steps + generic `click` on any visible control.
  - Backend: `apps/api/src/guide2build/voice/chat.py` (ActionType incl. `click`, ControlContext, MAX_CONTROLS=80, validate_action), `main.py` (`checked_navigation` fallback for open_tutorial).
  - Web: `voice/controls.ts` (collectControls, usable), `voice/assistant.ts` (parseAction click), `voice/useAssistant.ts`, `App.tsx` (performAction, assistantContext with controls, `data-voice-scope`), `VoiceChat.tsx` (collapsible dock), `ViewerWorkspace.tsx` (step commands + step context).
- Live checks: "Open the plane tutorial" -> honest fallback to booklets (no prepared scene). "Can you click on prepare booklet?" with 2 prepare buttons -> `click c2` (picked Main build without asking).
- Tests: Playwright software 24 passed (incl. `tests/e2e/voice-navigation.spec.ts`, 4 tests); Vitest 62 passed; pytest tests/backend exit 0; ruff OK; build OK.
- Evidence: `var/evidence/voice/` (dock-*.png, dock-layout.mjs, e2e-*.mjs, pytest.log).

- 15:15: Mic mute button (session.ts setMuted, useAssistant muted/toggleMute, VoiceChat `.voice-mute`). Offline test `tests/e2e/voice-mute.spec.ts` (page.routeWebSocket fakes Gradium; Chromium fake mic = loud audio). Fixed flaky `say()` helper in voice-navigation.spec.ts (collapsed dock hides transcript). Software e2e 25 passed; Vitest 62; build OK.

- 15:25: Prepared-pages viewer in booklet dialog; `tests/e2e/prepared-pages.spec.ts`. Live: 30669/alt-01 shows 9 real pages (1149x817). Software e2e 26 passed; Vitest 62; build OK. Evidence `var/evidence/pages/`.
- Local prepared jobs: 30669/alt-01 (5f4312d8…, 9 pages), 60400/booklet-01 (5ab7d0fc…, 32 pages); both needs_review, no 3D.
- 15:30: LDConfig blocker RESOLVED without changing the pin: exact pinned file (sha 0178cd14…) found in official `lcad2605.zip` (member ldraw/LDConfig.ldr); installed to var/public/ldraw, provenance `materials.LDConfig.ldr.acquired_from` records archive URL/sha. Live official file (d3490047…) only adds 11 `!AVATAR` lines. Backups in var/ldraw-archive/.
- `tools/prepare_reference.py` OK -> revision pdf-assisted-30669-alt02-v3, 12 main steps, 16 microsteps, needs_review. "Try the plane tutorial" opens the 3D viewer (screens var/evidence/pages/plane-*.png). Plain scene route 409 by design; UI loads candidate revision.
- Warning: re-running `tools/fetch_parts.py` keeps the pinned file (hash matches receipt); deleting var/public/ldraw/LDConfig.ldr would refetch the live (mismatching) file.

- 15:40: Movable/minimizable voice dock with 9-dot grip. New e2e test in voice-navigation.spec.ts. Software e2e 27 passed; Vitest 62; build OK. Screens var/evidence/voice/dock-move-*.png.

## Running
- Dev server: `var/.venv-gradium/bin/python tools/dev.py` -> http://127.0.0.1:5173 (API :8000). Restart after backend edits; wait until ports free (old processes linger ~seconds, cause Errno 48).

## Blockers / risks
- No prepared 3D tutorial: `tools/prepare_reference.py` fails, `LDConfig.ldr` hash differs from reference pin (1 of 135 assets, likely upstream LDraw change). Pin NOT changed (provenance check). In-tutorial navigation only tested with synthetic fixture.
- No confirmation for voice clicks (user choice): misheard command can start preparation/automatic conversion (may use paid AI) or save/cancel. Ambiguous labels: Gemini picks one without asking.
- External links by voice may be popup-blocked (no user gesture).
- `uv` not installed; Node 20.19.5 vs engines >=22.12.
- 2026-10-10: real Gradium key removed from `.env.example` before push to `francesco-voice`. Key remains only in ignored `.env`. Rotate the key; it was in the working tree and this chat.
- No barge-in; not tested with a real human mic, Safari or Firefox.
- Mobile: open viewer dock covers much of the 3D viewport (collapsed by default).

## Next
- 15:33: pushed `francesco` to origin. HEAD `30a9508` matches `origin/francesco`. Local `francesco-voice` remains at `8491f37` and was not pushed.
- User tries voice with a real mic. Optional: ask-which when labels are ambiguous; confirmation for spending actions; resolve LDConfig pin with explicit approval.
