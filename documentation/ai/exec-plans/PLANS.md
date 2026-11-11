# Asante implementation blueprint

Blueprint revision: 2026-11-09. This is the controlling implementation order and handoff document. Feature specifications describe targets; they are not evidence that those targets already work.

## Product and fixed boundaries

Asante connects audio/video stories to landmarked places. Contributors plan stories with Asante AI workers, retain original material and credit, and submit a versioned packet for human review. Listeners can explore locations and play published stories from anywhere. GPS is optional and must never gate remote discovery or playback.

- Public website, listener map and contributor portal: `app/websites/asante`.
- Internal approval website: `app/websites/dashboard`.
- Asante API and worker implementation: `app/services`; database migrations/seeds: `app/db`.
- Docker/proxy definitions: `infrastructure`; delivery/deployment: `ops`; automation scripts: `scripts`.
- Retain the established root layout. Do not scaffold extra services, new root folders, or one document per feature.
- Codex is the development assistant. Asante AI workers are application runtime components. Codex MCP, memory, skills, rules, and automation are not Asante runtime dependencies.
- Keep Next.js/TypeScript, FastAPI/Python, PostgreSQL/PostGIS, MapLibre and S3-compatible MinIO. Add pgvector only when a measured retrieval requirement exists. Defer Redis, Kafka, Kubernetes, native/background GPS, offline maps, and independent microservices.
- The four capstone tracks remain creation/craft, voice/language, discovery/audience, and truth/authorship/ownership.

## Read only the specification needed for the task

| Document | Owns |
|---|---|
| [DESIGN.md](../design-docs/DESIGN.md) | Tokens, layout, component interactions, responsive and accessibility criteria |
| [FRONTEND.md](../design-docs/FRONTEND.md) | Public map, tour, playback, contributor portal and reviewer UI slices |
| [BACKEND.md](../design-docs/BACKEND.md) | Target API, database, ownership, media, review and publication contracts |
| [ASANTE_AI_RUNTIME.md](../design-docs/ASANTE_AI_RUNTIME.md) | Asante worker schemas, jobs, limits, fixtures and evaluations |
| [PRODUCT_SENSE.md](../product-specs/PRODUCT_SENSE.md) | User journeys and final discrepancy review |
| [GITHUB_CI.md](GITHUB_CI.md) | Current CI, local URLs, reviewer-key setup and deployment boundary |
| [BOOTSTRAP_PROMPT.md](BOOTSTRAP_PROMPT.md) | Reproducible current app startup |
| [tests/README.md](../../../tests/README.md) | Current test commands and manual browser checklist |
| [CODEX_MCP.md](../references/CODEX_MCP.md) | Installed read-only Codex tools and named execution checks |

Use the existing documentation folders: design-docs for technical/visual specifications, exec-plans for plans and execution prompts, product-specs for acceptance/journeys, references for setup/tool guidance. Keep generated reserved for generated documentation. Codex execution summaries go under logs/codex and test evidence goes under logs/tests by category; do not move or hand-edit generated records.

Read `AGENTS.md`, this feature registry, and the named feature section. Inspect affected code before editing. Do not reread all historical chats, dump unrelated files, or create missing speculative documents from old lists.

## Observed code baseline

The Asante UI prototype has a full map, anchored version-2 tour, public catalogue, language/search filters, optional GPS and story location details. One original synthetic English MP3 demo supports user-initiated playback, transcript and HTTP range requests. The MP3 is a versioned asset at `documentation/project/assets/media/asante-playback-demo.mp3` is retained as the source asset and is seeded into private MinIO. The browser receives a normal Asante media URL; the API resolves its published story in PostgreSQL and streams the database-selected object. Other illustrative stories have no media.

Profiles, saved project revisions, upload metadata, immutable submission packets, review decisions and listener preferences now persist in PostgreSQL. Original uploads and verified browser migration archives persist in private MinIO. The portal uses explicit draft saves, real uploads and email/password account sign-in with revocable seven-day sessions. A lost cookie can be replaced by signing in again. Provider SSO, verified email and password recovery remain pending. Reviewer accounts and server roles protect the dashboard, replacing shared reviewer keys.

The contributor portal's current authorized surface is a story chat shell. Each project is a chat; New chat shapes a project, and its thread provides plan, evidence, upload and submission actions. The left rail lists story chats rather than portal sections. Planner/researcher calls still use durable Asante API worker runs and the existing research collector; sources remain candidates for human interpretation, and plans require explicit accept/reject. The former Research-room-only portal baseline below is historical and superseded by the 2026-11-09 chat authorization. The 2026-11-10 AS-07/12 repair reuses the existing field-report/export/share surfaces. The 2026-11-10 recorded activity/autosave slice adds a bounded view of actual planner/researcher handoffs. Autonomous multi-agent teams, report redesign and the `/asante/talk/` Ollama gateway remain out of scope. Nothing publishes automatically.

Docker Compose runs the two websites, API, `job-worker` (same API image, durable media/assessment jobs), PostgreSQL/PostGIS, MinIO and Nginx. Live AI uses Modal rather than a separate in-Compose GPU service. GitHub Actions configuration exists; a remote successful run and branch protection have not been verified in this workspace. Git initialization/remote state must be inspected before any Git operation.

AS-03.a/b checks ran on 2026-11-07: 13 API unit/functional tests and one isolated PostgreSQL/PostGIS integration test passed, covering migrations and seeds applied twice, catalogue queries, `/v1` compatibility, `/v2` cursor paging and filters, antimeridian bounds, distance ordering and nearby paging. Repository contracts passed (14 tests) after the documentation update. Earlier recorded website checks remain 7 logic/render tests, 12 repository/live route checks, website type checks and production compilation. These results do not prove visual correctness, persistent accounts, live AI integration or a completed production workflow.

## Work carried out

### Live AI on Modal with Ollama (2026-11-11)

- Decision: localhost keeps host Ollama + local Whisper unchanged. Live uses a separate backend (`ASANTE_AI_BACKEND=modal`) that calls Modal-hosted Asante tools; Modal runs Ollama (and Whisper) for those tools. No Gemini tokens required for that path. Full operator contract: [ASANTE_AI_RUNTIME.md](../design-docs/ASANTE_AI_RUNTIME.md) “Live Modal backend”.
- Code: `app/services/ai/modal/asante_ollama_app.py` (Modal deploy), `app/services/api/asante_api/ai/live_modal.py` (live-only HTTP adapter), `caption_limits.py`, thin gates in `provider.py` / `jobs.py`. Secrets stay in env / Modal secrets, never in git.
- Deploy: create Modal secret `asante-modal-auth` with `ASANTE_MODAL_SHARED_SECRET`, then `python -m modal deploy app/services/ai/modal/asante_ollama_app.py` (or `scripts/asante/deploy_modal_ollama.sh`). Set live `ASANTE_MODAL_BASE_URL` to the printed ASGI URL. HubTweak MinIO/Modal and other projects are out of scope.
- Live cost caps (env, easy to raise later): `ASANTE_LIVE_CAPTION_SECONDS` default 45, `ASANTE_LIVE_TRANSLATE_MAX_CUES` default 12, `ASANTE_LIVE_TRANSLATE_BATCH_SIZE` default 3, `ASANTE_LIVE_TRANSLATE_DEADLINE_SECONDS` default 45. Localhost keeps 180s / 100 cues unless overridden.
- Draft media jobs (2026-11-11): verified audio/video uploads enqueue capped `transcribe` + `translate` (+ `analyze` for video) with `submission_id` null. Submit promotes matching draft jobs for the same upload instead of re-running Modal work, then adds assessment. Portal projects expose `mediaJobs`, `transcriptDraft` and `translations`. Backfill script: `scripts/asante/backfill_draft_media_jobs.py`.
- When prompting future AI/job work: keep localhost≠live backends; enforce caps through `caption_limits.py`; never invent transcripts/captions; rebuild `api` + `job-worker` after live AI changes; leave publication human-gated.

| Work | Status and evidence | Remaining boundary |
|---|---|---|
| Codex development workflow | Conda environment, named execution checks, project-scoped Codex MCP inspection tools for PostgreSQL/MinIO, and local Codex execution rules are documented and set up. | Codex MCP remains read-only; these tools and rules do not belong to the Asante application runtime. |
| Asante local runtime and CI setup | Docker Compose services, Nginx path-based proxy routes, environment-key guidance with `.env` fallback, and GitHub Actions configuration are in place. | Clean-machine bootstrap and a successful remote GitHub Actions run/branch protection are not verified. |
| Laptop local proxy coexistence | Local ignored `.env` uses `ASANTE_HTTP_PORT=8082`; the separate local reverse proxy owns host port 80 and forwards `/asante` to Asante. Map, portal, review, and API health routes return 200 through the clean URLs; no proxy-manager login was needed. | Catalogue requests now return 200 and demo range playback returns 206 after local migration and catalogue/media seeds. Port 80 remains the standalone/live-demo Asante setting. |
| AS-00.a map extraction | Automated-verified: map lifecycle, catalogue loading and selection behavior were extracted while preserving the frontend contract. | User browser review is pending; no visual acceptance is claimed. |
| AS-00.b Codex execution harness | Named checks, execution summaries, categorized test reports and scoped MCP setup/verification scripts are in place. | A clean-machine bootstrap and remote GitHub CI run remain to be verified. |
| AS-01.a database foundation | Automated-verified: async SQLAlchemy/Psycopg connection, Alembic runner, initial schema/PostGIS migration, and repeatable isolated-database check. | The developer database is migrated through 0002_public_catalogue. Contributor/project/review persistence is now implemented; worker persistence and provider identity remain incomplete. |
| AS-03.a/b public catalogue | Automated-verified: persisted catalogue, repeatable seeds, PostGIS queries, `/v2` paging/filters/bbox/distance, and existing `/v1` compatibility all pass on an isolated DB. | Developer DB migrated/seeded and live API refreshed; live HTTP verification passes, user browser verification pending. |

