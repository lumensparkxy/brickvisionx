# Tutorial release operations

The public server is `guide2build.public:app`. Never deploy `guide2build.main:app`, which contains the local construction and review APIs.

## Prerequisites and authority

Use `lumensparkxy`, release database `guide2build`, request database `guide2build-requests`, and the project-local gcloud configuration at `var/gcloud`. Both named databases are mandatory: the default database is rejected. Complete project-local gcloud login and Application Default Credentials using the cloud setup runbook. Credentials are never placed in a release bundle.

`tools/release.py` impersonates `guide2build-uploader` for staging and `guide2build-publisher` for approval/publication. The uploader can create and read staging objects and synchronize request records; it cannot write the release database or public asset bucket. Publication additionally requires a verified Google ID token for `maswadkar@gmail.com` with the gcloud CLI audience. No email argument or `actor_type` submitted in a body grants approval.

**Run `approve` only after the user explicitly approves that exact release hash.** Google authentication identifies the principal; it does not replace the user's per-version decision. Agents must not invoke approval merely because credentials are available.

## Prepare a reviewed tutorial bundle

A release requires:

- A structurally valid source-aware v2 scene with geometry and connector checks passing.
- A validation report bound to the canonical scene SHA-256, no blocking findings, an assembly review, and complete source coverage.
- A separate, independently verified coverage index. Raw model-generated `automatic_unverified` indexing is not sufficient.
- Sources matching `config/release-sources.json`: set/booklet identity, actual PDF hash, official URL and page count. Append new edition pins only from verified official bytes; never from model output. Retain old hash-specific pins so approved earlier versions remain verifiable and rollback stays available. Never overwrite an earlier edition pin merely because a booklet URL now serves new bytes.
- A PNG captured from the actual model renderer for this exact scene. Do not use a generic image or a PDF screenshot. PNG metadata and size are bounded; its file hash and scene binding enter the immutable manifest.
- Real individual LDraw geometry with confined paths, actual byte hashes, dependency closure, classifications and retained licence notices.

The reviewed coverage index has this shape (values below are placeholders, not source evidence):

```json
{
  "verification": "independently_verified",
  "sources": ["<actual PDF SHA-256>"],
  "expected_step_keys": ["main:1", "main:2"]
}
```

The validation report's `coverage_index_sha256` is SHA-256 of the canonical JSON encoding of that exact index, using `guide2build.releases.models.digest`. Printed numbering resets use distinct section IDs. Unnumbered steps use `section:unnumbered:step_id`. Preserve the observations and independent review evidence locally; the normalized index records the verified denominator rather than private source crops.

```sh
.venv/bin/python tools/release.py package \
  --scene var/reviewed/scene-v2.json \
  --validation var/reviewed/validation.json \
  --coverage-index var/reviewed/coverage.json \
  --preview var/reviewed/model-render.png \
  --output var/releases/new-version

.venv/bin/python tools/release.py verify var/releases/new-version
.venv/bin/python tools/release.py stage var/releases/new-version
```

The output directory must not already exist. Packaging is atomic. `verify` rechecks hashes, source pins, coverage, the lightweight index against full snapshots, and publication file allowlists. Staging is resumable and verifies remote object generations and bytes. No tutorial becomes public during staging.

## Approve, publish and roll back

After reviewing the exact bundle and receiving the user's explicit approval:

```sh
.venv/bin/python tools/release.py approve --release <release-sha256>
.venv/bin/python tools/release.py publish --release <release-sha256>
```

For an existing tutorial, provide its current release hash:

```sh
.venv/bin/python tools/release.py publish \
  --release <new-release-sha256> --expected-head <current-release-sha256>
```

Publication revalidates the staged scene and source evidence, copies generation-checked immutable assets to the public bucket, then atomically changes the catalogue head and published catalogue metadata. The published catalogue is a single bounded Firestore document (SQLite has an equivalent transactional table), containing only approved head identities and official source links. Interrupted copying leaves the previous tutorial selected. A changed head rejects the update. Approval for one hash cannot approve a correction with another hash.

Rollback restores a previously approved version; it does not delete history or bytes:

```sh
.venv/bin/python tools/release.py rollback \
  --release <previous-approved-release-sha256> --expected-head <current-release-sha256>
```

A failed operation prints a redacted error class and claims no success. Use private local/cloud diagnostics without copying credentials into evidence. Public metadata is cached for 30 seconds, so catalogue visibility can lag promotion or rollback by that interval.

## Public runtime configuration

