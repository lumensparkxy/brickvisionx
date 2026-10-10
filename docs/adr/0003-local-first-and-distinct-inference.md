# ADR 0003 — local first; runtime inference is explicit
Status: accepted implementation direction.

Use a local web frontend, FastAPI, SQLite and filesystem storage. Keep runtime perception behind a provider
boundary with a disabled default. Codex-assisted source interpretation may create a labelled reference,
but cannot be reported as deployed automatic conversion. Credentials, budget and accuracy are separate gates.
This allows progress without silently charging a provider or claiming inference capabilities that do not exist.