The AS-01.a migration runner is the foundation for later feature-owned migrations. AS-03.a adds the public catalogue tables and read repository; AS-01.b now persists the local owner-scoped contributor/review boundary with restart tests; worker_runs and media_derivatives persistence are present for the Research-room baseline.

AS-03.a/b are implemented in source. Existing `/v1` routes remain for the current website; `/v2` adds camelCase cursor pages, filters, bbox and explicit nearby paging. The developer database now has the AS-03 migration and four landmarks/four published demo records. The API was refreshed independently; catalogue routes return 200 and demo media returns 206 from MinIO after restart. User browser verification remains pending.

Read-only local storage inspection on 2026-11-07 found no Asante catalogue tables in the developer database and no objects in the `asante-media` bucket. That was the pre-activation state; the local migration and seeds have now populated the catalogue and one MinIO demo object. Contributor originals now upload into private MinIO with server verification. During the port change, Compose recreated the Asante API, website and dashboard containers with their existing images despite targeting the proxy service. This was not an image rebuild; any API-memory review submissions were cleared. PostgreSQL and MinIO volumes were retained. The sample MP3 remains reproducible from its repository asset. The public catalogue and demo audio are now persisted; contributor/review records also persist after the workspace activation below.

## Feature registry

P = prototype/partial; N = missing. No row is production-complete. Slice identifiers such as AS-01.a are defined in the owning specification.

| ID | Feature | Baseline | Depends on | Owning specification | Completion evidence |
|---|---|---|---|---|---|
| AS-00 | Harness, readable modules, stable contracts | P; AS-00.a automated_verified, browser verification pending | — | This file; FRONTEND; BACKEND | Existing behavior preserved; focused map/catalogue/discovery units; website tests, types and build pass; user browser review pending |
| AS-01 | Durable domain model and migrations | P; AS-01.a automated_verified; AS-03.a adds catalogue repository/seeds; local contributor/review persistence restart-verified; worker_runs and media_derivatives tables exist | AS-00 | BACKEND | Foundation and catalogue table constraints/seed checks pass in isolated DB. Local owner-scoped profile/draft/upload/submission/review repositories pass restart tests. Provider identity and full provenance remain open. |
| AS-02 | Identity, sessions, roles and ownership | P; local email/password accounts and revocable sessions automated_verified; role-based workspace redirects implemented, clean/direct URL helper tested; signed-in role browser acceptance pending; SSO/recovery pending | AS-01 | BACKEND; FRONTEND | Contributor isolation; reviewer authorization; login/logout/recovery |
| AS-03 | Published catalogue and location queries | P; AS-03.a/b automated_verified; local DB/API activated; live HTTP verified; browser review pending | AS-01 | BACKEND; FRONTEND | Public catalogue, stable seeds, PostGIS nearby/bbox queries, global remote access, cursor pagination and filters pass on an isolated DB. Existing `/v1` contract remains. Local runtime migrated/seeded and API refreshed; frontend still uses `/v1`. |
| AS-04 | Map, pins, search and optional GPS | P; discovery thumbnails and explicit 150 m foreground auto-play added 2026-11-10; browser acceptance pending | AS-03 | FRONTEND; DESIGN | Real map dimensions, selected locations, denial/offline fallback |
| AS-05 | Anchored onboarding tour | P | AS-04 | FRONTEND; DESIGN | Per-element spotlight, resize/scroll, skip/resume/replay/keyboard |
| AS-06 | Listener player and language controls | P, demo only | AS-03; real assets need AS-10/16 | FRONTEND | Explicit play, range/seek/resume, accurate language and media states |
| AS-07 | Contributor profile and story projects | P; account-owned profile/draft revisions, published-story/profile links, explicit Save, persisted Step 2 research brief and chat shell automated_verified; deterministic browser creation/reload verified; archive/provider SSO pending | AS-02 | FRONTEND; BACKEND | Server-owned drafts; reload/cross-device; explicit save/conflict feedback |
| AS-08 | Consent, authorship and version provenance | P | AS-01/02/07 | BACKEND | Immutable originals, scoped consent, attribution approval, revision trail |
| AS-09 | MinIO upload and server verification | P; five-minute API-mediated uploads verified; prototype limits are 100 MiB audio and 500 MiB video; direct presigning/staging cleanup deferred | AS-07/08 | BACKEND; FRONTEND | Scoped short-lived URLs; actual asset verified; expired/forged cases fail |
| AS-10 | Media derivatives and efficient delivery | P; upload-time ffmpeg probe/audio/poster/keyframe derivatives and demo/MinIO streaming verified; broader HLS delivery and listener readiness UI still open | AS-09 | BACKEND; FRONTEND | Probe, poster/audio/HLS as appropriate; playback-ready assets |
| AS-11 | Durable Asante worker runs | P; planner/researcher persist `worker_runs`; Compose job-worker claims durable draft+submission media/assessment jobs; general retry/cancel harness remains partial | AS-01/02 | ASANTE_AI_RUNTIME | Bounded jobs, retries, deduplication, persisted status and trace |
| AS-12 | Planning, research and evidence workers | P; explicit saved questionnaire → planner → researcher uses returned server versions; persisted working/failure/retry/completion, report/source popups; deterministic browser journey verified | AS-07/08/11 | ASANTE_AI_RUNTIME; FRONTEND | Structured suggestions, source records, uncertainty and contributor decisions |
| AS-13 | Transcription, translation and video analysis | P; draft verified uploads enqueue capped transcribe/translate(/analyze); live Modal Whisper/Ollama path + live caption caps; publish still human-gated | AS-10/11 | ASANTE_AI_RUNTIME; FRONTEND | Preserved originals; timed text; language evaluations; reviewed derivatives |
| AS-14 | Submission packet and guideline evaluation | P; exact saved revision/story details/consent/media and optional PDF freeze into the packet; preview hash checked on submit; assessment/media jobs enqueue transactionally; reviewer assessment uses no contributor research. Live provider validation and full auth/restart matrix remain open. | AS-08/10/11; AS-12/13 results or explicit unavailable states | BACKEND; FRONTEND | Immutable revision snapshot; deterministic blockers and reasoned findings |
| AS-15 | Human reviewer workflow | P; reviewer sees submitted story details, English transcript, optional supporting-PDF evidence, video drafts and provenance; contributor research remains private; API and UI use `asante.review-policy.v1`; approval remains human. Browser acceptance remains pending. | AS-02/14 | BACKEND; FRONTEND | Roles, evidence comparison, media review and versioned reasoned decisions |
| AS-16 | Publication, withdrawal and correction | P; approve publishes to catalogue + admin email; withdrawal/correction still open | AS-15/03 | BACKEND; FRONTEND | Approved version appears remotely; withdrawals revoke delivery; revisions re-reviewed |
| AS-17 | Clean bootstrap, GitHub CI and deployment | P, CI config only; deployment deferred | AS-00; release requires AS-16 | GITHUB_CI; BACKEND | Clean clone proof, required CI checks; deployment only to chosen target |
| AS-18 | Full journey and discrepancy review | Deferred for now | AS-04–16; AS-17 CI | PRODUCT_SENSE | Browser evidence plus real service tests mapped to acceptance criteria |

Dependencies describe integration requirements. UI slices may use typed fixtures before dependencies exist, but must remain labelled prototypes and cannot be marked integrated.

### AS-07/11/12 recorded research activity and form autosave (2026-11-10)

- Authorized: a compact chat view of actual worker delegation/activity with a button opening the fuller research record, plus autosave while completing contributor forms. This extends the prior research flow; no autonomous worker team, simulated conversations, or private model reasoning is exposed.
- Implemented: `ResearchActivity.tsx` shows the latest recorded planner→researcher handoff and up to three other recent events in a 660px-wide bubble with a 240px scroll region. **View full research activity** opens a responsive, keyboard-dismissable popup with chronological events, timestamps, saved revision/brief, handoff questions, search query/focus, retrieval states, uncertainty, candidate sources, and run/trace references. Older runs explicitly say detailed activity was not recorded. Account/project changes discard stale reads. Read/poll/reload never start Asante workers.
- Implemented: API worker runs persist bounded factual progress events in existing `worker_runs.result_payload` JSONB as steps happen. A request-scoped progress sink uses short independent database transactions, so the owner can read progress during the request. Planner output questions are actually passed into the researcher's input snapshot. The researcher reports real query preparation and collector delegation/results, bounded page retrieval, URL deduplication, completion/failure/cancellation. Model query preparation runs off the API event loop so progress remains readable. No migration or extra runtime service is needed.
- Implemented: a shared 900ms debounced/serialized autosave hook covers new/existing story details, partial research questionnaires, story notes and profile edits after explicit storage consent. It preserves edits made during a save, queues the newest snapshot, reuses server versions, shows Saved/Saving/Unsaved/failure with retry, flushes form saves before closing/switching or explicit research start, and guards account changes. New story autosave keeps the form open and the same project ID. Partial briefs persist as incomplete and cannot start workers. Field-report autosave remains in its existing editor; uploads, account credentials, submission and publication are never automatically triggered.
- Compatibility: saving a research questionnaire no longer requires completed required answers; worker start still validates them. Existing saved projects and reports remain readable; submitted projects stay frozen. Asante publication, authenticity workers, dashboard redesign, translation, deployment, and broad crash/lease recovery remain outside this slice.
- Verification: named website check passed 33 tests (13 DOM interaction cases), TypeScript and production build. Named API check passed 54 unit/functional tests and 11 of 13 real PostgreSQL/MinIO integration cases, including live-readable activity, planner-question handoff, incomplete-autosave validation and stale-run rejection; the two pre-existing migration-head/video-job expectation failures from the prior repair remain. Browser at `http://localhost/asante/portal/` passed against the disposable deterministic Python worker API: new project/partial brief autosave, reload, save-failure retention/retry, live worker activity, popup details, worker failure, version sequencing, report/source views and 390px layout. Evidence: `logs/tests/e2e/portal-research-activity/` (screenshots, trace, result JSON). This is fixture/persistence evidence, not live provider quality or historical verification.
- Exact execution records: `conda run --no-capture-output -n asante-codex python scripts/codex/checks.py website` → `logs/codex/execution-20261110T171102151001Z.json`; `contracts` → `execution-20261110T171041654830Z.json`; `api` → `execution-20261110T170608010815Z.json`. Browser command remains the documented `ASANTE_RESEARCH_FIXTURE_URL=... node tests/e2e/portal_research.mjs` with the installed Playwright module selected via `ASANTE_PLAYWRIGHT_MODULE`. Live `api` and `asante` were explicitly refreshed; final `http` passed all 12 checks (`logs/codex/execution-20261110T171206214376Z.json`), and the final browser journey passed after activating the compact handoff/scroll behavior. The disposable fixture API was stopped and cleaned up after verification.
- Changed files: website `ContributorChat.tsx`, `ContributorWorkspace.tsx`, `workspace-client.ts`, `globals.css`, `ContributorWorkspace.test.tsx`, new `ResearchActivity.tsx` and `useDraftAutosave.ts`; API `workspace.py`, `research_brief.py`, `workers_api.py`, `ai/workers.py`, `ai/research.py`, new `ai/activity.py`; worker unit/workspace integration/browser fixture tests; this plan and the relevant frontend/runtime/test documentation.

