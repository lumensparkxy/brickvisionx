# Acceptance tests and completion evidence

## 1. Mandatory reporting rule
For every check, record **passed**, **failed**, **blocked** or **not run**. Include exact command or manual
procedure, environment, code revision where available, output and evidence path. Do not replace a missing
browser test with a unit-test result. Do not replace a missing reconstruction with a synthetic fixture.

The baseline fixture is an original structural example using set identifier 99999 and absent synthetic
geometry. It is never served as a supported set and never used as evidence for the official aircraft.
The starter Playwright tests mock API states; their passing result would not prove real-backend integration.

## 2. Source and catalogue

| ID | Check | Expected result |
|---|---|---|
| SRC-01 | Enter supported set and select guide. | Exact curated official source and distinct guide identity. |
| SRC-02 | Enter malformed/unsupported set. | Specific error; no guessed PDF, community fallback or fake model. |
| SRC-03 | Fetch actual PDF. | Hash matches downloaded bytes, signature/type/size checked, receipt retained. |
| SRC-04 | Redirect to private/external URL; HTML masquerading as PDF; oversize file. | Reject with bounded work and no secret disclosure. |
| SRC-05 | Render pages with a rotated page or different scale. | Stable index, dimensions, crop conversion and reproducible assets. |
| SRC-06 | Change source bytes under the same guide URL. | New source version; stale reconstruction not silently reused. |
| SRC-07 | Simultaneous downloads and interrupted cache write. | No corrupt final artifact; cleanup and retry are deterministic. |

## 3. Contracts and geometry

| ID | Check | Expected result |
|---|---|---|
| GEO-01 | Duplicate instance/step ID, unknown reference, missing pose, nonfinite coordinate. | Reject structurally. |
| GEO-02 | Non-unit quaternion or accidental scale/reflection. | Reject or normalise only through an explicit recorded adapter. |
| GEO-03 | Asymmetric real part through LDraw-to-canonical conversion. | Orientation/origin correct; no double coordinate conversion. |
| GEO-04 | Part metadata/asset missing or wrong. | Named mapping/asset issue; no generic-brick substitution. |
| GEO-05 | Compatible connection versus floating/noncompatible contact. | Connector result reflects the supported connector metadata. |
| GEO-06 | Stud/socket engagement versus unrelated penetration. | Narrower checks distinguish intended contact from collision. |
| GEO-07 | Visually similar candidates with hidden different connection. | Ambiguity retained unless evidence resolves it. |
| GEO-08 | Path escape in `.dat` dependency, cyclic references or huge expansion. | Root confinement, cycle/resource limits and a recorded error. |

Broad-phase bounding-box tests alone cannot pass GEO-05/06. A structural pass must leave geometry,
connector and physical check fields as `not_run` unless their actual checks were executed.

## 4. Step and BOM correctness

| ID | Check | Expected result |
|---|---|---|
| STEP-01 | Cover first four printed main steps and all internal callouts. | Source-aligned reconstruction for each, not four arbitrary frames. |
| STEP-02 | Build then attach the same subassembly. | Stable IDs; zero new pieces on attachment when appropriate. |
| STEP-03 | Quantity multiplier for repeated subassembly. | Separate physical instance IDs and correct total count. |
| STEP-04 | Seek forward/backward/reload/replay. | Exact same final poses and visibility; no accumulated transform drift. |
| STEP-05 | Compare parts callout with introduced instances. | Quantity/colour/part agreement; discrepancies become findings. |
| STEP-06 | Complete selected booklet. | Every original main step covered; microstep count reported separately. |
| STEP-07 | Compute complete BOM. | Count physical instances once, not screenshots; correct part/colour grouping. |
| STEP-08 | Update a reconstruction revision. | Progress key changes or migrates explicitly; old evidence remains traceable. |

## 5. Browser experience
Use a real running backend and local real-source assets for final integration tests, not only Playwright route mocks.
At desktop and phone sizes, test set lookup, loading, source failure, not-ready, review-needed, part-load failure,
callout microsteps, attachment replay, previous/next, final state and resume. Inspect console/network errors.
Test keyboard focus/navigation, meaningful labels, reduced motion and a WebGL-unavailable state.
Confirm no upload requirement, misleading completed model or default community/shopping navigation.

Required captures: lookup; source/preparation state; one early assembly; detached callout; attached callout;
review item; final reconstructed model. Capture both original guide crop and render for geometry checkpoints.
Screenshots from a generated mockup are not runtime evidence.

Measure cached load and orbit responsiveness on a documented machine/browser. Reopen the viewer repeatedly
and inspect resource growth. Performance targets are in the product spec and should be measured, not asserted.

## 6. Jobs, review and security
Test job lease recovery after process termination, idempotent duplicate submissions, cancellation between
stages, provider timeout/rate limit, absent credentials, malformed observations and budget exhaustion.
Test revision conflict, invalid correction, correction-history retention and revalidation of descendants.
An agent cannot set `actor_type=human` through its automated correction route.

Ensure the local static mount cannot access the SQLite database, source receipts, private observations,
`.env`, arbitrary local paths or external asset URLs. Validate path traversal, archive extraction and prompt
injection strings in document text. Server-side code must never execute extracted instructions.

## 7. Automatic conversion evaluation
A separately evaluated run starts with official source bytes and a generic parts catalogue, not the
accepted scene's poses. Log provider/model/prompt/solver versions. Save raw observations and candidates.
Compare raw and corrected outputs separately. Report exact part-ID, colour, pose, step-membership and
subassembly-group matches; report numerator/denominator and every manual correction.

Do not claim measured accuracy without an evaluation corpus. One successful small source is one successful
case, not a general conversion rate. An agent-authored reference is not independent human ground truth.
Blocked inference does not block software unit testing, but it blocks an automatic-conversion success claim.

## 8. Human and physical verification
Agent comparison with rendered source pages can establish an **agent-reviewed** reference. A human review
requires an actual recorded human action for that revision. A physical-build pass requires somebody actually
building the model and recording the result. Leave these states unverified when unavailable; do not fabricate them.

## 9. Final report template
Use `execution/VALIDATION_REPORT.md` and include scope, exact source hash, main/microstep coverage,
parts coverage, scaffold/software/reference/automatic/human/physical statuses, commands and results,
source-render comparisons, corrections, limitations and reproducible startup instructions.