```text
GUIDE2BUILD_PUBLIC_STORE=firestore
GOOGLE_CLOUD_PROJECT=lumensparkxy
GUIDE2BUILD_FIRESTORE_DATABASE=guide2build
GUIDE2BUILD_REQUEST_DATABASE=guide2build-requests
GUIDE2BUILD_PUBLIC_BUCKET=lumensparkxy-guide2build-assets
GUIDE2BUILD_ASSET_BASE_URL=https://storage.googleapis.com/lumensparkxy-guide2build-assets/
GUIDE2BUILD_WEB_DIST=/app/apps/web/dist
```

Without the Firestore selector, the public app uses a local SQLite publication store at `var/publication.sqlite3` (override with `GUIDE2BUILD_PUBLIC_DB`). This adapter is for tests and local development; local candidate files never imply publication.

Public requests deduplicate by set number, admit at most 100 new set numbers per UTC day transactionally, and at most 60 request attempts per minute per process before database access. The published catalogue caches for 30 seconds globally; unknown set searches do not issue per-set database reads. Full manifest reads use a four-entry cache with a 30-second lifetime. Publication is capped at 1,000 booklet entries and 500 KB of catalogue metadata; exceeding either bound rejects the transaction before changing a head. These limits reduce work; they are not a guaranteed billing cap.

## Evidence boundaries

Package validation proves typed structure, official-source binding, declared coverage consistency, real dependency hashes and explicit review gates. It does not independently prove that every pose matches the PDF, that a coverage reviewer was correct, or that the model was physically assembled. Keep automatic, corrected, agent-reviewed, human-approved and physically tested outcomes distinct.

No current blocked or partial candidate may bypass these gates. Test fixtures and mock PNGs used by the software tests are not production tutorial evidence. Cloud IAM, transfers and deployment require live verification separately from passing local tests.

## Publish an explicitly unverified alpha model

The separate `unverified_alpha` category exposes a frozen PDF-assisted model for exploration. It preserves `needs_review`, `accuracy: unverified`, and assembly/connector/physical checks as `not_run`. It cannot be presented as a reviewed tutorial or an automatic reconstruction success. The reviewed tutorial gate above is unchanged. A publication approval authorizes public distribution of one exact hash; it does not record a human assembly review.

Alpha packaging requires a bounded disclosure (`AlphaDisclosure`), an exact `reported_unverified` coverage index, official-source pins, an actual final Three.js viewport PNG bound to the canonical scene and PNG hashes, and the same verified individual-part dependency closure. Uncertainty notes are retained. Later cumulative booklets distinguish this booklet's snapshots from cumulative snapshots. Geometry component counts are not certified retail piece totals.

```sh
.venv/bin/python tools/release.py package-alpha \
  --scene var/alpha/scene-v2.json \
  --disclosure var/alpha/disclosure.json \
  --source-index var/alpha/source-index.json \
  --preview-binding var/alpha/preview-binding.json \
  --geometry-root var/alpha/geometry \
  --preview var/alpha/final-viewport.png \
  --output var/releases/alpha-version
```

The preview binding identifies `scene_sha256`, `preview_sha256`, `renderer: threejs`, and the actual final `rendered_step_id`. Only typed public disclosures, snapshots, geometry, viewport PNG and sanitized provenance are exported. Official PDFs, page crops, completion reports, prompts, engine jobs and credentials remain private. Original DAT notices and author/source/licence references remain intact; colour configuration rights are recorded separately from DAT licence headers.

Use the same `verify`, private `stage`, exact-hash `approve`, and compare-and-swap `publish` commands. The user approval requirement in **Prerequisites and authority** applies to alpha releases too. Cloud transfer/validation supports `--transfer-workers 1` through `8`; this changes bounded per-file transfer concurrency, not ordering, byte verification or approval. Heads remain sequential and generation checked. Public UI labels this category **ALPHA MODEL · UNVERIFIED** with **Open alpha model**, and never enables source-image or private review APIs.


## Add a new set without a website rebuild

Prepare the new official source locally, append its verified source pin, reconstruct and validate its booklet, then use the same stage/approve/publish commands. Promotion inserts its metadata into the approved catalogue atomically with its release head. The already running portal discovers the set after its catalogue cache refreshes; neither `config/sets.json` in the container nor the container image needs changing for availability.

A newly published set without a curated display name appears as `Set NUMBER`, and its booklet uses its actual guide ID. Its instruction link and page count come from the approved manifest's source record. The portal never invents a title or an official URL. Existing curated names remain useful display metadata; they are not proof of publication. Rollback restores the prior version's source metadata and head in the same transaction.