### AS-07/12 Step 1 → Step 2 research repair (2026-11-10)

- Hardened: successful Step 1 server creation selects the chat and renders exactly one Step 2 reply from the persisted project. Existing drafts also receive it. The questionnaire opens only on a button click; project selection, reload and opening the questionnaire never start Asante workers. Submitted projects expose no brief editing/start actions.
- Hardened: typed `researchBrief` lives in existing project/revision JSONB, separate from generated plan/research/report content. It reuses the project claim and optional source URL and collects known material, research questions, cultural context, priorities and uncertainties. Main question and research questions are required; oral history needs no URL. Both explicit save actions retain answers on validation/save failure.
- Hardened: Save and start research waits for the saved server revision, calls planner then researcher with each returned server version, and sends all saved questionnaire answers in immutable worker input snapshots. Input hashes associate outputs with the brief. Synchronous client locks and the API project lock reject accidental duplicate starts; failed researcher retries reuse the successful plan for the same inputs. Account epochs/project IDs prevent late results from replacing another chat/account. Persisted run state can be refreshed without restarting workers.
- Hardened: empty/failed research never reports completion. A completed brief needs matching plan/research outputs and candidate sources; the existing report builder persists a report from those outputs. Automatically generated reports refresh when inputs change; contributor-edited reports are preserved, with the latest evidence available in the source view. Existing editing, exports, sharing, uploads and submission controls remain available.
- Verification: `contracts` passed 15 tests; `website` passed 28 tests (including eight DOM interaction journeys), TypeScript and production build; refreshed `api`/`asante` explicitly and `http` passed all 12 checks after development routes warmed. Browser interactions at `http://localhost/asante/portal/` passed using a separate, loopback-only fixture API with disposable PostgreSQL/MinIO data and deterministic Python planner/researcher functions. Evidence under `logs/tests/e2e/portal-research/` includes trace, screenshots at 1440px and 390px, and `result.json`. Browser tests cover save failures, one Step 2, popup buttons, save-only reload, worker failure, revised brief, sequential versions, report/source views and completed reload without another run. This is fixture orchestration evidence, not live research/source-quality evidence.
- API verification: the new worker-input unit case and real PostgreSQL brief/version/failure/retry/report and concurrent-worker/stale-revision cases are included in the named API check. The full API suite remains blocked by unrelated stale integration expectations: migration test expects `0013_submission_assessment` although checkout head is `0014_merge_review_schema`; video job test omits the existing `translate` job. Temporarily correcting those expectations also exposed an existing missing `provider_config` import in video analysis; those exploratory corrections were reverted and no video/translation implementation was changed.
- Changed files: website `ContributorChat.tsx`, `ContributorWorkspace.tsx`, new `ResearchBriefForm.tsx` and `ContributorWorkspace.test.tsx`, `workspace-client.ts`, `story-domain.ts`, `globals.css`, `page.test.ts`, `package.json`/lock (test-only jsdom); API `workspace.py`, `workers_api.py`, `ai/workers.py`, new `research_brief.py`; tests `test_workers.py`, `test_workspace_persistence.py`, new `research_fixture_api.py`/`portal_research.mjs`; this plan and `tests/README.md`.
- Exact recorded verification: `conda run --no-capture-output -n asante-codex python scripts/codex/checks.py <job>` (`/opt/anaconda3/bin/conda` on this host). Contracts report `logs/codex/execution-20261110T164930708541Z.json`; website report `logs/codex/execution-20261110T164952140552Z.json`. API report `logs/codex/execution-20261110T164830880529Z.json`: 53 unit/functional passed; 11/13 integration passed, including both new brief/concurrency cases, with the two unrelated failures above. Browser command uses `ASANTE_PLAYWRIGHT_MODULE` pointing to the installed Playwright `index.mjs`, `ASANTE_RESEARCH_FIXTURE_URL=http://127.0.0.1:18083`, and `node tests/e2e/portal_research.mjs`; its result/trace are under the evidence directory above.
- Leave unfinished: admin dashboard, authenticity assessments, publication, translation, deployment and unrelated portal redesign. Full durable worker crash/lease recovery and provider-quality evaluation remain AS-11/12 boundaries. A reloaded partially finished sequence resumes only through an explicit Start research action. No schema migration or live-data reset was needed; this checkout is not a Git repository, so no commit/diff evidence is claimed.

### AS-14/15 submission evidence slice (2026-11-10)

- Implemented: the API builds a preview from the expected `ProjectRevision`; submit rechecks its preview hash. The frozen packet contains the saved plan, editable field report, narrative/claim/source records, contributor decision, attribution, consent scope, original/derivative media references, revision linkage, and planner/researcher run/trace references. Derived assessment and media drafts live in their job results and do not mutate the contributor snapshot.
- Implemented: one `assessment` processing job is unique per submission; audio adds transcription and video adds transcription plus video analysis. The assessment result records input hash, submission/revision/run/trace IDs, schema/prompt versions, provider/model, state, findings, citations, uncertainties, safe error and timestamp. Citation IDs and excerpts are restricted to submitted source records. Provider failure and malformed output are explicit; assessment does not produce authenticity scores or decisions.
- Implemented: deterministic provenance/readiness checks and `asante.review-policy.v1` drive reviewer findings, the dashboard affordance and the decision API. Pending or unavailable assessments block approval and present the escalation path. Keyword/model heritage classification is advisory attention only.
- Implemented: reviewer assessment v2 now uses an allowlisted title, story description/claim, location, completed English transcript (or a labeled English translation draft), submitted PDF text (first ten pages), and bounded scene observations. It never sends contributor research, research briefs, source URLs, field reports, plans, or worker traces to the reviewer model. Assessment jobs wait for transcription/translation/scene jobs; the dashboard reports actual queued/running/completed/provider-failure states.
- Implemented: Poppler extracts bounded text from verified supporting PDFs; exact quote references are restricted to those PDF/transcript/scene inputs. Migration `0016_requeue_review_evidence_v2` requeues old assessments for undecided packets so they are rebuilt using the new contract. Missing transcript or PDF text is explicit, not an empty success.
- Implemented: restored the owner-only project ZIP pack route so existing contributor download coverage remains intact. It includes project/report/research/narrative metadata and verified original media without storage keys.
- Still open: browser journey on both clean and port URLs; live provider correctness/cultural evaluation; restart/retry/concurrent lease and isolation suite; production-readiness. The known live Alembic version `0013_drop_project_messages` is absent from this checkout; never stamp, downgrade or reset the live database. The new migration extends checkout head `0012_project_messages` and was not applied to the live database during this slice.

### AS-03/04 discovery thumbnail and position playback slice (2026-11-10)

- Implemented in source: desktop discovery panel is wider; every catalogue card renders its stored poster or a visual fallback; video upload posters use an extracted frame and audio uploads receive deterministic decorative cover art. The existing `stories.poster_file` and `media_derivatives` schema are reused; seed media generation fills missing published story poster records and MinIO objects without adding a redundant column.
- Implemented in source: public poster URLs now resolve through the published-story API boundary. Position auto-play is a separate opt-in; it requests location, watches foreground movement only while enabled, and tries the nearest playable story within 150 m. Browser media policy can block audible auto-play; the selected player then presents the manual Play control and a clear message. Disabling the option stops the watch and position-started playback.
- Verified locally: rebuilt/recreated `asante` and `api`, ran the idempotent `python -m app.db.seed_media` against the existing local database/MinIO, and confirmed all four published catalogue stories return poster URLs. The poster route returns 200 with `image/svg+xml` for audio cover art and `image/jpeg` for a video frame; the clean map URL returns 200 and the website container TypeScript check passes. No schema migration was needed. Browser interaction and position-triggered playback still need manual acceptance; audible playback remains subject to browser autoplay policy. The existing Alembic history mismatch is untouched.

### AS-06 video popup and timed caption choices (2026-11-10)

