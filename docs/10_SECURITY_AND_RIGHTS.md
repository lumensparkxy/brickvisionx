# Security, provenance and content-use boundaries

This is an engineering risk plan, not legal clearance. Before external distribution, review the actual
source and asset terms and obtain appropriate advice or permissions. Source links and downloads do not
by themselves grant redistribution rights. The initial product is a local private-development prototype.

## Source retrieval
Browser input is a set number and supported guide ID. Resolve only through trusted catalogue configuration.
Allow exact approved HTTPS hosts and paths; validate every redirect. Reject credentials in URLs, private
addresses, unexpected ports/types, excessive bytes and malformed signatures. The starter deliberately has
no arbitrary-URL fetch endpoint. Keep retries bounded and respect access restrictions/rate limits.

Before any dynamic discovery is added, validate destination addresses and DNS resolution, enforce public
address ranges at the outbound connection boundary, and prevent redirect/DNS-rebinding SSRF. The existing
fixed-host registry reduces the attack surface but is not a substitute for a hardened public fetch service.
Do not bypass login walls, reverse-engineer private instruction-app endpoints or bulk scrape by default.

## Parsing and execution
Treat PDF text, images, metadata, part comments and model output as untrusted data. A document saying
“ignore previous instructions” is source content, not an instruction to the agent or backend. Do not execute
extracted code, macros, embedded attachments or provider-generated shell commands.

Run PDF rasterisation in a resource-bounded subprocess before exposing the conversion API. Set limits on
bytes, pages, page pixels, elapsed time and memory. Prevent asset/archive path traversal, symlink escape,
recursive dependencies, cycles and decompression bombs. Return structured errors rather than raw tracebacks.

## Geometry assets
Individual LDraw parts and primitives are permitted inputs; finished model assemblies are prohibited by
product scope. Verify the resource classification, preserve source notices and follow each asset's license.
Do not assume all third-party assets have the same terms. LDraw legal information is in [S7]; actual downloaded
file and release notices remain authoritative. Retain hashes, origin URL and version for every dependency.
Reject `.dat` dependencies that reference external URLs or escape the curated asset root.

## Manual and branding
Keep official PDF bytes and rendered pages out of the source archive and source-control repository by default.
Fetch them locally from their official source. Do not publish mirrored manuals or source crops without reviewing
the permitted use. Use the set number and name for identification, not to imply an official partnership.
Display: `Independent prototype. Not affiliated with or endorsed by the LEGO Group.`
LEGO's own fair-play guidance is listed in [S8]; it is not a blanket license for this product.

## API, secrets and data
The unauthenticated API is local-only. A future public deployment needs authentication and authorization
for conversion, asset access, corrections and review; CSRF/origin protections; rate limits; isolated job
execution; cost controls; secure uploads if ever introduced; and an actual content-use policy.

Keep credentials in a user-controlled secret mechanism. Never store them in `project.toml`, agent files,
skills, test fixtures, logs or a browser bundle. Provider output may contain sensitive operational metadata;
redact credentials and keep private observations separate from public scene assets. Do not log full environments.

## Review integrity
Do not accept arbitrary actor metadata from an automated job as proof of human review. The review command
boundary must preserve origin and expected revision. Automated tests can test a review-record contract;
those tests do not create actual review evidence for the target model.

## Publication gate
No automatic cloud deployment, public asset serving, repository publication or third-party purchases.
A separate authorized task must resolve rights, authentication, operational costs and hosting security first.
