# State (updated 2026-10-10 15:05 UTC+2)

## Last completed
- Voice/typed navigation with Gemini: screens + tutorial steps + generic `click` on any visible control.
  - Backend: `apps/api/src/guide2build/voice/chat.py` (ActionType incl. `click`, ControlContext, MAX_CONTROLS=80, validate_action), `main.py` (`checked_navigation` fallback for open_tutorial).
  - Web: `voice/controls.ts` (collectControls, usable), `voice/assistant.ts` (parseAction click), `voice/useAssistant.ts`, `App.tsx` (performAction, assistantContext with controls, `data-voice-scope`), `VoiceChat.tsx` (collapsible dock), `ViewerWorkspace.tsx` (step commands + step context).
- Live checks: "Open the plane tutorial" -> honest fallback to booklets (no prepared scene). "Can you click on prepare booklet?" with 2 prepare buttons -> `click c2` (picked Main build without asking).
- Tests: Playwright software 24 passed (incl. `tests/e2e/voice-navigation.spec.ts`, 4 tests); Vitest 62 passed; pytest tests/backend exit 0; ruff OK; build OK.
- Evidence: `var/evidence/voice/` (dock-*.png, dock-layout.mjs, e2e-*.mjs, pytest.log).

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
- User tries voice with a real mic. Optional: ask-which when labels are ambiguous; confirmation for spending actions; resolve LDConfig pin with explicit approval.