- Implemented in source: video playback opens in a dismissible modal popup; selecting a published story’s translated caption track overlays only the cue active at the video’s current time. Caption tracks are fetched on popup open from the public story-specific captions route, not bundled into catalogue list responses.
- Available choices come only from bounded, valid timed cues stored in the existing `stories.caption_tracks` JSONB field and included from an approved packet when present. Full translation text is never fabricated into timed captions.
- Implemented and verified: the API now authorizes and serves each published HLS playlist and segment through the same story boundary, rewriting playlist references to same-origin routes. The discovery Play action opens the popup; its video controls play the HLS stream, and the caption selector lists only timed translated tracks actually stored for the story.
- Verification: rebuilt/recreated `api` and `asante`; Python compile and website TypeScript checks pass; the sample HLS playlist and first segment return 200; browser playback advanced inside the popup. An explicit user-requested backfill of all three published videos now serves captions extracted from each video’s actual first 180 seconds, replacing unusable legacy JSON whose text described different narratives. The prior values are preserved at `/private/tmp/asante-story-002-legacy-captions.json` and `/private/tmp/asante-other-video-legacy-captions.json` on this development host. Current per-story translation coverage and provider failures are recorded in the AS-06/13 audio captions and published backfill section below. Browser smoke showed English and isiZulu text in the video at 45 seconds for `story-002`, with partial coverage stated in labels. The source video itself does not match the illustrative story title and narrative.

### AS-13 timed media caption drafts (2026-11-10)

- Audio and video submissions enqueue translation after transcription; video also enqueues scene analysis. Local Whisper transcribes at most the first 180 seconds of the verified speech WAV into timed segments; the translation worker preserves those timings and prefers configured Ollama through the existing provider adapter, using Gemini when Ollama is not configured. Translation runs in batches of three timed cues with a bounded per-cue fallback for malformed or timed-out batches and a per-language deadline; unavailable results remain explicit.
- The reviewer packet now projects original and translated timed tracks from durable job results. The review video player overlays the selected cue at the video clock time and shows translation drafts and job states. Future public caption tracks still require an explicit human-approved packet value; worker drafts are not published automatically. The one-time `story-002` backfill was directly requested by the user and is labeled as an AI draft.
- Verified locally: a 30-second MP4 fixture yielded four local Whisper cues; the existing pending video submission yielded four cues each in English, isiZulu, and Sesotho, and the API packet projection returned all three choices. Rebuilt/recreated `api`, `job-worker`, and `dashboard`; Python compilation and dashboard TypeScript check pass. Restored the local Alembic branch revision and merged it with the assessment migration; `alembic upgrade head` applied successfully. Reviewer browser playback still needs a signed-in visual acceptance pass. Upload-time derivative generation is still synchronous; moving its poster/audio/HLS work to a durable post-upload queue remains open.

### AS-06/13 audio captions and published backfill (2026-11-10)

- The listener and reviewer audio players now show the cue at the audio playback time and offer language choices from the same per-story caption API as video. The API also reports per-language `draft`, `partial`, or `unavailable` state, cue coverage and provider. The explicit `python -m asante_api.ai.backfill_published_captions` command scans active published audio/video, preserves existing human tracks, fills missing original timed drafts from actual media and resumes partial translations without duplicating cues.
- Local Compose now connects Asante server containers to the installed host Ollama `llama3.2:3b` through `host.docker.internal`; the ignored `.env` carries that local setting. All 21 worker unit tests pass after isolating the provider-disabled test from the local Ollama setting; API Python compilation and both website TypeScript checks passed. Browser smoke showed timed English text centered below the map navigation during published audio playback. All four published recordings now have original timed captions: audio demo 8 cues, videos `story-001` 48, `story-002` 33 and `story-003` 21. Public translation coverage is complete for both isiZulu and Sesotho on the audio demo and `story-003`, and on `story-002`; `story-001` has 48/48 isiZulu and 22/48 Sesotho cues. These are AI drafts; a focused Ollama Sesotho probe produced poor wording, so accuracy requires human review before treating any translation as final.

## MVP smart-hardening gate (2026-11-09)

The restored Research-room baseline is **not** a finished MVP. Many registry rows are still incomplete jobs, half-wired surfaces, or prototype labels. “Harden what is there” is only valid when the prompt names the incomplete contract being finished, what stays unfinished, and what may be removed to stop false completeness.

### Hardening rules

1. **One incomplete job per prompt.** Prefer finishing or honestly bounding one AS-* slice over sprinkling polish across many.
2. **Name three buckets in every prompt:**
   - `Harden:` the exact behaviour that must become true and testable
   - `Leave unfinished:` related work that remains explicitly incomplete; do not silently implement it
   - `May remove / disable:` half-wired code, UI affordances, docs claims, or orphan services that pretend the unfinished work already exists
3. **Honesty over feature count.** A button, worker tile, migration, or Compose orphan that cannot complete its contract must be removed, disabled, or labelled unfinished. Do not leave decorative “success” paths.
4. **No unapproved product surfaces during MVP hardening.** The user explicitly authorized the contributor story-chat slice on 2026-11-09. Field reports, multi-agent research team, talk gateway, and deployment host work remain excluded unless authorized separately.
5. **Update this plan after the slice.** Registry baseline text must say what is now true, what remains unfinished, and what was removed.

### Current incomplete-job map (honest)

| Area | Present but incomplete | MVP hardening intent |
|---|---|---|
| AS-10 | Upload derivatives exist; listener HLS/readiness UI incomplete | Harden poster + reliable playback for published stories; leave full HLS profiles unfinished unless needed for one demo asset |
| AS-11 | `worker_runs` for planner/researcher exist; lease/retry/cancel harness incomplete | Harden durable run status/safe failure for Research room; leave full SKIP LOCKED platform unfinished |
| AS-12 | Chat-thread Prepare/Refresh plan and Find evidence use existing workers; source relevance and richer claim-link UX remain incomplete | Harden working/failed/empty source states and accept/reject plan; leave language/structure/provenance workers unfinished and unavailable |
| AS-13 | Partial code/migrations/orphans may exist | **Out of MVP harden set.** Mark unfinished; remove/disable UI or Compose claims that imply live transcription/translation/analysis |
| AS-14 | Immutable packet + media/consent checks exist; packet preview may not show the same plan/research/media the reviewer sees | Harden packet preview parity; leave deep guideline scoring unfinished |
| AS-15 | Dashboard review/auth exists; claims/sources/media comparison may be thin | Harden reviewer packet comparison + reasoned decision; leave portal review-chat and advanced queue filters unfinished/removed |
| AS-16 | Approve can publish + email; withdrawal/correction open | Harden publish → map discovery/play for the approved revision; leave withdrawal/correction unfinished |
| AS-17/18 | CI config only; full journey deferred | Leave unfinished for MVP; do not spend tokens on host deployment |

### Ordered MVP hardening prompts

Use these in order. Each is one pasteable Feature/Scope. Do not merge adjacent rows in one prompt.

| Order | Feature | Harden | Leave unfinished | May remove / disable |
|---|---|---|---|---|
| H1 | AS-12.b | Chat Find evidence: busy/fail/empty/source-card states; no invented sources | Claim-conflict graph, social depth beyond current collectors, language/structure workers | “Sources ready” copy when the run failed |
| H2 | AS-12.a | Chat Prepare/Refresh plan + accept/reject against saved project; fixture vs live provider labelled | Live provider spend ceilings, multi-revision suggestion history UI | Planner tiles that claim AI success without a run/trace |
| H3 | AS-14.a | Submission preview shows the frozen credit/consent/media/plan/research the server will store | Rich guideline scoring, AS-13 transcript/translation fields beyond honest unavailable | Preview fields that invent worker results not on the project |
| H4 | AS-15.a | Reviewer opens that exact packet with media + research sources + plan decision visible | Portal-as-review-chat, advanced sensitivity filters | Dashboard affordances that imply AS-13 analysis exists when it does not |
| H5 | AS-16.a | Approve publishes that revision to catalogue; remote map can discover and Play it | Withdrawal, correction, multi-version public history | Publish success that does not create a playable public story |
| H6 | AS-10.a | Published story has poster/media readiness sufficient for that Play path | Full HLS ladder, caption tracks, dubbing | Listener UI that promises stream profiles not produced |
| H7 | AS-11.a | Research-room runs expose durable run/trace/status/safeError to owner; stale expectedVersion fails closed | Full job worker lease platform, cancel API, spend ledger | Orphan AI/job-worker Compose claims not in the current stack |

Stop after H5 if the vertical demo already works. Do H6/H7 only when playback or run honesty still fails.

## Implementation sequence and gates

1. **Preserve the working prototype:** AS-00.a/b; review current code and baseline tests. Keep map CSS specificity, anchored tour and remote listening as regressions.
2. **Make data and ownership real:** AS-01.a/b, AS-02.a/b, AS-07.a/b and AS-08.a/b. Migrate local drafts only through explicit user confirmation. No silent ownership assignment.
3. **Connect catalogue and media:** AS-03.a/b are implemented in source and integration-tested on an isolated database; local catalogue and MinIO demo delivery are now activated; continue integrating AS-04 and AS-06 against persisted published assets.
4. **MVP smart hardening:** follow the H1–H7 gate above. Finish or honestly bound one incomplete job per prompt. Mark AS-13 and withdrawal/correction unfinished rather than half-implementing them.
5. **Only then broaden intelligence:** AS-11.b lease/retry platform and AS-13.a/b/c when the user explicitly opens that gate.
6. **Prove delivery later:** AS-17 deployment target and AS-18 discrepancy review remain after the MVP vertical slice is browser-verified.

Review ownership/session changes, upload authorization, and publication/withdrawal transactions at their feature gates as well as in the final review. Do not accumulate those decisions until the final website inspection.

## Small implementation tasks

AS-00.a: replace compressed/oversized route components with focused components, hooks and domain functions inside their existing app folders. Preserve behavior; do not redesign the website during extraction.

AS-00.b: establish a deterministic test command per layer, isolated fixtures and a typed API adapter. Existing HTTP smoke tests are not Playwright interaction tests. Retain current unittest/Vitest coverage; add pytest for new service cases when its runner is configured in CI. Do not mass-convert tests just to adopt a framework.

Each implementation prompt selects **one slice**, normally one behavior change with its tests. Split a slice if it requires several independent contracts. A file budget is a planning aid, not permission to omit necessary tests. Prefer existing files; justify each new module by responsibility.

