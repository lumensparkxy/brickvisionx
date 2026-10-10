# Cloud website operations

Project: `lumensparkxy` (`989917723212`). Administrator: `maswadkar@gmail.com`.
New resources use `europe-west1`. Never change the existing `krishi-agent-service` or `(default)` database.

## Local setup and authentication

The approved SDK is installed under `var/tools/google-cloud-sdk`; no shell profile or system installation is required.

```sh
.venv/bin/python tools/install_cloud_sdk.py
export CLOUDSDK_CONFIG="$PWD/var/gcloud"
export CLOUDSDK_PYTHON="$PWD/.venv/bin/python"
var/tools/google-cloud-sdk/bin/gcloud auth login maswadkar@gmail.com --update-adc
.venv/bin/python tools/cloud.py preflight
```

Credentials stay in ignored local `var/gcloud`. Never upload or commit this directory, share auth files, or put credentials in the Codex model child environment. Authentication does not authorize tutorial publication.

## Infrastructure and code deployment

`deploy/settings.json` is the scoped resource configuration. Mutating commands require `--apply`; without it they print their intended scope.

```sh
.venv/bin/python tools/cloud.py provision --apply
.venv/bin/python tools/cloud.py budget --apply
.venv/bin/python tools/cloud.py deploy --apply
```

Provisioning uses dedicated named databases `guide2build` (release records) and `guide2build-requests` (request queue), three dedicated buckets, four service accounts and the `guide2build` Artifact Registry repository. It never selects the existing default database. The public portal has read-only release access and request-database write access. The uploader cannot write release records or public assets; the publisher cannot access the request database. No service-account keys are created.

The deploy command requires a clean local Git commit and runs local software checks. Cloud Build builds the Docker image remotely with a dedicated builder identity. It deploys IAM-private preview first and verifies public-mode routes before deploying the website. Existing public revisions are smoke-tested using a revision tag before traffic promotion. A failed public smoke restores recorded prior traffic; on the first deployment it removes public invoker access. No tutorial approval occurs during code deployment.

Runtime: one CPU, 512 MiB RAM, request billing, minimum0/maximum1 instance per service, concurrency40. Static frontend and small public API share a container. CPU may scale to zero while storage still incurs charges. No load balancer, Cloud CDN, always-on worker, GPU or database server.

## Preview and rollback

```sh
CLOUDSDK_CONFIG="$PWD/var/gcloud" CLOUDSDK_PYTHON="$PWD/.venv/bin/python" \
  var/tools/google-cloud-sdk/bin/gcloud run services proxy guide2build-preview \
  --project=lumensparkxy --region=europe-west1 --port=8080

.venv/bin/python tools/cloud.py rollback --apply
```

The preview requires your Google identity. The public portal has no correction, reconstruction, source-image or approval routes. Its catalogue uses only approved immutable release pointers.

Code rollback uses the exact traffic map saved in `var/evidence/cloud-release/guide2build-web-before.json`. It does not delete images or content. Tutorial rollback is separate; see `docs/RELEASE_OPERATIONS.md`.

## Cost alerts

On3October2026 the project Console created **Guide2Build conservative project cost alert**, budgetID `89e5ad10-dcf4-44ae-bc81-bdf2142b3068`, at **CHF8.26/month**, with50/80/100percent actual-spend alerts to project owners. The amount uses the2October2026 ECB USD/CHF rates for the USD10target. Evidence: `var/evidence/cloud-release/budget-created.jpg` and `budget-currency.json`.

The account permits project-scoped budget administration in the Console but denied billing-account BudgetAPI reads. The CLI therefore recognizes the recorded Console budget and does not create duplicates. Edit this existing budget through project Billing → Budgets & caps. Do not widen billing permissions just to automate an alert.

This conservative alert covers the **entire shared project**, including Krishi; it does not independently attribute only Guide2Build costs. Review labelled Cloud Run/Storage/ArtifactRegistry costs and the two named databases separately. Named Firestore databases have no free quota. Alerts are not a hard cap; public asset egress and repeated requests may still incur charges. No automated deletion or billing shutdown is configured.

## Verification evidence

Local deployment logs and cloud resource descriptions are under ignored `var/evidence/cloud-release/`. Source upload uses an explicit allowlist in `.gcloudignore`/`.dockerignore`; no `var`, PDFs, source crops, engine jobs, credentials or private evidence is uploaded.

IAM inspection confirms database-conditional roles. An authenticated uploader was allowed to read its request database and denied reads of both release/default databases. Direct impersonation of the portal for an additional probe was not granted: automatic approval review rejected that extra temporary privilege. Portal behavior is verified through the deployed service; no permission bypass is used.

## Deployed checkpoint

Public: https://guide2build-web-i2tso5lznq-ew.a.run.app

Private: https://guide2build-preview-i2tso5lznq-ew.a.run.app (Google IAM required; the documented local proxy was verified).

The first verified image was built from `c91669ec1dba0a0b01a938511ea6edb5d67fe2e8`, digest `sha256:b0abb031845d479c44ea8240a9da207a29002b0f0f9d6405c5c2fad196bde09e`. Source, tests and operations scripts have subsequent local checkpoints; no remote repository exists.

A successful build can be reused after deployment-tool/documentation-only repairs:

```sh
.venv/bin/python tools/cloud.py deploy --apply --build-id SUCCESSFUL_BUILD_ID
```

This rejects changes to uploaded application inputs and deploys the existing immutable digest. Normal deployment suppresses streamed build logs so structured output remains parseable; detailed build logs remain in Cloud Logging.

The real rollback drill passed: a second revision of the same image received traffic, then the original revision was restored and smoke-tested. The verification tag was removed. `var/evidence/cloud-release/rollback-exercise.json` records the tested/restored revisions. This is website rollback, not tutorial publication or tutorial-content rollback.
