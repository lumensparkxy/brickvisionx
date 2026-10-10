# Architecture and technical design

## 1. System shape
Use a small local monorepo, not a distributed platform. The browser owns interaction; the backend owns
source acquisition, validation, persistence and workflow state. A separate worker process handles slow work.
The core reconstruction functions must also be callable from the CLI for reproducible experiments.

```text
React + TypeScript + Three.js
       | set lookup / job status / scene / review commands
       v
FastAPI -------------------------- SQLite job/review/revision store
       |                                  |
       | enqueue                          | lease/checkpoint
       v                                  v
Local conversion worker <--------- persistent job queue
       |
       +-- official-source resolver -> bounded PDF fetch -> source receipt
       +-- page renderer -> instruction-panel observations
       +-- perception adapter -> part candidates and relative arrangements
       +-- individual part catalogue -> geometry + connectors
       +-- constrained pose solver -> candidate scene
       +-- structural / geometric / connector / visual checks
       +-- review queue -> accepted versioned scene
       |
       v
Local asset store: PDFs, pages, parts, provenance, candidate scenes, evidence
```

The starter includes a source reader, structural scene contract, BOM counter and read API. Persistent jobs,
part procurement, pose solving, visual comparison and review commands are implementation work, not hidden
features of the starter. See the status document before inferring anything from a directory name.

## 2. Repository layout

| Path | Responsibility |
|---|---|
| `apps/web/src/components/` | Viewer and source-comparison UI. |
| `apps/api/src/guide2build/core/` | Framework-independent contracts and deterministic functions. |
| `apps/api/src/guide2build/source.py` | Official-source retrieval and page rendering. |
| `apps/api/src/guide2build/providers.py` | Perception boundary; disabled default. |
| `apps/api/src/guide2build/reconstruction/` | To create: observations, candidates, connector placement, scoring. |
| `apps/api/src/guide2build/jobs/` | To create: persistence, leases, retries, cancellation, worker loop. |
| `apps/api/src/guide2build/review/` | To create: versioned correction and acceptance operations. |
| `packages/contracts/` | Generated JSON Schema, then generated TypeScript types. |
| `config/sets.json` | Trusted set/guide-to-official-source mapping. |
| `tools/` | Local setup, checks, fetching, schema export and scene auditing. |
| `var/` | Ignored runtime content; never blindly expose this directory as static files. |
| `docs/` | Product contract, source register, execution plan and evidence index. |

## 3. Source resolver
Use the explicit registry for the first source. A resolver interface may later support official-page discovery,
but there is no assumed stable public LEGO JSON API. Keep discovery and fetching separate. Browser requests
supply catalogue identifiers, never an arbitrary fetch URL. An changed/removed source becomes a visible
source error, not an invitation to scrape unrelated sites or substitute a community model.

Cache the original bytes by SHA-256 and store the source URL, resolved URL, date and size. Record page
orientation, dimensions, renderer version and per-page hashes. A cache receipt must hash actual bytes.
Keep any source/page count mismatch reviewable before assigning the known guide identity to new content.

## 4. Durable jobs
Implement a single-worker SQLite queue before exposing conversion as an API request. Use WAL mode,
explicit transactions, timestamps, attempt counts, lease ownership and expiration, and atomic state transitions.
A worker claims one eligible job transactionally, renews its lease, and checkpoints after each stage or main step.
Crashes leave a resumable record. Do not hold a database transaction open during rendering or model inference.

Use an idempotency key scoped to requested set, guide, source revision, pipeline version, part-catalogue
revision, provider/model configuration and extraction prompt version. Source hash is discovered after download;
use a provisional request key then record the content-addressed artifact key. Two requests for the same result
must not launch two paid conversions. A newer source must not overwrite an existing reviewed revision.

Retry transient network/rate-limit failures with bounded exponential backoff. Do not endlessly retry malformed
PDFs, missing credentials or ambiguous geometry. Cancellation is checked between bounded units of work.
The worker stays idle when no jobs exist; it is not an always-running browser automation loop.

## 5. Storage
Proposed SQLite tables: `guides`, `source_versions`, `jobs`, `job_events`, `reconstruction_revisions`,
`review_items`, `review_actions`. Store JSON payloads only where typed schemas validate them. Index job
state/lease expiry and guide/revision lookups. Keep binary PDFs and geometry on disk with content hashes.

Suggested runtime directories:

```text
var/sources/<set>/<guide>/<source-hash>/source.pdf
var/public/pages/<source-hash>/page-000.png
var/public/ldraw/{parts,p,LDConfig.ldr,NOTICE...}
var/reconstructions/<set>/<guide>/<revision>/scene.json
var/observations/<job>/<stage>/...
var/evidence/<run>/...
var/guide2build.sqlite3
```

The starter uses a simpler `scene.json` path. M5 introduces revision routing and an explicit latest-reviewed pointer.
No code should treat a draft's filename as proof of publication. Keep raw observations and correction logs private.

## 6. Geometry boundary
The assembly engine manipulates real part instances, poses and connector relations. The renderer consumes
immutable snapshots. Geometry is fetched by a curated part resolver, not from a provider-returned URL.
Keep part origins consistent. Use a dedicated adapter for LDraw coordinates. A generic THREE.BoxGeometry
may be used for a test fixture or debug collision volume, never as an undisclosed replacement piece.

## 7. Runtime vision versus development assistance
Define a provider interface with structured observations, explicit model identity, prompt version, latency,
request ID, usage/cost metadata where available and complete errors. The default provider raises unavailable.
Do not assume a signed-in coding agent automatically supplies inference credentials to the deployed backend.
Select and implement a real adapter only after confirming available credentials and authorizing costs.

During development, the coding agent can inspect official page images and author a reference with provenance.
That path remains usable without an additional API key. It is not the automated provider path and may not be
reported as a successful live conversion. Contract replay fixtures are useful for software testing only.

## 8. Operational scope
One API process, one conversion worker, one browser frontend, local file storage and SQLite are sufficient.
Do not introduce Redis, Kafka, Kubernetes, a vector database or user authentication before the local prototype
requires them. Lack of public deployment is deliberate; deploying the unauthenticated local review API publicly
would require a new threat model and authorization layer.