Use these states in the registry/handoff: `specified → implementing → automated_verified → browser_verified → accepted`. Record prototype-only or blocked dependencies explicitly. User browser verification and final acceptance are separate from a model claiming tests passed.

## How the user runs each implementation prompt

1. Open the Asante project in the coding client and select the implementation model. Start Docker Desktop/local Docker when this task needs containers. Do not recreate the repository or Codex MCP accounts.
2. Choose one feature slice from the registry in dependency order. AS-00.a, AS-01.a and AS-03.a/b are automated-verified; AS-00.a visual review and AS-03 user browser verification remain pending; local HTTP verification passes. The Codex checks/MCP portion of AS-00.b already exists; do not rebuild it as missing work.
3. Paste the short request below. Change Feature and Scope for later slices. The model must resolve the relevant specification sections, affected files and tests; the user does not need to rewrite those lists each time.
4. Read the model's file-change plan. By default it continues after presenting the plan. If you want to approve the plan before edits, add “Stop after the file-change plan; wait for my approval.” Respond to environment permission requests only for actions within the chosen task.
5. Let the model implement and run the relevant execution checks. Ordinary feature tasks must not reinstall MCP, rotate keys, reset storage or repeat full bootstrap unless setup is actually missing. An unavailable connection is reported and diagnosed, not silently invented.
6. Read the handoff: changed paths, exact checks/results/skips, prototype limits and browser test steps. For UI changes, have the model refresh the affected live website before testing; disposable test builds do not update the running website. You perform the browser checks and report the route, steps, expected and actual result. Record browser acceptance in the plan only after it is observed.
7. If a defect remains, keep the same feature/scope and ask for that specific repair. When accepted, choose the next slice and repeat. Use the later Codex discrepancy-review prompt in product-specs/PRODUCT_SENSE.md at integration gates and for AS-18.

Copy this short request for the next MVP hardening task. Change only the Feature letter/number and the three buckets; keep the protocol the same:

```text
Use the “Codex implementation handoff prompt” in
documentation/ai/exec-plans/PLANS.md.
Follow the “MVP smart-hardening gate” in that file.

Feature: H1 / AS-12.b
Harden: Research room Find evidence busy/fail/empty/source-card states;
no invented sources; durable researcher run status visible to the owner.
Leave unfinished: claim-conflict graph; language/structure/provenance
workers; AS-13 transcription/translation; portal chat; field reports.
May remove / disable: leftover chat/timeline/research-team UI or copy that
claims sources are ready when the run failed or never ran.

Do not implement adjacent hardening rows in this prompt.
Read the repository instructions, present the file-change plan, implement
only this slice, run its checks, update PLANS.md registry/hardening notes,
and give me browser smoke-check steps. I will perform visual browser testing.
```

A fresh machine or stopped/missing stack uses exec-plans/BOOTSTRAP_PROMPT.md first. That setup prompt is not the feature implementation prompt and should not be pasted before every change. No separate reminder to read context or run tests is needed; those requirements are part of the execution protocol below.

## Codex implementation handoff prompt

This is a reusable protocol, not a map-only hard-coded file list. Use Feature and Scope from the user's request. If either is genuinely missing, select a safe independent diagnostic step and ask for the missing scope before implementation; do not implement the whole registry.

```text
Implement exactly the Asante feature slice and scope selected in the user's request.
Work from the Asante repository root.

1. Load the correct context.
Read AGENTS.md and documentation/ai/exec-plans/PLANS.md: the selected feature row,
baseline, dependencies, scope and definition of done.
Use the registry to read only the relevant sections of:
- documentation/ai/design-docs/FRONTEND.md — UI/integration tasks.
- documentation/ai/design-docs/DESIGN.md — visual, responsive and accessibility rules.
- documentation/ai/design-docs/BACKEND.md — data/API/identity/media/review tasks.
- documentation/ai/design-docs/ASANTE_AI_RUNTIME.md — Asante worker tasks.
Read tests/README.md for checks and documentation/ai/references/CODEX_MCP.md
for tools, credentials and limits. Acceptance cases are in
documentation/ai/product-specs/PRODUCT_SENSE.md.
Inspect affected code, helpers, test configuration and Docker build contexts.
Do not dump unrelated documents or rely on an old chat for current state.

2. Preflight and plan changes.
Use `conda run -n asante-codex python scripts/codex/checks.py preflight` and `contracts` as applicable.
If Git exists inspect status/diff; preserve unrelated changes. Do not initialize,
commit or push Git as a side effect.
Present a short table: path | edit/create/move | reason | affected contract |
test/evidence. State dependencies, acceptance cases and rollback approach.
Use the existing documentation subfolders and established source folders;
justify every new file. Do not scaffold later features.
Continue unless the user requested plan approval or a required choice/permission
is missing. Report missing dependencies; do only independent work meanwhile.

3. Implement within scope.
Use typed boundaries, focused functions and design tokens. Preserve documented
compatibility, authorship/consent gates and labels for incomplete integrations.
Do not replace a required real integration with mocked success.
Retain the map sizing, moving tour and location-independent playback regressions.
Use the available read-only Codex PostgreSQL/MinIO MCP for authorized inspection;
use scoped CLI/test adapters if unavailable and report that limitation.
Preserve application keys and local Codex configuration. Do not install servers,
rotate credentials, reset data, call paid external AI, publish stories, deploy
or push unless this selected task explicitly authorizes that action.
Add meaningful behavior/failure tests; do not write identity-string assertions.

4. Verify current source and affected services.
Run `conda run -n asante-codex python scripts/codex/checks.py` followed by the affected job names:
- website: user website Vitest, types and production build from a fresh image.
- dashboard: reviewer website tests, types and production build.
- api: API unit/functional cases from a fresh image.
- contracts: repository/Compose/runner contracts.
- http: strict live routes, queries, media and running-service checks.
- mcp-verify: read-only permission/protocol checks when Codex tools are affected.
Use all at cross-layer integration gates, not after every trivial edit.
Do not use --skip-build unless those images were just built.
Database/storage/worker changes also need their new targeted real-service or
fixture cases from the owning specification; current tests alone may not cover
the new feature. Run configured pytest/Playwright suites where relevant.
Fix introduced failures and rerun affected checks; identify pre-existing failures.

Disposable checks do not update the running app. Before claiming live behavior
or handing over changed UI for browser testing, refresh only the affected live
service with the scoped Compose command. The API now persists review packets and decisions. Preserve any legacy volatile state before replacing an older API image.
Never remove developer volumes to make tests pass.
Use documentation/ai/exec-plans/BOOTSTRAP_PROMPT.md only when setup is missing.
Do not claim unavailable, skipped or nonexistent checks passed.

5. Review, record and hand off.
Inspect the change for scope creep, leaked secrets, misleading states and errors.
Update only the selected slice/evidence and necessary contract notes in
documentation/ai/exec-plans/PLANS.md and the owning specification.
Keep generated execution summaries under logs/codex and test evidence under logs/tests by category; do not hand-edit generated logs.
Report: outcome; changed paths; exact check results/skips and evidence;
remaining prototype boundaries; refreshed live services; browser test steps;
smallest next slice. Keep it concise.
The user performs visual browser testing. Mark it unverified until observed.
Do not mark the entire feature accepted because one slice passed automated checks.
```

## Codex project tools and execution automation

CODEX_MCP.md records the working documentation connection and installed project-scoped PostgreSQL/PostGIS and MinIO read-only tools. The execution runner is scripts/codex/checks.py; use its named checks rather than retyping pipelines. A Codex model SDK runner remains proposed, not installed. These tools do not belong inside the Asante runtime.

Deterministic preflight, fresh-image checks and redacted result capture are implemented. Service checks use disposable containers and do not refresh the live app automatically; explicitly refresh affected running services before claiming the HTTP checks exercised newly changed live code. GitHub Actions uses the same runner. The Codex SDK can later drive bounded implementation/review tasks through these scripts. Keep model/provider credentials and application credentials separate. Do not start recurring tasks, install more servers or edit local Codex config merely because a feature prompt mentions automation.

## Cost-conscious development workflow

- Use this blueprint as durable context. Give the implementation model the selected feature sections, not the entire chat or a request to build everything.
- Freeze the slice's contract before coding; raise concrete conflicts instead of designing competing architectures in separate prompts.
- Use focused tests while implementing; run cross-layer tests at integration gates. Avoid repeated clean builds when no code or dependency changed.
- Use a review-capable Codex model for architecture decisions, sensitive feature gates and AS-18. Model choice is a user setting, not an Asante application dependency.
- A review report must cite files, reproduction steps, screenshots/traces when browser behavior matters, and severity. Fix only an authorized defect slice, then rerun the affected checks.
- No token/cost savings are guaranteed. Compare actual usage per accepted feature, retry/rework count and defect rate, not just price per call.

## Definition of done for an integrated feature

The named UI and API behavior work against the intended service, ownership and failure paths are tested, data survives required restarts, secrets and private drafts stay out of public responses, and pending work is visible. Required checks have recorded commands and results. Browser-dependent criteria have user or authorized Codex browser evidence. Update the feature row and relevant contract; do not count a placeholder button as implementation.

Current baseline commands are in tests/README.md and GITHUB_CI.md. AS-17 must keep them aligned as the database, auth, media and worker runners change. If a live stack is expected, `ASANTE_REQUIRE_SERVICES=1` prevents unavailable services from silently passing through skips.

## Decisions still requiring a product/environment choice

