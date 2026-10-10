# Docs-only bootstrap

`materialize.py` restores the non-document starter files from `template/`, verifying each file against
`manifest.json`. It uses only Python's standard library and does not install or execute dependencies.

Run it from a project containing this complete `docs/` folder:

```sh
python3 docs/bootstrap/materialize.py --dry-run
python3 docs/bootstrap/materialize.py
```

It checks all expected files before writing. Identical files are left alone. Conflicts stop the operation
without overwriting existing content. It rejects path traversal, symlinks and altered template files.
Do not resolve a conflict by deleting unrelated user work. Inspect and merge deliberately.

The template is a frozen copy of the delivered starter, not a second working tree. Once materialized,
edit the root implementation, not the template. Do not rerun bootstrap as a project update mechanism.
The full project archive already contains the root implementation; no bootstrap is necessary there.

The manifest protects against accidental corruption, not a malicious replacement of both manifest and payload.
Only run project code from a source you trust.
