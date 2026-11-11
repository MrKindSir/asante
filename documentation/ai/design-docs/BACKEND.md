# Asante backend feature specification

Target blueprint, 2026-11-07. Feature IDs/dependencies/statuses are controlled by [PLANS.md](../exec-plans/PLANS.md). This file specifies the backend work still needed; it does not describe all of it as already implemented.

## Current implementation and target boundary

Current entry point: `app/services/api/asante_api/main.py`. The public catalogue reads PostgreSQL/PostGIS; profiles, saved project revisions, upload metadata, immutable submission packets and review decisions now persist in PostgreSQL. Published media URLs resolve a story in PostgreSQL and stream its stored object key from private MinIO with GET/HEAD and single byte-range support. The versioned synthetic MP3 is copied to MinIO by the explicit `python -m app.db.seed_media` setup command. Contributor recordings now upload through expiring same-origin owner-scoped API intents, are probed/hashed server-side and stored in private MinIO. Local email/password accounts and server-owned contributor/reviewer roles now control private access; the old reviewer key no longer grants access.

Keep one modular FastAPI service. Extract routers, schemas, domain services, persistence adapters and worker handlers only as their feature is implemented. Put migrations/seeds in `app/db`, reusable external adapters in `lib/sdk`, infrastructure in `infrastructure`. Do not scaffold a network of services.

## AS-00 — application boundaries and contract migration

- **AS-00.a:** make `main.py` assemble the app; move coherent behavior into small modules in the same package. Domain functions must not depend on FastAPI requests or global mutable lists. Keep legacy fixtures and endpoints working during extraction.
- **AS-00.b:** establish typed repository/provider interfaces, explicit configuration and test factories. API errors have safe public messages and trace IDs; logs must not contain keys, raw media, transcripts or listener coordinates.
- Keep current `/v1` snake_case routes compatible while existing clients use them. Target integrated routes use `/v2`, camelCase JSON/query fields and Python snake_case internally with explicit Pydantic serialization aliases. TypeScript internal names are camelCase. Do not silently change case on a current route.
- The public proxy prefix remains `/asante/api`; FastAPI routes omit that prefix. Generate/validate client types from the target OpenAPI schema. Keep the v1/v2 mapping in the frontend API adapter until migration completes.
- Tests: legacy contract regression, target JSON casing, schema rejection, safe error payload and trace propagation. Remove v1 only in a separately reviewed cleanup after every caller and setup test has migrated.

Target error shape:

```json
{
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "This story changed. Refresh before saving.",
    "fields": [],
    "traceId": "uuid"
  }
}
```

Use 401 for no valid session, 403 for insufficient role, 404 for inaccessible/absent owned resources, 409 for version/state/idempotency conflicts, 422 for invalid input, 429 for quota and 503 for unavailable dependencies. Do not expose another contributor's resource existence through detailed errors.

## AS-01 — PostgreSQL/PostGIS persistence