| Decision | Blocks | Independent work may continue |
|---|---|---|
| Identity provider and recovery/email configuration | Provider SSO, verified email and recovery | Local email/password sign-in, contributor/reviewer roles and ownership now work |
| Initial real stories, permissions, languages and media fixtures | Cultural/language acceptance; AS-13 live evaluation | Existing labelled synthetic English demo and structural cases |
| Asante AI provider models, supported languages and spend ceilings | Broader live AS-12/13 evaluation | Current Gemini/OpenAI-compatible adapter, fake/fixture planner path, Research-room worker tests |
| Deployment host, domain, registry and secret delivery | AS-17 deployment | CI and reproducible local bootstrap |
| Production map provider and any budget/key | Hosted tile rollout | Existing attributed local interactive map |

Prototype English/isiZulu/Sesotho codes and audio/video forms are test inputs, not promises of evaluated language support.

## Decision history and local setup context

- 2026-11-05: selected the existing web-first stack and two website responsibilities. Original media, consent, authorship and publication remain human governed. Native/background tracking and offline maps deferred.
- 2026-11-05: established local Docker/PostGIS/MinIO, shell variables with ignored .env fallback, scoped Codex Docker ExecRules, read-only Codex documentation integration and reproducible bootstrap instructions. Local Codex configuration is separate from repository code.
- Local Codex snapshots were recorded under ignored `.codex-backup/`; credentials and private session data are excluded. Do not edit local Codex configuration while implementing Asante features. Relevant records: ENVIRONMENT.md, EXEC_RULES.md and CODEX_MCP.md.
- 2026-11-05: added GitHub Actions configuration and no-port public proxy routes. Deployment remains a separate target-dependent step.
- 2026-11-07: added the local UI/API prototype and tests; later corrected the centred-only guide to anchored steps, map sizing, global catalogue access and demo playback. These corrections must survive subsequent refactors.
- 2026-11-07: adopted this feature blueprint and per-slice model handoff workflow. Detailed backend specifications are now in BACKEND.md. Historical broad phases are superseded by the registry and dependency order above.
- 2026-11-07: implemented the authorized Codex project MCP and execution-check subset of AS-00.b/AS-17.a. Dedicated service identities enforce read-only inspection; project settings and separate private credentials preserve existing application keys and the global docs MCP. Verified real stdio sessions, allowed reads and denied writes. Codex execution summaries live under logs/codex and test evidence under logs/tests; CODEX_MCP.md owns setup, scopes and recovery. Application persistence, the remaining API-adapter refactor and remote GitHub CI verification are still pending.
- Verification: the all job passed both websites' tests/types/production builds, API tests and strict live HTTP/service checks. Final runner contracts include credential reuse, application-env preservation and Codex config backup tests. The final mcp-verify report passed service-level denials, the SDK tool session and the exact project host launcher. Existing npm install audits reported 9 website and 8 dashboard advisories, including critical items; triage under AS-00.b/AS-17.a before shared deployment. No force upgrade or security acceptance was claimed.
- Documentation organization: moved the 11 authored AI documents into the existing design-docs, exec-plans, product-specs and references folders; no duplicate root documents remain. Updated repository instructions, links, bootstrap/review prompts and the runner's required-plan path. The reusable execution protocol now resolves files/tests from the chosen feature; the user changes Feature and Scope only.
- 2026-11-07: organized generated test evidence under logs/tests by unit, functional, integration and e2e categories, kept Codex execution summaries under logs/codex, and restricted the logs root to its README. Existing execution history was categorized; the runner and CI artifact upload now preserve this layout.
- 2026-11-07: AS-00.a extracted public-map state into focused catalogue, MapLibre lifecycle and discovery modules. The Asante website tests (10), TypeScript check, production build and live HTTP/service checks (8) pass. Refreshed only the Asante website container; visual/browser acceptance remains with the user.
- 2026-11-07: added the minimal `asante-codex` Conda environment (Python 3.12) for host-side repository scripts. Local checks now reject system Python and Anaconda `base`; GitHub CI retains its managed Python 3.12 runtime, and Asante API dependencies remain isolated in Docker. Updated the project Codex MCP interpreter with a config backup and verified its database/storage denials, MCP session and host launcher through the Conda environment.

## 2026-11-07 catalogue and MinIO activation

Implemented the public request flow: website → Asante API → PostgreSQL catalogue → same-origin media URL → published-story lookup → private MinIO byte stream. API MinIO settings come from Compose; storage keys and credentials are not returned to the browser. Media GET/HEAD supports bounded, suffix and open-ended ranges, safe 404/503 failures and 416 invalid ranges. No full-file buffering or automatic playback was added. The later workspace activation implements owner uploads; derivative processing remains AS-10 work.

Applied both existing migrations and insert-only catalogue seed to the local DB; seeded one 130,786-byte audio/mpeg demo object into MinIO. API alone was recreated; its empty review queue was recorded in ignored logs before refresh. Data and playback survive API recreation. Fixed the existing Alembic formatter indentation, and added explicit migration/catalogue/media setup to bootstrap and CI. No Git metadata exists in this checkout; no Git initialization was performed.

Evidence: `logs/codex/execution-20261107T130450960303Z.json` records 14 API unit/functional tests and one real isolated PostGIS+MinIO integration test passing, including seed twice, exact media bytes, HEAD/206/416, draft delivery denial and unavailable storage. `logs/codex/execution-20261107T130357282724Z.json` records 14 repository contracts passing. Live HTTP checks passed nine cases through the clean URL, including remote playback and dependency readiness. The read-only Codex MinIO inspection transport closed during verification; the actual Asante runtime client independently confirmed the object size/type, and real-service tests passed. Logs remain categorized under `logs/tests/`.

Browser handoff: open `/asante/`, confirm stories/landmarks load without 500s, select the labelled audio demo, explicitly press Play, pause and seek. Confirm Network uses `/asante/api/v1/stories/story-demo/media` with range responses and no MinIO hostname/key/credentials. Browse distant landmarks without GPS. User visual acceptance is pending.

## Contributor persistence integration — automated_verified; browser cleanup observed (2026-11-07)

The user authorized connecting the remaining profile, draft, upload, submission and review flows together and clearing Asante browser storage after verified migration. This spans AS-01.b, local ownership groundwork for AS-02.b, AS-07.a/b, AS-09.a/b and persistence portions of AS-14/15. Treat each boundary's evidence separately; OIDC, worker processing and public publication remain separate.

- PostgreSQL stores private device workspaces, hashed 90-day HttpOnly sessions, typed profile data, versioned project snapshots, upload metadata and immutable submission packets with append-only human decisions. A cookie is an access capability, not verified email/account identity. Preserve it during cleanup; provider sign-in/recovery remains unimplemented. Device sessions survive API restarts but incognito browser closure discards their cookies.
- For this local integration, uploads use an expiring five-minute same-origin owner-scoped API URL rather than a browser-to-MinIO presigned URL. The API limits streamed bytes, probes real media type/duration with ffprobe (ten-minute maximum), hashes server-side and stores the original in MinIO. This avoids exposing MinIO addressing/CORS/signature configuration to the browser. An OS temporary probe file is unlinked at request completion; no uploaded originals are retained in the repository/container media folder. Existing source demo fixtures remain.
- The upload requires explicit storage consent. Submission references the saved project revision and server-verified media, and retains attribution/consent. Review decisions use row locks and expected versions; approval does not publish a story. Reviewed originals use the normal API streaming route with a ten-minute HttpOnly review-media cookie, never keys in URLs. Reviewer key access remains development-only.
- Import is an explicit portal action: back up captured Asante local/session storage values to private MinIO, persist typed records in PostgreSQL, verify DB readback and the original backup hash, then remove only exact captured Asante values. Conflicting or changed browser data is preserved. The saved backup can be downloaded from the portal. This user has authorized that import/cleanup for their current Asante browser. Other localhost applications and cookies remain intact.
- Fresh website/dashboard/API checks and isolated PostGIS+MinIO upload/review/restart/failure tests pass. The live schema/apps were refreshed and clean-URL HTTP checks passed after initial cold compilation. Browser migration/cleanup succeeded; broader visual acceptance remains with the user.

Current automated evidence for this integration: API `logs/codex/execution-20261107T132433854179Z.json` passes ten unit/functional tests and three real PostGIS/MinIO integration cases (catalogue migration + complete workspace/upload/review/restart + upload failures). Website `logs/codex/execution-20261107T132452792432Z.json` passes 13 Vitest tests, TypeScript and production compilation. Dashboard `logs/codex/execution-20261107T132022181569Z.json` passes two Vitest tests, TypeScript and production compilation. Repository contracts: 14 pass in `execution-20261107T132150648626Z.json`. Applied migration 0003 locally and refreshed API/website/dashboard only; the prior volatile review queue was empty and archived under ignored logs. Nginx upload/streaming settings validated and reloaded. First live HTTP attempt hit development-server cold compilation timeouts; warmed routes returned 200 and verification is being rerun. Browser import/cleanup evidence follows when observed.

Browser cleanup evidence: the open Chrome incognito Asante portal reported three saved Asante browser records. The explicit import action returned the visible success message “Asante browser records backed up, verified and cleared.” The import banner disappeared. Independent runtime inspection found one private MinIO browser-import backup (163 bytes); this was small browser state, not stored media. No pre-existing projects/submissions/review decisions were found in that workspace. Its session cookie was retained. Cleanup applies to this open browser session; no other application's storage or other browser profiles were cleared. The old preview did not store original media bytes; previously selected files must be selected for their first real upload.

Live route evidence after warm-up: `logs/codex/execution-20261107T133049770179Z.json`, nine HTTP/service cases pass including dependency readiness, remote catalogue and byte-range media. The failed first cold-start run is retained as evidence rather than hidden. Rollback keeps the additive schema, named volumes and archived browser data; restore prior app images if needed, never drop the workspace tables/objects to roll back code.

Final media-format verification: `logs/codex/execution-20261107T133641590647Z.json` passes ten API unit/functional cases and four real-service integration cases. In addition to real MP3, generated WAV, OGG, MP4 and WebM recordings all upload, pass server probing and stream exact requested byte ranges with the correct content type. This supersedes the earlier three-case API integration count for this task. All test databases/buckets are disposable; live contributor/media data was retained. The running application code is the verified source; the final extra image build changed test fixtures only.

