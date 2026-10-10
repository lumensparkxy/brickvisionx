# Alpha model production release

Date: 4 October 2026. Follow-up to the website-only deployment.

The 13 retained booklets across 10 sets are packaged as **unverified_alpha**, with exact canonical scene/final Three.js PNG bindings and audited individual-part geometry. All 13 first/final snapshot views loaded through the public UI in a read-only loopback inspection; no JavaScript/HTTP errors, private API calls or PDF/crop fetches were observed. Desktop and phone plane and Rivendell views were inspected.

The user explicitly approved publication of these exact 13 hashes via the campaign-hash question on 4 October 2026. All 13 are now public. Readback confirms the exact approved hashes in the live catalogue, publication heads and Google-authenticated approval records. The portal exposes 13 alpha models among 19 official booklet choices for the ten sets; the six remaining booklet choices retain their unavailable status. Assembly accuracy remains unverified; human review and physical build remain `not_run`.

The release code is pushed to private GitHub and deployed: commit `88e27ea6540c3f581a80cdb059260d80b0a20604`, public revision `guide2build-web-00008-vof`, 100% traffic, image digest `sha256:bc2569f37b8f73e35959f003345dcef5023d8d8380cc4dfcba20db82320229a6`. [GitHub CI 37184818332](https://github.com/lumensparkxy/brickguide-3d/actions/runs/37184818332) passed with 470 backend tests, 2 cache-dependent skips, 48 frontend tests and 17 software browser cases. The production desktop/phone portal smoke passed; private API/source routes remain 404 and unauthenticated private preview 403. All 13 public viewers passed first/final snapshot inspection, with exact release hashes and persistent unverified labels.

Campaign index SHA-256: `4bdd5f6ec3f9dc6ff64e60d9515d02f44d26b4c1f4596180627d505903d13f82`. This identifies `var/evidence/alpha-production/release-index.json`, including the 13 exact hashes below.

| Set / booklet | This booklet / cumulative snapshots | Release SHA-256 |
|---|---:|---|
| 30669 / alt-02 | 16 / 16 | `a536622614fb514be6eac7a8fa83a732d7e17907861654408538448fa3e13988` |
| 60400 / booklet-01 | 33 / 33 | `d5a1df2381108fb8fd8eeb4a5c3a3f4eeff177e1f74d42c2dc3eed7102a1c8f9` |
| 60400 / booklet-02 | 36 / 36 | `9e6cf34c43c216089e963a8ec4fbe8b0fd06fbfa34412d580d9c5b088422c108` |
| 31134 / booklet-01 | 78 / 78 | `c69dfaa57a350fed8ecc57d19934f80f47b0caab84091ac97a133703417b93e7` |
| 42163 / main | 88 / 88 | `629b8f5ac55c8950c8e0442e533e18bdd12163656cc1591ca8e2adda58b62366` |
| 76920 / main | 151 / 151 | `103abd9b7ff285e8ba7b84d30ce17a35d3ff38ff0471cd671a234215c70636fb` |
| 31129 / booklet-01 | 437 / 437 | `a2e9327f25f52633873cb66e9aa37e15d6a4da136ce1f9377422d60515da62a0` |
| 42171 / main | 462 / 462 | `a705bfe0631b831160531cb5270c6c290ff2a5a1a565d82749eec5520846f7dc` |
| 21343 / main | 444 / 444 | `8ccdae81bb7f1151bef919d186e9fdd66ffd0192fece4ef2426c8c8b440dbfdd` |
| 21061 / main | 393 / 393 | `6f1d436a3bc85ad5de20ecb45140c4606f17d34ef311fd8f286656550905540c` |
| 10316 / booklet-01 | 278 / 278 | `383baafde89c3b384834500f426a48def87028dc5c53c6f4e30fc3d954731717` |
| 10316 / booklet-02 | 255 / 533 | `242b8b9e8256f7136f9652f6a23057a272f32ca49265a732c69139030f6d0ad2` |
| 10316 / booklet-03 | 434 / 967 | `5176d0242cc7f75f4dde43a0c0a5690c91b22f8c0da3dee311d28fa7eee48cbe` |

## Verification and limitations

- Local software: 472 backend tests, 48 frontend tests, 36 browser tests passed; 3 optional performance audits skipped. Schema, Ruff, typecheck and production build passed. Independent security review cleared the tightened PNG, licence, alias, selected-booklet and catalogue integrity gates. All 13 actual bundles passed again with unchanged hashes. The 3 focused alpha browser cases passed again after the final label/parser changes.
- Live software/browser: Chromium 153.0.8010.12 loaded 26 first/final views across all 13 actual public releases. Plane and final Rivendell phone views passed at 390×844; desktop views used 1440×1000. JavaScript/console errors, HTTP error responses and application warnings were zero. Four Chromium GPU pixel-readback warnings are retained separately. Official booklet/page links, alpha provenance and component counts matched the manifests; private source/review routes and PDF/crop fetches were absent. Root visually inspected representative live plane, F1, Viking Village and both later Rivendell desktop views, plus plane/Rivendell phone captures. These are software/visual inspections by an agent, not human assembly acceptance.
- Actual bundles: 5835 files, 217169038 bytes total. The largest is 21061/main, 57123196 bytes. Each release stays within 512MB/22000 files; the largest file count is 1061.
- Frozen scene/checkpoint digests and original final render hashes match. Official PDF bytes were rehashed against existing source pins. No part identities, placements, assembly review or physical-test outcomes were changed.
- Accuracy remains unverified. Human assembly review and physical build are `not_run`; connector/assembly checks remain unchecked. These are PDF-assisted alpha reconstructions, not automatic successes or reviewed tutorials. Rivendell later booklets preserve cumulative prefixes; geometry component counts are not certified retail piece totals.
- Public exports contain snapshots, actual viewport PNGs, individual part closure, typed disclosures, coverage/validation summaries and sanitized attribution. Official manuals/crops, completion reports, engine jobs, private paths and credentials remain private. DAT source bytes retain their original CC BY4.0 or dual2.0/4.0 notices. LDConfig rights are recorded from its actual receipt without inventing an in-file licence.
- Scope/cost: existing dedicated Guide2Build resources only; no provisioning or inference. Private staging and public assets total 434338076 bytes. Transfers used 8 bounded workers; exact object generations/hashes and sequential compare-and-swap publication heads were verified. Existing min 0/max 1 Cloud Run and shared-project CHF8.26 budget alerts remain; alerts are not a hard billing cap.

## Evidence

- Exact releases and final scene/render bindings: `var/evidence/alpha-production/release-index.json`.
- Software logs: `software-check-verified.log`, `browser-software.log` in the same folder.
- Actual public UI inspection: `local-browser/report.json` and its 13 final desktop plus 2 phone screenshots.
- Security/cost plan: `security-cost-plan.json`; private transfer receipts: `staging-receipts.json`.
- Human distribution authorization: `authorization.json`; immutable public transfer/head receipts: `publication-receipts.json`; independent live catalogue, heads and approval readback: `final-state.json`.
- Production portal inspection: `production-alpha-portal-browser/report.json` and desktop/phone screenshots. The earlier warning-sensitive run is retained in `production-alpha-portal.log`; the verified run distinguishes four Chromium pixel-readback GPU warnings from zero application warnings.
- All 17 engine-job rows match the pre-release snapshot hash `a7864e489c989822a56b9e7d8fefeb4a8ed8f68609bb54478d475fbda02f8dd1` (`engine-preserved.json`).
- All 13 live viewer checks and screenshots: `production-model-browser/report.json`; live deployment after tag cleanup: `live-service-final.json`. Publication and browser commands exited successfully; earlier failure logs remain available.
- The temporary read-only inspection server on port 4186 was stopped after verification. The requested local engine preview at `http://127.0.0.1:4175/` remains available; no data was deleted (`service-cleanup.json`).

Local large-booklet 3 inspection took 51.2 seconds from the start of lookup through both first and final loaded views. This is one observed loopback software QA sample with concurrent tests, not a GPU or network benchmark.

Live Rivendell booklet 3 took 53.6 seconds from release lookup to first geometry readiness, and 73.7 seconds through both first/final views and phone inspection. Large models can load slowly. These are observed browser QA timings, not GPU measurements or a performance guarantee. Safari and real touch devices were not tested.

Temporary code-verification URL tags were removed after the canonical deployment passed; earlier revisions and immutable release assets are retained for rollback.

The final ledger and browser-warning diagnostics change documentation and verification tools only; those paths are excluded from the deployment build context. No further application deployment is required for that checkpoint. Reconstruction accuracy is the next iteration; no new inference or assembly corrections were performed during this publication.