**AS-01.a: connection, migration runner, first schema.** The initial implementation uses SQLAlchemy's async engine/sessionmaker with Psycopg 3's async driver and pinned dependencies. `asante_api.database.get_session` yields one request/job-scoped session; no mutable session is shared between concurrent jobs. `app/db/migrations` owns the Alembic async migration environment, and the API image includes that migration tree. Migrations are explicit commands, not API startup side effects. The first revision creates the `asante` namespace and enables PostGIS without claiming feature-owned tables. See [SQLAlchemy session guidance](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) and [Alembic migration workflow](https://alembic.sqlalchemy.org/en/latest/tutorial.html).

**AS-01.b: repositories, reproducible seeds and restart verification.** Replace one fixture-backed feature at a time. Migrations run as an explicit setup/CI step, not opportunistically in every web worker. Seeds have stable identifiers and a demo marker; rerunning them must not overwrite contributor records. Use a distinct disposable test database.

Required tables are introduced by their owning slices, not all in the first migration:

| Entity | Minimum columns / constraints | Owner feature |
|---|---|---|
| users / role memberships / sessions | UUID; identity issuer+subject unique; role allowlist; revoked/expired sessions | AS-02 |
| contributor_profiles | user FK; display/attribution names; bio; language preferences; version | AS-07 |
| landmarks | UUID; name/region; public location `geography(Point,4326)`; GiST index | AS-03 |
| story_projects / project_revisions | owner FK; stable project ID; revision number unique per project; immutable content snapshot; optimistic version | AS-07/08 |
| contributions / consent_records | revision, contributor, scope, approved attribution, consent text version, grant/revocation times | AS-08 |
| media_assets / media_derivatives | owner/revision; private object key; MIME/bytes/hash/duration; verification and processing states; unique derivative identity | AS-09/10 |
| worker_runs / job_attempts | revision/input hash; worker/schema/prompt versions; status; attempts/lease; safe errors and usage | AS-11 |
| claims / sources / claim_source_links | claim type/text; source URL/publisher/dates/excerpt/hash; relationship and reviewer interpretation | AS-12/14 |
| transcripts / translations | asset/revision; original or target language; timed segments; source revision; review state and provenance | AS-13 |
| submissions / review_decisions | immutable packet; revision/packet hash; reviewer/reason; expected version; guideline version | AS-14/15 |
| publications / audit_events | approved revision and decision FKs; visibility/revocation; actor/action/time; append-only event | AS-16/08 |

Use UTC timestamps, foreign keys, parameterized SQL and explicit uniqueness constraints. JSONB is suitable for versioned worker payloads/packet snapshots, not a substitute for ownership FKs, searchable statuses or media verification columns. Preserve immutable original object references and content hashes.

Done: migrate an empty DB, migrate again with no change, seed twice without duplicates, reject broken FKs, restart the API and retrieve the same data, and prove test DB isolation. Never reset a developer database to make tests pass.

## AS-02 — identity, sessions and authorization

**AS-02.a:** implement the identity boundary with an OIDC adapter and local server-side sessions. Provider selection, issuer/client configuration and recovery/email setup are product/environment decisions. Use a fake issuer in isolated tests; it must not be available in normal runtime configuration. Sign-in/sign-up/recovery routes delegate to the selected provider. Validate state, nonce, issuer, audience and PKCE before creating a session.

**AS-02.b:** enforce contributor ownership and reviewer/publisher capabilities server-side. Default new users to contributor; privileged roles require an administrative grant. Reviewer keys are allowed only in explicit local prototype mode and cannot coexist as a production bypass.

- Use an opaque, rotated, revocable session ID; store its digest server-side. Put it in a same-origin HttpOnly cookie with explicit SameSite, path and lifetime. Use Secure cookies under deployed HTTPS; local HTTP exceptions are explicit development configuration. Return `Cache-Control: no-store` for private/session responses.
- Protect cookie-authenticated mutations against CSRF; validate Origin and a session-bound CSRF token. Do not treat SameSite alone as the entire policy. See [OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
- No session/access/reviewer keys in localStorage, page URLs or browser logs. Logout revokes the server session. Roles and project owner IDs come from server identity, never the submitted display name.
- Tests: contributor A cannot read/change B's project/upload/run; contributor cannot review; revoked/expired sessions fail; callback replay fails; CSRF fails; reviewer role is not self-assignable. Provider failure keeps the contributor's unsent work intact.

## AS-03 — public catalogue and geospatial queries

**AS-03.a — automated-verified:** persist the public landmark/story projection in `asante.landmarks` and `asante.stories`, with WGS84 PostGIS `geography(Point,4326)` and a GiST location index. The insert-only `python -m app.db.seed` command uses stable IDs for the current demo catalogue and is safe to rerun. Keep existing `/v1` field names and response shape while switching catalogue, nearby and media-availability reads to PostgreSQL. This slice does not persist submissions or contributor-owned drafts. Migration/seed behavior and API compatibility pass against an isolated PostGIS database; local activation requires the explicit migration, catalogue seed and media seed described in the bootstrap prompt.

**AS-03.b — automated-verified:** `GET /v2/landmarks`, `GET /v2/stories` and `GET /v2/stories/nearby` provide cursor-paged public catalogue reads. Pages default to 20 items and cap at 100. Story filters include `search`, `language`, `region` and `mediaFormat`; both catalogue routes accept `bbox=west,south,east,north`, including antimeridian-crossing bounds. Supplying latitude and longitude together adds distance annotations and nearest-first ordering with a stable slug tie-break; it does not silently restrict the global catalogue. Nearby stories are an explicit radius query. Cursor pages, filters, date-line bounds, distance and nearby paging are covered by the isolated PostGIS integration test. Existing `/v1` endpoints remain the current website contract. Local activation and live evidence are tracked in PLANS.md.

- Default catalogue is globally accessible and contains only active published revisions. Optional listener latitude/longitude must be supplied together; they add distance/order, not an implicit radius filter.
- Nearby mode is a separate explicit query. Use WGS84 longitude/latitude order and metre units. `ST_DWithin` on geography supports metre distances and index-aware filtering; see [PostGIS reference](https://postgis.net/docs/ST_DWithin.html). Use stable ID tie-breaks in pagination.
- Map viewport bbox filtering follows the area being explored, not the listener's physical location. Handle an antimeridian-crossing bbox as two intervals. All published places remain reachable through paging/search.
- Proposed defaults: page size 20, maximum 100; nearby radius maximum 500 km. These are product limits with explicit validation. The global catalogue must not inherit that radius cap.
- Public response omits owner email, drafts, reviewer identity, private source notes, storage keys, consent documents and job inputs. Public coordinates may be generalized for sensitive places; retain precise contributor location privately.
- Avoid storing/logging listener coordinates in request logs, analytics or worker traces. Redact relevant query fields at the proxy/API.
- Tests: same public story IDs from no coordinates, London and Sydney; remote playback allowed; stable pagination; latitude/longitude bounds; metre-versus-degree boundary; private drafts never leak; withdrawn revisions disappear.

## AS-07 / AS-08 — projects, consent and authorship

- **AS-07.a:** authenticated profile CRUD and owner-filtered project list/create/detail. Explicitly offer migration of a local draft to the signed-in account; preview what will be sent.
- **AS-07.b:** revision saves, rename/duplicate/archive and optimistic concurrency. Use expectedVersion on updates; return 409 rather than overwrite a newer edit. A duplicate gets a new project ID, draft status and no copied submission/approval/consent.
- **AS-08.a:** immutable revision snapshots and contribution records. Model creator, translator, editor and researcher contributions separately. AI assistance is recorded as assistance, not silently attributed as a human author.
- **AS-08.b:** versioned consent scopes: storing original media/location, processing with external Asante services, publication and approved attribution. Record purpose, revision and policy text version. Revocation is a new record, not deletion of prior evidence.
- Only a contributor can approve their contribution/attribution changes. Reviewer feedback does not grant permission to rewrite the original. Editing submitted/published content creates a new revision and invalidates prior readiness/approval for that revision.
- Tests: restart persistence; owner isolation; save conflict; duplicate resets gates; revocation blocks future use; original hash unchanged after transcript/translation edits; local import requires explicit consent.

A project has mutable organizational metadata such as name/archive state. Story content belongs to immutable revisions. Saving content appends a revision and updates latestRevisionId/version atomically; it never PATCHes a frozen content row. Start with explicit Save, not a new revision on every keystroke. A consent or approval references that exact revision.

## AS-09 — actual media upload

**AS-09.a:** owner-scoped upload intent and a short-lived presigned PUT/POST to a private MinIO bucket. Server assigns a random object key tied to project/revision. Prototype limits are audio <=100 MiB and video <=500 MiB, with MP3/WAV/OGG audio or MP4/WebM video and a five-minute upload expiry. Enforce the chosen signing method's limits server-side; client checks alone are insufficient.

**AS-09.b:** completion/verification endpoint. Check object existence, bytes, detected media type, duration and server-computed SHA-256 before setting verified. Browser-provided checksum/name/MIME are claims, not proof. Stream hashing rather than loading the full asset into API memory. Expired, wrong-owner, truncated, oversized and format-spoofed uploads fail with actionable status.

The browser needs a reachable storage origin, not a Docker-only host such as `minio:9000`. Prefer a local proxy storage route with exact CORS/origin and signature-preserving Host/path configuration; document any deliberate storage-port exception. Do not commit an integration that works only inside the Docker network.

Cancel/expiry leaves a cleanup candidate, not a published asset. Cleanup deletes only unreferenced expired staging objects after a grace period; never original/published/referenced objects.

Done: browser-origin upload contract verified with a real MinIO test, server verification cannot be forged, cancellation/retry does not duplicate assets, and originals remain private.

## AS-10 — media processing and delivery

- **AS-10.a:** bounded ffprobe/ffmpeg processing job: type/duration/dimensions, normalized speech audio, video poster and caption references. Use fixed argument lists, no shell interpolation; cap duration, resolution, subprocess time and memory.
- **AS-10.b:** progressive audio with range support; streamable MP4 or HLS renditions for video as needed. Do not reencode on every request. Save derivative profile/version and original hash for deterministic reuse. Bound initial video profiles; never upscale a lower-resolution original.
- Suggested initial processing limit: 10-minute media; show the limit before upload. Confirm and record limits when real demo videos are supplied.
- Delivery checks publication/role at each request. Use a same-origin media route with Range/HEAD/416 and cache policy, or carefully scoped short-lived access. A guessed MinIO key is not authorization.
- HLS manifests and segments use the same active-published-story authorization policy through `/v1/stories/{story_id}/hls/{name}`. Playlist segment references are rewritten to same-origin routes. A public CDN or presigned URL can outlive withdrawal; do not promise immediate revocation if choosing it. Keep revocable content on authorization-checking routes without public immutable caching.
- Processing states: `uploaded → verifying → verified → processing → ready`, with explicit `failed` and retry states. Upload completion alone cannot mark ready.
- Tests: actual audio/video fixture probe, corrupt/oversized input, timeout, one derivative per input/profile, valid 206/416, seek, media MIME, missing poster/caption, no private original retrieval, withdrawn delivery denied.

**AS-13 media jobs (draft upload + submit):** verified audio/video uploads enqueue capped `transcribe` and `translate` immediately (`submission_id` null); video also enqueues `analyze`. Submit promotes matching draft jobs for the same upload, then ensures assessment and any missing media jobs. Caps come from `asante_api/ai/caption_limits.py` (live defaults 45 seconds / 12 cues when `ASANTE_AI_BACKEND=modal`; localhost defaults 180 / 100). Live transcription/translation/vision use Modal via `live_modal.py`; localhost uses host Ollama + local Whisper. Compose runs the API image as a separate `job-worker` process. Drafts and job state persist in `processing_jobs.result_payload`, project onto contributor workspace drafts (`mediaJobs`, `transcriptDraft`, `translations`), and appear beside (not into) the frozen packet for the review dashboard. No job publishes or rewrites the narrative/original. `scripts/asante/backfill_draft_media_jobs.py` enqueues jobs for older drafts that already have verified media. Broad retry/cancel controls remain unfinished. See [ASANTE_AI_RUNTIME.md](ASANTE_AI_RUNTIME.md).

## AS-14 — submission and guideline checks

**AS-14.a:** freeze a revision into an immutable packet; store hash, contributor approval and referenced asset/worker versions. Authorize owner, validate expectedVersion, deduplicate Idempotency-Key per actor+operation+payload. Do not accept an arbitrary client-provided packet as a verified server snapshot.

**Implemented slice note (2026-11-10):** `GET /v1/submissions/preview/{project_id}?expected_version=N` builds the server preview from the saved revision and returns a stable `preview_hash`; `POST /v1/submissions` accepts that hash and rejects changed snapshots. The packet copies the revision content, plan, report, research source metadata, contributor decision, attribution, consent scope, original/derivative refs, and only planner/researcher run IDs/traces for that project. Assessment/transcript/video-analysis outputs remain in `processing_jobs.result_payload`; packet output joins them without changing packet JSON. Consent scope and reviewer `assessment_version` are additive migration fields. The existing project ZIP download route remains owner-scoped and excludes internal object keys.

**AS-14.c bounded assessment:** every submission receives one unique `assessment` job. It computes deterministic provenance/readiness and submits only frozen narrative/report/source excerpts to the configured provider for claim/evidence comparison. The output schema is `asante.assessment.v1`, prompt version `claim-evidence.v1`; each result stores submission/revision IDs, SHA-256 input hash, job/trace IDs, provider/model or deterministic mode, state, findings/cited submitted source IDs and exact excerpt spans, uncertainty, safe error and timestamp. Provider failures distinguish timeout, provider unavailable and malformed output. Citation IDs must resolve to submitted source records and excerpts must be substrings of their submitted text. Personal-memory/oral-history claims cannot be contradicted merely due to missing online corroboration. Source retrieval states include search snippets, social catalogue entries, metadata, news headlines and retrieved page excerpts. Repeated identical references share a duplicate group. No authenticity score or verdict is produced.

**AS-14/15 review policy:** `asante.review-policy.v1` is server-owned and powers both reviewer packet findings and `POST /v1/review/{submission_id}/decision`. Technical/consent blockers and pending/failed/unavailable required assessment block approval. Completed claim findings remain attention for a human decision. Escalate is the available human path for a terminal unavailable/invalid assessment. Keyword-based or model heritage relevance can only produce attention; no automatic rejection occurs from missing keywords or model uncertainty. Review decisions store reviewer identity, reason and assessment policy version. This slice does not claim complete Idempotency-Key semantics, live-provider evaluation, or production readiness.

Packet fields: projectId, revisionId, owner/contributor references, title/summary, approved attribution, scoped consent refs, landmark/public and private location refs, originalLanguage, translation refs, original/derivative media refs with readiness/hash, transcript refs, typed claims, source/link refs, worker run refs, unresolved questions, guidelineVersion and packetHash.

**AS-14.b:** evaluate deterministic guideline findings, separately from AI interpretations:

| Check | Block publication | Attention requiring reviewer explanation |
|---|---|---|
| Owner/attribution/consent | Missing, revoked, unapproved attribution or wrong revision | Contribution dispute escalates |
| Media | Missing, unverified, failed processing, checksum mismatch, unavailable required playback | Optional derivative missing |
| Original language/narrative | Missing required language/original references | Translation uncertainty, incomplete transcript |
| Claims/evidence | Invalid/unsafe source record or mandatory review incomplete | Unsupported/conflicting evidence; personal memory/oral history classification |
| Version integrity | Packet changed, stale approval or duplicate conflicting decision | New evidence after packet freeze requires a new packet |

No numeric model confidence can override a blocker. A single URL does not verify a claim. Source scarcity must not automatically invalidate oral history; record claim type and uncertainty.

Tests: missing consent scope, missing media, revision linkage, provider timeout/unavailable/malformed response, fabricated citation, evidence-bound outcomes, oral-history preservation, duplicate retry and immutable packet hash. PostgreSQL/MinIO isolation, lease/restart exhaustion and live-provider evaluation still require the explicitly named integration/browser checks.

## AS-15 / AS-16 — review, publication and correction

- **AS-15.a:** reviewer-only queue/detail with packet, media, claims, sources, guideline findings, contribution history and worker traces.
- **AS-15.b:** reasoned decisions against packetHash and expectedVersion. Actions approve/request_changes/reject/escalate. Reject is terminal for that submitted revision. Request changes creates feedback; contributor resubmission is a new revision/packet. Preserve the previous decision.
- **AS-16.a (current partial):** reviewer approve on the exact packet revision publishes that packet into the public catalogue (story slug, transcript, optional translation) and attempts an admin publication email. Blocking findings still prevent approval. Workers cannot publish. Concurrent/stale decisions return 409. A later dedicated publication resource/audit table remains desirable; withdrawal/correction are not done.
- **AS-16.b:** owner withdrawal, correction requests and revised submissions. Withdrawal disables catalogue and media delivery and schedules cleanup only according to retention policy; retain private audit evidence. A correction does not silently replace the approved original; the new revision needs review.

State transitions (server-authoritative):

```text
draft → submitted/pending_review → approved → published
                              → changes_requested → new draft revision → submitted
                              → escalated → pending_review (reasoned human reassignment)
                              → rejected (terminal for this submitted revision)
published → withdrawn
published → correction_requested → new draft revision (old version remains explicit)
```

The current review desk uses a deliberate combined approve-and-publish flow: catalogue visibility is updated only for the exact approved packet/revision, and workers still cannot publish. A fuller split between approval decision and publication resource remains future AS-16 work alongside withdrawal/correction.

Tests: contributor cannot publish, stale decision, simultaneous publish, duplicate action, revoked consent race, missing derivative, withdrawal prevents seek/new segment requests, rejected old revision retained, new revision not public until approved.

## Target API inventory

Rows marked **implemented** are available in source; runtime setup requires the explicit migrations and seeds described in the bootstrap prompt. Prefix with `/asante/api` in the browser.

| Routes | Required access / contract owner |
|---|---|
| GET /v2/landmarks; GET /v2/stories | **Implemented, AS-03.a/b:** public published projection, cursor paging, filters and optional bbox/distance |
| GET /v2/stories/nearby | **Implemented, AS-03.a/b:** explicit radius query and cursor paging |
| GET /v2/stories/{storyId} | Planned: public published story detail; AS-03 |
| GET /v2/auth/login; GET /v2/auth/callback; POST /v2/auth/logout; GET /v2/me | OIDC/session boundary; AS-02 |
| GET/PATCH /v2/profile; GET/POST /v2/projects; GET/PATCH /v2/projects/{projectId} | Owner profile/projects; AS-07 |
| POST /v2/projects/{projectId}/revisions; GET /v2/projects/{projectId}/revisions | Versioned owner content; AS-08 |
| POST /v2/projects/{projectId}/consents; POST /v2/consents/{consentId}/revoke | Contributor-scoped consent; AS-08 |
| POST /v2/projects/{projectId}/uploads; POST /v2/uploads/{uploadId}/complete; GET /v2/uploads/{uploadId} | Owner upload lifecycle; AS-09 |
| POST /v2/projects/{projectId}/runs; GET /v2/runs/{runId}; POST /v2/runs/{runId}/cancel | Owner/reviewer worker access; AS-11 |
| POST /v2/projects/{projectId}/suggestions/{suggestionId}/decision | Explicit accept/edit/reject; AS-12 |
| POST /v2/projects/{projectId}/submissions; GET /v2/projects/{projectId}/submissions | Owner versioned packets; AS-14 |
| GET /v2/review/submissions; GET /v2/review/submissions/{submissionId}; POST /v2/review/submissions/{submissionId}/decisions | Reviewer role; AS-15 |
| POST /v2/publications; POST /v2/publications/{publicationId}/withdraw; POST /v2/stories/{storyId}/corrections | Publisher or owner/authorized correction role; AS-16 |
| GET/HEAD /v2/media/{assetId}/playback | Public approved derivative or authorized private review; AS-10/16 |

Collections return `{ items, nextCursor }`. Mutations return resource IDs, version, state and traceId. PATCH/review/publication requests specify expectedVersion; retryable creation/submission/publish routes require Idempotency-Key. Resource-specific schemas and OpenAPI contract tests must precede client integration.

### Shared field shapes to freeze before client work

New resource IDs are UUID strings; versions are positive integers; timestamps are UTC ISO-8601 strings; content/packet hashes are SHA-256 hex. Language codes come from the evaluated capability registry. Coordinates use named latitude/longitude fields, with GeoJSON arrays ordered longitude then latitude.

```text
Catalogue query:
  cursor?, limit=20 (1..100), q?, language?, region?, mediaType?,
  bbox? [west,south,east,north], latitude? + longitude? as a pair
Public story:
  storyId, revisionId, title, approvedAttribution[], originalLanguage,
  landmark { landmarkId, name, region, latitude, longitude, precision },
  distanceMeters: number|null, media { mediaType, state, playbackUrl?, posterUrl?,
    availableRenditions[], transcriptId?, captionLanguages[] },
  availableTranslations[], publishedAt, isDemo
Revision save:
  expectedVersion, parentRevisionId|null, content {
    title, summary, narrative, landmarkId, locationPrecision,
    originalLanguage, mediaType, audience, sensitivity, contributionRefs[]
  }
Upload intent request:
  revisionId, fileName, declaredMimeType, byteSize, clientSha256?, consentId
Upload intent response:
  uploadId, assetId, method, uploadUrl, requiredHeaders, expiresAt, limits
Upload complete request:
  expectedVersion, clientSha256?
Submission create:
  revisionId, expectedVersion, consentIds[], attributionApprovalIds[]
Submission response:
  submissionId, revisionId, packetHash, status, version, findings[], traceId
Review decision:
  expectedVersion, packetHash, action, reason
Publication create:
  submissionId, revisionId, approvalDecisionId, expectedVersion, packetHash
Finding:
  checkId, status: pass|attention|blocked, reasonCode, message, references[]
```

These shapes are target contracts. Serialize optional absent fields consistently as omitted except explicitly nullable fields. A private packet has richer authorized records; do not reuse its schema as the public story response. Resolve owned IDs server-side before constructing any upload/job/submission.

## AS-17 — runtime and delivery

**AS-17.a:** keep CI, migrations, demo seeds, integration services, unit/functional/HTTP/Playwright runners, type checks and production compilations aligned. Prove a fresh clone starts using BOOTSTRAP_PROMPT without the original developer's shell variables or cached images. External AI credentials are optional for fixture CI.

**AS-17.b:** after target host/domain/registry are chosen, implement deployment environment, least-privilege credentials, migration rollout, health verification and a rollback/restore rehearsal. Record manual approval points and test on a disposable target before a public release.

Use a modular API plus, when durable media/AI jobs arrive, one Asante worker process from the same code/image with a different command. PostgreSQL stores jobs and leases; no broker is required for the first workload. Update Compose/health/readiness, migrations and bootstrap together.

The chosen deployment target gates production configuration: HTTPS, session/key delivery, database backups and restore test, private storage, worker limits, health probes, schema rollout and rollback. Never use Compose `down -v` as an ordinary developer setup/recovery step. CI may remove its own disposable volumes.

Every backend slice adds unit/domain cases, feature-level API cases and required real PostgreSQL/MinIO integration cases. SQLite and mock S3 results alone do not establish PostGIS or MinIO correctness.

### Current public media delivery boundary

The website receives `/asante/api/v1/stories/{storySlug}/media`, never a MinIO URL, bucket or object key. Each GET/HEAD checks the active published story and landmark in PostgreSQL before using the database-selected object key. MinIO stays private; its credentials remain in the API environment. The API streams 64 KiB chunks, forwards validated byte ranges as bounded object reads, returns 206/416 for seeking, and closes storage connections. Missing/unpublished stories return 404; unavailable storage returns a safe 503. Responses use `Cache-Control: no-store` so withdrawal is checked on the next request. Contributor originals also use private MinIO streaming. Upload-time AS-10 probe/audio/poster/keyframe derivatives are present; audio-only uploads receive deterministic decorative SVG cover art and video uploads receive an extracted JPEG frame. Published poster requests use `/v1/stories/{storySlug}/poster` and database-selected `stories.poster_file` references. Translated caption choices are served separately from `/v1/stories/{storySlug}/captions`; the API returns only bounded, validated timed cues from `stories.caption_tracks` for an active published story. Catalogue list responses do not include full caption tracks. The idempotent media seed backfills missing public demo poster references/objects and extracts a frame for the seeded video example when its fixture is available. Broader HLS listener delivery remains open. `/health` is liveness; `/health/ready` checks the catalogue table and configured bucket.

## Implemented local contributor persistence contract (2026-11-07)

Migration `0003_contributor_workspace` adds contributors, hashed workspace sessions, projects, immutable project revisions, uploads, submission packets and append-only review decisions. Profile content and project snapshots use bounded Pydantic-validated JSONB; IDs, ownership, versions and links are relational. This is the current local integration, not completion of the target account/OIDC schema. Private device sessions are HttpOnly/SameSite=Strict with a 90-day server expiry; losing the cookie does not delete DB records, but account recovery/cross-device sign-in remains unimplemented. No identity is inferred from a submitted email.

Current `/v1` routes: POST workspace/session; GET workspace; POST workspace/profile, workspace/projects, workspace/preferences, workspace/import; GET workspace/import-receipt/{checksum}, workspace/browser-backup; POST uploads; PUT uploads/{id}/content; GET/HEAD uploads/{id}/media; POST submissions; GET review/queue; POST review/session, review/{id}/decision; GET/HEAD review/{id}/media. Prefix them with `/asante/api` in the browser. Project writes use `version`; submission uses `project_id`, `expected_version`, `consent_given`; reviewer decisions require `expected_version`. Old free-form submission bodies are intentionally replaced by server-owned project/revision references.

Owner mutations require the workspace cookie, `X-Asante-Request: 1`, and an exact same-origin check when Origin is present. Private responses are no-store. Foreign project/upload IDs return 404. Saved edits create revisions and reject stale versions with 409. Submitted projects are frozen; duplication creates a new draft without attached uploaded media, submission or consent. Submission stores original attribution, original text, consent and verified media metadata. Review locks the packet and appends a decision. Approving a packet now publishes a public catalogue story and attempts an admin publication email (AS-16 partial); withdrawal and correction remain open. Reviewer keys and ten-minute signed HttpOnly review-media cookies are development-only, separate from contributor sessions.

Upload transport decision: for the current local stack, a five-minute owner-scoped same-origin API upload URL replaces direct browser-to-MinIO presigned transfer. The API caps bytes at the declared size and applies the 100 MiB audio / 500 MiB video limits, probes actual format and duration (up to 600 seconds) using ffprobe with a timeout, computes SHA-256 server-side, and writes a random immutable original key. It supports MP3/WAV/OGG and MP4/WebM. An OS temporary file is needed for probing and is automatically unlinked after success/failure; it is not persistent media storage. Expired/incomplete/oversized/spoofed/wrong-owner requests fail; replays of completed intents fail. Durable job cleanup for expired staging records/orphan objects and derivative processing remain future work.

The explicit browser import action archives exact captured Asante local/session storage values in private MinIO, imports typed records/preferences into PostgreSQL, verifies DB readback and archive SHA-256, and then removes only unchanged captured Asante values. Imported old submission IDs are retained in the archive, never promoted into verified submissions. Import resets submission consent and media references. A conflicting existing server draft/profile stops import and preserves browser data. A cookie is preserved during cleanup. The archive can be downloaded through the authenticated workspace backup route. No browser file bytes existed in the old preview flow, so files must be selected once for their first actual upload.

## Implemented local account authentication and profile links (2026-11-07)

This supersedes the device-only contributor and shared-key reviewer access described in the earlier implementation history. The current user-authorized local account path uses POST `/v1/auth/register`, `/login`, `/logout` and GET `/me`. Registration requires explicit consent, normalizes email, enforces 12–128 character passwords, and always creates a contributor. Roles cannot be supplied through registration/profile edits. Passwords use salted Argon2id (19 MiB, two iterations, one lane), following [OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) and the [argon2-cffi API](https://argon2-cffi.readthedocs.io/en/stable/howto.html). Unknown and wrong-password login failures use the same safe message; ten failures per normalized identity in fifteen minutes trigger a persisted 429 limit.

Migration 0004 introduces accounts, account_sessions and login_attempts, adds nullable contributor ownership to legacy public story projections, and records reviewer_id on new review decisions. A random opaque seven-day HttpOnly, SameSite=Strict cookie points to a SHA-256 session digest in PostgreSQL; HTTPS cookies are Secure. Login rotates the current browser session, logout revokes it, and expired/revoked tokens cannot authorize requests. Mutation headers and same-origin checks remain mandatory. Passwords/hashes/session tokens never appear in profile/catalogue responses or browser storage. Provider SSO, email verification and email recovery remain pending; local password sign-in is implemented and restores data after browser cookies are lost.

Contributor routes require contributor accounts. Review queue, decisions and review-media GET/HEAD require a reviewer account on every request. The former `ASANTE_REVIEWER_KEY` and signed key cookies are no longer accepted; existing environment secrets were preserved but are unused by review authorization. New decisions retain the acting reviewer's account ID. Device sessions remain available for public listener preferences and for explicit linking of a currently controlled legacy workspace during registration. Linking revokes the legacy device capabilities; an email/name match never assigns ownership. Logging into an existing account does not silently absorb another device workspace.

### Current plan document and sharing API (AS-07/08 extension)

`asante_api.plan_documents` builds a bounded field-report document from the project’s persisted planner plan and researcher packet. It does not rerun either worker or synthesize evidence. The structured model supports sections, attributed HTTPS images/sources, tables and simple chart data, and is rendered as PDF, plain text or JSON. Authenticated project routes provide document read/save/export and share/collaborator management. Saves use project ownership/version checks and submitted-project freeze rules. Existing migration `0011_plan_shares` supplies `plan_shares` and `plan_collaborators`; ORM records now match that schema, so this feature adds no migration.

Share tokens are random capabilities. Public token GET returns the saved report and export formats without exposing the private project. A signed-in owner/editor may save through the token route; anonymous users and `reader` collaborators are read-only. Invites resolve to existing contributor accounts and accept `reader` or `editor`; revoking a collaborator removes that account’s access. Share creation/update and writes do not change plan acceptance, consent, submission or publication state. API paths are `/v1/workspace/projects/{id}/plan-document`, `/plan-document/export`, `/plan-share`, `/plan-share/collaborators` and `/v1/plans/share/{token}` with the export suffix for formats.

Public story responses add contributor_id/contributor_profile_url in v1 and contributorId/contributorProfileUrl in v2. GET `/v1/profiles/{profileId}` returns public attribution, language and that contributor's active published stories only. Email, private bio, drafts, sessions, passwords and object keys are omitted. Public story credit is retained as its publication snapshot when a profile name changes. The portal lists published catalogue records separately from owned private project drafts; submissions retain contributor IDs and snapshot credit.

The development seed `python scripts/asante/accounts.py` creates/reuses five generated passwords in ignored `.env.asante-test-accounts` (0600; excluded from images), then sends them via stdin to `app.db.seed_accounts`. The server seed is development-only, assigns four known fixture stories by exact fixed ID/slug/credit to demo/nomsa/thabo/amina profiles, and creates a separate reviewer account. It never overwrites an existing owner's FK, password, edited draft or review decision. It creates no new publication and refuses mismatching existing account credentials/roles. Account recovery and production identity/abuse protections remain separately scoped.
