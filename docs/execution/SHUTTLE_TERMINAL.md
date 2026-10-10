# Run the Shuttle ADK experiment from Terminal

This explicit command starts inference without Codex. It creates a fresh
31134/booklet-01 exploration revision with no client invocation deadline.
The original job remains frozen at 120 seconds. Both revisions share its
300-request ceiling: at handoff the verified ledger contained 24 requests,
leaving 276. Failed, cancelled and interrupted requests remain charged.

Removing the deadline permits slow requests to finish; it does not accelerate
Gemini. Google can still apply server deadlines and project quotas. The runner
uses one worker, medium thinking, two proposal attempts, disabled tools, no
SDK retries and no provider fallback. Ctrl-C stops the worker; checkpoints and
charged attempts remain available for an explicit resume.

Run this once to create the new job. It reuses the verified official PDF and
individual geometry, and starts indexing and reconstruction afresh. It does
not import the old model responses or modify the red aeroplane application.
Keep Terminal open; `caffeinate` prevents idle sleep while the worker runs.
The existing ignored `.env` supplies the backend key without printing it.

```sh
cd /Users/admin/learn_python/brickvisionx
bash <<'SHUTTLE_RUN'
set -euo pipefail
DATA=var/experiments/adk-31134-booklet01-20261010/data
JOB="$(
  .venv/bin/python tools/engine.py --data-dir "$DATA" enqueue \
    --set 31134 --guide booklet-01 --execution-policy explore \
    --model gemini-3.8-flash --thinking-level medium \
    --provider-timeout none --max-model-calls 300 --max-panel-attempts 2 \
    --efficiency-profile incremental-v1 --proposal-profile baseline \
    --revision adk-31134-booklet01-no-timeout-v1 \
    --share-budget-with 2573f70cc20e45329bce1656bddf64d9 |
  .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])'
)"
printf 'Shuttle job: %s\n' "$JOB"
printf '%s\n' "$JOB" > "$DATA/../no-timeout-job-id.txt"
.venv/bin/python tools/engine.py --data-dir "$DATA" resume "$JOB" \
  --provider
exec caffeinate -i .venv/bin/python tools/engine.py --data-dir "$DATA" run \
  --job-id "$JOB" --workers 1
SHUTTLE_RUN
```

To resume that same new job after interruption or a resolved provider blocker,
use this block instead of enqueueing again.
Do not run two workers for this booklet.

```sh
cd /Users/admin/learn_python/brickvisionx
bash <<'SHUTTLE_RESUME'
set -euo pipefail
DATA=var/experiments/adk-31134-booklet01-20261010/data
JOB="$(cat "$DATA/../no-timeout-job-id.txt")"
.venv/bin/python tools/engine.py --data-dir "$DATA" resume "$JOB" \
  --provider
exec caffeinate -i .venv/bin/python tools/engine.py --data-dir "$DATA" run \
  --job-id "$JOB" --workers 1
SHUTTLE_RESUME
```

Only add `--retry-provider-calls` to `resume` when the job has an eligible failed
provider call to retry after its blocker is resolved. It fails on a fresh job
with `No failed provider call is eligible for explicit retry`. Retried requests
remain charged and their original failure evidence is preserved.

In a second terminal, observe the new job without restarting it:

```sh
cd /Users/admin/learn_python/brickvisionx
DATA=var/experiments/adk-31134-booklet01-20261010/data
JOB="$(cat "$DATA/../no-timeout-job-id.txt")"
.venv/bin/python tools/engine.py --data-dir "$DATA" logs "$JOB" --follow
```

The existing preview on port 4176 still selects the original blocked job. A
new-job preview can be started separately on an unused loopback port once a
candidate exists:

```sh
.venv/bin/python tools/preview_engine.py "$JOB" --data-dir "$DATA" --port 4177
```

No fresh live request was made while preparing these commands. The original
experiment results remain in [SHUTTLE_VALIDATION.md](SHUTTLE_VALIDATION.md).
