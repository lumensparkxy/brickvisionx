# API specification

Base path: `/api/v1`. JSON responses; no secret values or filesystem paths in errors.
Use Pydantic/OpenAPI as the source of transport contracts and generate the browser client in M1.
The starter is local and unauthenticated; do not bind it publicly.

## Implemented starter endpoints

| Method/path | Success | Failure |
|---|---|---|
| `GET /health` | 200, software stage and disabled provider status. | Server unavailable. |
| `GET /sets/{set_number}` | 200, curated set and supported official guide metadata. | 422 malformed; 404 unsupported. |
| `GET /sets/{set}/guides/{guide}/scene` | 200, structurally valid stored scene. | 404 guide unsupported; 409 missing/invalid scene. |
| `GET /sets/{set}/guides/{guide}/bom` | 200, revision and aggregated physical-instance quantities. | Same scene errors. |

Public local artifacts are mounted at `/assets-local/`; the private runtime directory is not exposed.
Current scene reads may return candidates and carry their status. M5 must separate draft/review reads from
accepted tutorial reads. Do not remove status warnings merely to make a demo appear complete.

## Target endpoints to implement

| Method/path | Contract |
|---|---|
| `POST /conversions` | Body `{set_number, guide_id, mode}`; modes `automated` or `assisted`. Requires `Idempotency-Key`. Returns 202 with job ID; no blocking reconstruction in the request. |
| `GET /jobs/{job_id}` | Current stage, completed units, errors, source hash and output revision. |
| `GET /jobs/{job_id}/events` | Ordered persisted stage events; polling first, SSE optional. |
| `POST /jobs/{job_id}/cancel` | Idempotent cancellation request; finishes current bounded unit safely. |
| `POST /jobs/{job_id}/retry` | Resume a recoverable failure without losing prior evidence; new attempt recorded. |
| `GET /sets/{set}/guides/{guide}/status` | Source availability, latest candidate/reviewed revision, job and coverage. |
| `GET /reconstructions/{revision}/scene` | Immutable revision; explicit review status. |
| `GET /reconstructions/{revision}/review-items` | Outstanding ambiguities, candidates and source references. |
| `POST /reconstructions/{revision}/corrections` | Typed mapping/pose/group command and expected base revision; creates new revision. |
| `POST /reconstructions/{revision}/review` | Decision plus actor metadata and evidence. UI actor and agent actor must remain distinguishable. |
| `GET /sources/{hash}/pages/{page_index}` | Root-confined local rendered page; no arbitrary URL/path fetch. |

Automated mode without configured provider credentials returns a specific provider-unavailable error or
creates an explicitly blocked job; it never falls back silently to a stored handcrafted scene.
Assisted mode can generate a review task with source pages and typed observations but must report assistance.

## Error envelope
```json
{
  "detail": {
    "code": "reconstruction_not_available",
    "message": "Official guide located; the 3D reconstruction has not been prepared yet.",
    "retryable": false,
    "job_id": null
  }
}
```
The starter provides code/message. M1 should normalise optional fields and request IDs consistently.
Use 409 for stale revision or not-ready scene, 413 for configured size limits, 422 for invalid data,
429 for local concurrency limits, and 503 for unavailable external providers. Do not leak raw provider responses.

## Concurrency and provenance
Use expected revision plus transactional updates for corrections. Duplicate idempotency keys return the
original operation result. A correction cannot mark a scene reviewed without the corresponding review event.
A restarted worker must recover a persisted job; in-memory background tasks alone do not satisfy this contract.
Cache and job state should reflect real stages, not a timer-based “AI processing” animation.