## Local accounts and story/profile links — automated_verified; live account checks passed (2026-11-07)

Authorized scope: finish local portal/dashboard sign-in accounts, link the existing story catalogue to contributor profiles, provide reusable local test credentials and verify account boundaries. This implements the local password path of AS-02.a/b and profile linkage for AS-07/03; the user requested local accounts without selecting a hosted identity provider. The earlier device-only session and shared reviewer-key instructions are superseded for contributor/reviewer access.

- Added migration 0004: accounts, hashed revocable account sessions, persisted login throttling, story-to-contributor FKs, and reviewer identity on decisions. Passwords use Argon2id with per-password salts; plaintext test credentials are kept only in an ignored local file and this private handoff. Seven-day HttpOnly/SameSite=Strict cookies identify account sessions and are revoked by logout. Invalid/expired/revoked sessions cannot access private accounts or media.
- Registration creates contributor roles only. A newly registered account can explicitly claim the device workspace it currently controls; old device sessions are revoked for the claimed profile. Existing accounts require their password; matching an email/name never grants ownership. Reviewer keys and signed key cookies no longer grant review access.
- Profile, draft, upload and submission ownership use stable contributor IDs. Published story attribution remains a snapshot while story records carry a profile FK. Public profile responses include the attribution name, language and published stories only; no email, private bio, draft, storage key or credential. Portal account changes/logout clear cached private UI data.
- Development fixtures: demo/nomsa/thabo/amina contributor accounts map to the four existing fixed catalogue stories; reviewer is a separate role. Each contributor gets an editable private draft. `scripts/asante/accounts.py` generates/reuses `.env.asante-test-accounts` (ignored, mode 0600, excluded from Docker images), sends passwords to the API seed through stdin and prints no passwords. Rerunning preserves hashes, ownership, edited drafts and decisions. It refuses mismatching existing credentials or roles rather than resetting accounts. No new publication is seeded.
- Plan: run account/login/logout/expiry/role/owner-isolation/seed tests in disposable services, apply the additive local migration, refresh affected services, provision the five accounts and verify all five through the clean public URLs. Preserve current volumes and anonymous workspace data. The user will perform visual/use-case acceptance; email verification/recovery and provider SSO remain pending. Rollback retains the additive tables and original data; restore app images instead of destructive schema downgrades.

Account activation evidence: applied migration 0004 locally, provisioned the five development accounts and four contributor drafts with `scripts/asante/accounts.py`, and refreshed the three app services with the verified images. The map, portal and dashboard warm-up requests return HTTP 200. Stored public fixture ownership links are explicit; unrelated contributor workspaces/media remain intact. Automated API evidence `logs/codex/execution-20261107T141149168831Z.json`: 12 unit/functional cases and eight real PostGIS/MinIO integration cases pass, including account roles, password failures, logout/replay/expiry, throttling, seed preservation, public profile privacy and sign-in after an API lifecycle. Website evidence `execution-20261107T140938449132Z.json`: 14 Vitest cases plus types/build. Dashboard evidence `execution-20261107T140936461131Z.json`: three Vitest cases plus types/build. Contracts: 14 pass in `execution-20261107T140402169907Z.json`. The new rendered dashboard login test initially exposed missing automatic JSX transformation in Vitest; corrected the existing test configuration and reran successfully. Live account checks and final user handoff follow.

Final live evidence: `logs/codex/execution-20261107T141303220759Z.json` passes all 11 HTTP/service checks through the clean localhost proxy, including every generated test account's sign-in/profile restoration/role boundary/sign-out and denial of cross-contributor draft writes. This was run after final API/website/dashboard refresh; migrations and named volumes are retained. Four existing catalogue fixtures now have linked contributor profiles, and four editable private test drafts are available. The reviewer queue is intentionally empty until a contributor submits real uploaded media; setup does not fake a submission, decision or publication.

Credentials were shared with the user in the private handoff only and are reusable from ignored `.env.asante-test-accounts`. Public docs contain only test email addresses, setup commands and credential-file key names. Visual/use-case acceptance is pending the user's testing. Test sequence: sign in as a contributor at `/asante/portal/`, open/save/reload their draft and public profile, upload supported media and submit with consent; sign in as reviewer in a separate browser session at `/asante/review/`, inspect/play the packet and record a reasoned decision. Log out and back in to verify restoration. Email verification/recovery, provider SSO, revised-submission workflow and deliberate map publication remain outside this slice.

## Research-room baseline restored — automated_verified; browser review pending (2026-11-09)

Authorized scope: remove the later portal-as-chat / research-team / field-report / talk-gateway product surface and restore the earlier Asante Research room that already worked on this project. Codex commentary remains allowed in these plan docs; product UI must not advertise removed chat/report features.

Current integrated behaviour:

- Portal sidebar Research room calls `POST /v1/workspace/projects/{id}/workers` for `planner` and `researcher`.
- `asante_api.ai.research` collects web, news and social/video candidates (DuckDuckGo + Google News RSS + YouTube seed catalogue), enriches a bounded set of pages, and raises when no usable sources remain.
- `asante_api.ai.workers` runs planner suggestions (live provider or fixture), researcher packets, and the deterministic `asante.verification.v1` verifier used by unit checks.
- Accept/reject plan decisions remain contributor-owned project fields. Language/structure/provenance tiles stay marked unavailable until those slices land.
- Removed from the current product baseline: `ResearchChat` / `ResearchTimeline` / research-team multi-agent runs, field-report editor/PDF/share pages, portal review chat, and `/asante/talk/` Ollama gateway code. Compose continues to run website + dashboard + API + Postgres + MinIO + proxy only.

Evidence on 2026-11-09 after rebuild/refresh: API worker baseline unit tests 8/8 pass; Asante website Vitest 14/14 and TypeScript check pass; live `/asante/`, `/asante/portal/` and `/asante/api/health` return 200. User browser verification of Prepare plan / Find evidence remains pending.

## Contributor story chat — automated_verified; local browser smoke passed (2026-11-09)

The user explicitly reauthorized a surgical contributor portal chat slice, superseding the earlier removal of portal-as-chat. Implemented the existing portal in a chat shell: project/published-story chat rail, bottom-right New chat shape popup, story context and notes in the thread, Asante team plan/research actions with working states, plan accept/reject, candidate-source results, composer upload, profile popup, upload consent, and human-review submission popup. Project selection is represented in `?project=` and published story selection in `?published=` so refresh restores the open conversation. Published-story history is labeled illustrative and is not represented as true worker/reviewer run history. Existing planner/researcher API workers and research collector remain in use.

Leave unfinished: transcription/translation/video jobs, field-report/PDF/share/collaboration, Ollama talk gateway, review desk redesign, HLS/captions/dubbing, deployment. Human gates remain for plan decisions, storage consent, and submission; nothing auto-publishes. No secrets are included in project files.


## Video upload, transcription and analysis — automated_verified; local smoke passed (2026-11-09)

Authorized scope: verify video uploads, preserve the original and attach upload derivatives, enqueue local Whisper transcription and ≤4-frame visual-analysis jobs at submit, and show honest drafts in the reviewer dashboard. No transcript is fabricated when Whisper is unavailable or silent. Video observations are model interpretations, never heritage proof; review and publication remain human-gated. `faster-whisper` runs locally in the API/job-worker image; Ollama is preferred for configured text/vision analysis and cloud providers are used only when Ollama is not configured. Compose owns the `job-worker` service; no separate Asante AI image is needed.

The contributor portal accepted a 30-second H.264/AAC clip derived from `Folktale Stories By Unstoppable.mp4` in `/Users/vavu/Downloads/TestData`; the original 12-minute file correctly exceeds the existing 10-minute upload bound. After explicit storage consent the clip was uploaded and server-verified, then submitted with explicit review consent. The Docker job-worker ran `faster-whisper` locally and attached an English timed transcript draft (four segments); Gemini produced a four-keyframe scene-analysis draft. The packet remained pending human review and nothing published automatically. Both draft fields, job rows and statuses are persisted on the submission. The internal review route now proxies to the dashboard app.

Evidence: API unit + functional tests passed (33/33); video upload → submit → mocked job drafts reviewer integration test passed; dashboard check passed (3 Vitest tests plus production build); repository contracts passed (15/15); Compose config validated. Final containers were rebuilt/recreated, `job-worker` is running, stale orphan `asante-ai` was removed, and the review URL returned 200 from the dashboard app. Live local processing with the TestData-derived clip produced an English faster-whisper transcript draft and a Gemini analysis draft based on four keyframes. The full API integration check still has two pre-existing failures outside this slice: the migration test expects revision `0004_accounts_and_story_profiles` rather than current `0012_project_messages`, and the workspace test expects a removed `/workspace/projects/{id}/download.zip` route. Translation polish, HLS/captions/dubbing, wider job retry/cancel controls, and deployment remain unfinished.

## Role-based workspace entry and local route choice (2026-11-09)

Sign-in now routes contributor accounts to `/asante/portal/` and reviewer accounts to `/asante/review/`, whether sign-in starts at the portal or dashboard. Opening the wrong workspace checks the authenticated server role and redirects accordingly. The review screen offers a labelled clean presentation URL/direct configured port switch, preserving the active review path, query and hash. The shared Localhost `/asante` proxy mapping already forwards to the configured Asante port, so its separate proxy configuration required no change.

Verification: dashboard and website named checks pass; Compose configuration validates; `http://localhost/asante/review/` and `http://localhost:8082/asante/review/` both returned HTTP 200 after refreshing the website and dashboard containers. User browser acceptance of signing into each role and using the route switch remains pending.

## Field-report plan editor, exports and sharing (2026-11-09)

Implemented the story plan as a structured field report within the existing contributor chat flow. The report builder reuses stored planner/researcher project output; it does not rerun those workers. View and edit share a typed document model, with section-level autosave, attributed related-image support when supplied by research, and chart/table rendering. Contributors can download PDF, text and JSON, create a read-only share token, and invite/revoke existing contributor accounts as viewer (`reader`) or editor. API role checks protect reads/writes, submitted projects remain frozen, and share operations never accept or publish a story. Public share pages live at `/asante/plans/{token}/`. Existing migration `0011_plan_shares` already had the required tables; ORM mappings/routes were added without a new migration.

Changed areas: `app/services/api/asante_api/{models.py,plan_documents.py,workspace.py,main.py,story_packet.py}`, Asante portal report/document/share components and styles, the token share route, API/frontend tests, `scripts/codex/checks.py`, and the frontend/backend specifications. Website Docker contexts now exclude host build/dependency folders. No chat redesign, research collector rewrite, media processing or deployment changes were made.

Verification on 2026-11-09: plan document API unit tests pass (2/2); API unit/functional stage passes (35/35); plan-share role/export integration passes, including anonymous read, viewer write denial, editor save and updated public read. Asante website Vitest passes (19/19), TypeScript and production build pass; repository contracts pass (15/15). API and Asante were rebuilt/recreated. API health and both `/asante/plans/demo/` clean-proxy and direct-port routes return 200. The broad API integration stage still has two unrelated existing failures: its migration assertion expects `0004_accounts_and_story_profiles` while current Alembic head is `0012_project_messages`, and its workspace test expects a removed ZIP download endpoint (404 vs expected 403). Applying migration head to the live DB is blocked because its recorded revision `0013_drop_project_messages` is absent from this checkout's migration tree (which ends at `0012_project_messages`); no stamp/downgrade was attempted. Fresh-database integration setup upgrades through 0012 and validates the share schema/role behavior. The share page is dynamically served; user browser acceptance remains pending.

Browser handoff after refresh: sign in as a contributor, open a project with a prepared plan, choose **View plan**, then **Edit plan** and change a section to observe autosave. Use **Download report** to choose PDF, text or JSON. Choose **Share report** to copy the `/asante/plans/{token}/` link and invite an existing Asante account as Viewer or Editor. Open the link signed out to confirm read-only access; sign in as the invited editor to confirm editing. Plan acceptance and submission continue through their existing human controls.

## Reviewer privacy and optional supporting evidence — automated_verified; live queue verified (2026-11-11)

The review projection now excludes contributor planner/researcher fields, field reports, worker traces, and source citations, including nested assessment job results. Reviewer-visible worker activity excludes planner/researcher runs. Terminal provider failures or malformed/unavailable assessments are marked `attention` for human judgment rather than blocking approval; queued/running assessments still block. The existing “The River Speaks” packet is therefore actionable in the human review gate without exposing its private research.

Contributors may optionally upload a verified PDF (25 MiB maximum) alongside the original recording. The PDF is stored under a separate purpose, linked to the frozen submission, and exposed only through the authenticated reviewer supporting-document route. The contributor UI labels research as private and provides the optional PDF picker; the dashboard provides an **Open supporting PDF** link when present. Migration `0015_supporting_documents` was applied to the local database.

Evidence: API named check passes 55 unit/functional tests and 13 integration tests; Asante website named check passes 33 tests plus TypeScript/production build; dashboard named check passes 4 tests plus TypeScript/production build; repository contracts pass 15 tests. Live catalogue query returns 4 published stories (3 non-demo). Live review queue for `submission_e66e9690f9fa49c6b09b1f4f0f5669d1` returns `may_approve: true` with no private research keys. No reviewer decision was made automatically.

## Approval now publishes to the public map — live verified (2026-11-11)

The reviewer `approve` decision now calls `publish_approved_submission` in the same database transaction as the saved decision. Reviewer API responses include published story ID/slug/time, and the dashboard confirms “Approved and published” and renders the recorded publication state. The already-approved `The River Speaks` packet was published idempotently using the same service; it now appears as `the-river-speaks-0f5669d1` at District Six with its original video media and poster routes. Live public catalogue count is 5. No approval or publication is performed without a reviewer decision. Live map catalogue verification passed after rebuilding API/dashboard; named tests were not rerun for this follow-up.

The published story also receives timed caption tracks from completed transcription and translation jobs. Job completion refreshes captions for stories that were already published, so captions that finish after approval are attached as well. The River Speaks now serves 23 English, 2 isiZulu and 12 Sesotho timed cues through its public captions endpoint. These are AI-generated drafts and may be inaccurate; review remains advisable.

## Discovery shuffle and foldable review sections (2026-11-11)

The map discovery list now shuffles on catalogue refresh, when reopening the list, and through a direct Shuffle control. Review packet sections (media/location, claim, authorship/consent, assessment, media processing, guideline findings, decision, and publication status) are foldable; worker activity and decision history are foldable as well.

Reviewer dashboard navigation no longer includes worker traces, and dashboard loads no longer request that endpoint.

Decision history now loads the public catalogue and lists every currently published video, showing its contributor/location and linked approval reason/date when available. Legacy catalogue videos without submission decisions are clearly labeled as having no linked reviewer decision record; a separate section retains the full recorded decision log.

## Reviewer evidence assessment wiring (2026-11-11)

Reworked the durable reviewer assessment to consume a server-built allowlist: submitted title, description/claim, landmark/location, original narrative, completed English transcription (or a clearly marked English translation draft), the contributor-attached PDF's extracted text, and bounded video scene observations. The reviewer model cannot receive contributor research, research briefs, reports/plans, source URLs, or worker traces. Its instruction states that these submission materials are unverified and do not constitute independent fact-checking or an authenticity judgment. Exact quoted references are accepted only when they match supplied transcript/PDF/scene text.

Assessment jobs now wait until transcription, translation and scene-analysis jobs are terminal. Verified PDF extraction is bounded to ten pages, 12,000 characters and a 20-second Poppler run. The panel shows real job state/provider/schema/prompt/hash and evidence labels; an empty assessment no longer renders as `unknown · · prompt`. Source URLs are also removed from reviewer packet output. Migration `0016_requeue_review_evidence_v2` requeued old assessments for undecided packets, without changing human decisions or published records.

Verification: API named check passed 55 unit/functional and 13 PostgreSQL/MinIO integration tests, including transcript + PDF evidence and job ordering (`logs/codex/execution-20261111T154700829267Z.json`). Dashboard check passed 4 tests, TypeScript and production build (`logs/codex/execution-20261111T154250585190Z.json`). Applied migration 0016; the live QA fixture regenerated an `asante.assessment.v2` result with English-transcript readiness, and reviewer/portal routes plus API health returned HTTP 200. Visual browser acceptance remains pending.

## Review workspace dashboard and queue controls (2026-11-11)

The reviewer sidebar now starts at a Dashboard with queue, published-video, decision-count and recent-submission summaries. The Review queue filter opens a custom accessible status dialog; its choices apply immediately, and Escape/backdrop/close dismiss it. The submission list can collapse to a narrow status-marker rail. Selecting a project stores its submission ID in the URL, and reloading that URL restores the same packet in the Review queue. Reviewer logo and email share one line; the contributor portal now keeps its logo and account email on one line as well.

Added one clearly marked `TEST ONLY` pending-review video packet from a 25-second excerpt of `/Users/vavu/Downloads/TestData/Folktale Stories By Unstoppable.mp4`. The local QA fixture has an explicit synthetic narrative, no heritage claim, and remains `pending_review`; it was not approved or published. Its source file remains outside the repository.

Verification: dashboard named check passed (4 tests, TypeScript and production build); Asante website named check passed (33 tests, TypeScript and production build). Dashboard and website services rebuilt/recreated; reviewer and portal routes both returned HTTP 200. The reviewer API returned nine queue items and confirmed the QA fixture is `pending_review` with zero decisions. User browser acceptance of modal interaction, collapsed queue selection, refresh restoration, and responsive logo/email fit remains pending.

## Legacy pending review job recovery (2026-11-11)

Opening the authenticated reviewer queue now calls an idempotent API repair endpoint for pending packets. Missing transcript, translation, video-analysis and assessment jobs are created; cancelled jobs of those types are reset and queued with the current safe packet/media inputs. Approved/rejected packets and completed jobs remain untouched. This allows older submissions to complete their evidence assessment after a cancelled processing run without changing the human review status or decision history.

The Haile Selassie submission `26798a75509850ed8bbde999f9f5e17a` already has a verified 8 MB MP4 with a stored checksum and matching TestData filename, so no duplicate media was attached. Verification: API named check passed 56 unit/functional and 13 integration tests (`logs/codex/execution-20261111T155659584739Z.json`); dashboard check passed 4 tests and production build (`logs/codex/execution-20261111T155721366071Z.json`). The API, job worker and dashboard were rebuilt/recreated. The browser session was signed out during the live check, so the authenticated queue repair has not yet been triggered for this packet; it will run when a reviewer next opens the queue.

## Reviewer worker trails (2026-11-11)

Evidence comparison and each transcription, translation, and scene-analysis section now open a worker-trail popup. Durable submission jobs record bounded timestamped checkpoints, worker output, retry/failure events, and the allowed input summary; reviewer UI includes provider/status and saved output. Trail details are observable actions and outcomes, not hidden model reasoning. Contributor research, raw PDF text and prompts stay private. Historical jobs without step events show their actual saved lifecycle timestamps and identify the missing step-level history rather than inventing it.

Verification: API named check passed 57 unit/functional and 13 integration tests (`logs/codex/execution-20261111T161713004994Z.json`); dashboard named check passed 4 tests, TypeScript and production build (`logs/codex/execution-20261111T161808410912Z.json`). Rebuilt/recreated the API, job worker, and dashboard. New/retried jobs will retain step checkpoints. Existing completed runs with no stored event trail will show only their actual persisted lifecycle timestamps and outputs.
