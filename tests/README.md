# Asante tests

## Named execution checks

Create and activate the `asante-codex` Conda environment as described in [ENVIRONMENT.md](../documentation/ai/references/ENVIRONMENT.md). From the repository root, use `python scripts/codex/checks.py <job>`:

- `preflight`: setup files, quiet Compose validation, Docker/services and Git state.
- `contracts`: deterministic repository/Compose/script unit cases.
- `website`, `dashboard`, `api`: fresh images and isolated service checks; website jobs include TypeScript and production compilation.
- `http`: strict live route/query/media checks and running-service verification.
- `all`: all application jobs above.
- `mcp-setup`: provision dedicated reader accounts and local project registration; `--no-config` is the CI variant.
- `mcp-verify`: positive reads, denied DB/storage writes, SDK protocol session and actual project launcher.

Codex execution summaries are generated under ignored `logs/codex/`. Test evidence is also written under ignored `logs/tests/`, grouped into `unit/`, `functional/`, `integration/`, and `e2e/`. One run may appear in more than one category when it covers multiple test types. The category report links to its full Codex execution summary. No generated report is written directly in the `logs/` root. A failed check returns nonzero. Service checks use disposable containers and do not restart the live API, alter live review records or delete volumes. They do not refresh the live app: update affected running services before testing new live code through HTTP. Use `--skip-build` only immediately after building the relevant images.

Codex MCP setup/scopes/recovery are in [CODEX_MCP.md](../documentation/ai/references/CODEX_MCP.md). Its integration suite intentionally skips outside the isolated tool container; `mcp-verify` runs it in the correct environment and additionally checks denied writes. Fixture creation/cleanup touches only named Codex probes.

The test folders map to the project test categories:

- `unit/`: small repository and application contracts
- `functional/`: behavior across a defined Asante feature boundary
- `integration/`: Docker and service integration checks
- `e2e/`: public Asante route and API checks against a running stack

Run the host-side Python contract tests with:

```bash
python scripts/codex/checks.py contracts
```

The end-to-end tests skip routes that are not running. The full website test suites run inside the website containers after their npm dependencies are installed. API and Codex MCP integration tests also run in their dedicated containers; their external dependencies are intentionally not installed in the lightweight host Conda environment.

The Asante API unit and functional tests run inside the API container because their FastAPI dependencies are container-managed. The API check also runs a separate database integration test against a uniquely named temporary database on the running PostgreSQL service. It requires the configured Asante database role to create and drop databases; cleanup targets only that generated database name.

```bash
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api \
  python -m unittest tests.unit.test_api tests.functional.test_api_routes -v
```

The explicit migration command, when a local migration is intentionally being applied, is:

```bash
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api \
  python -m alembic -c app/db/alembic.ini upgrade head
```

The API integration suite is run through `python scripts/codex/checks.py api`; it creates an isolated temporary database, applies all migrations twice, inserts the public demo catalogue twice, checks database counts/PostGIS behavior and both catalogue API versions, then removes only that temporary database. AS-03 coverage includes published-only results, stable cursor paging, search/language/region/media filters, bbox filtering across the antimeridian, distance ordering/annotation, explicit nearby radius and nearby cursor paging. It also creates a uniquely named temporary MinIO bucket, seeds the demo twice, verifies full/HEAD/range playback through the database-resolved URL, and removes only that test bucket. Missing storage returns 503. It does not migrate or reset the developer application database.

The explicit developer database setup for catalogue persistence, after refreshing the API image to include the new migration and code, is:

```bash
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api \
  python -m alembic -c app/db/alembic.ini upgrade head
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api \
  python -m app.db.seed
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api \
  python -m app.db.seed_media
```

The seed only inserts missing fixed demo rows; it does not update an existing row or overwrite contributor data. Contributor workspaces, drafts and review records are now durable. Apply migrations before refreshing affected app services.

## Website build test cases

Automated non-GUI cases cover onboarding preference validation/resume/completion, global catalogue loading with optional coordinates, map discovery transitions and GeoJSON geometry, combined language/search filters, supported file types and size limits, planning proxy requests and errors, reviewer filters, approval blockers, packet intake, reviewer authorization, decision reasons, and final decision conflicts. The previous identity-string placeholder tests have been replaced.

Use `ASANTE_REQUIRE_SERVICES=1` when running live route checks against an expected running stack so unavailable routes fail instead of being skipped.

## User browser test checklist

| Flow | Steps and expected result |
|---|---|
| Entry and guide | Open /asante/. Version 2 starts with a centred welcome, then moves to and spotlights search, location, the first story, and the contributor button. The active target remains usable. Test Back, Skip, Escape, reload/resume, Replay guide, scroll and resize. |
| Location fallback | Deny location at the location step. Story browsing/search still works. Allow location separately and check accuracy feedback and the map circle. |
| Discovery | Browse without location, then enable a location far from South Africa. Every story and landmark remains accessible. Search by place/contributor/region and language, select any story, and check its location. Show all resets search and map extent. |
| Remote playback | Choose “A place to begin — audio demo”. Press Play, pause, seek, reload and resume. Read its transcript and synthetic-demo label. The source is only attached after Play. Confirm HTTP 206 range responses; other records still disclose missing media. |
| Map failure | Block map tile requests. The story list and search remain usable. |
| Contributor profile | Open /asante/portal/. Import any existing Asante browser profile/drafts using the explicit import action; verify the backup download and cleared Asante storage. Create/save a profile with storage consent, reload and verify restoration. Sign in with a contributor account; sign out and back in to verify restoration. Email verification/recovery remains pending. |
| Project | Create a project, enter title/place/audience/narrative, switch sections, and reload. Draft changes remain. Duplicate a project from Overview. |
| Planning | Open Research room, prepare a plan, then accept/reject it or edit the brief. Source notes remain contributor-supplied. Try an unavailable API and retry. |
| Media preparation | Try an unsupported/empty/oversized file, then a supported audio/video file. Preview starts only when played. Check file metadata/checksum. Give storage/analysis consent and verify real upload progress, server verification, reload playback and the stored checksum. |
| Submission | Preview attribution, language, place, source, and media status. Submission requires explicit packet consent. Send once and note the submission ID. |
| Human review | Open /asante/review/. Sign in as reviewer@asante.test with its generated password; refresh the queue to see the submitted packet. Wrong passwords and contributor accounts must fail review access. Open the packet and inspect narrative, evidence, credit, consent, and findings. |
| Decision | Missing/unverified media is rejected before submission. Enter a reason of at least 10 nonblank characters and request changes, escalate, or reject. Check durable Decision history and stale-version rejection. Approval remains a human action and does not publish; rejection is final for that packet. |
| Responsive/accessibility | Check mobile widths, list collapse, queue cards, keyboard focus, guide focus loop, Escape, reduced motion, long story titles, and readable contrast. |

These are browser tests for the user; Codex does not claim visual approval from HTTP or unit-test results. The demo and privately uploaded originals are playable. Other illustrative public stories still await original media.

## Workspace persistence integration

The `api` job also runs `tests.integration.test_workspace_persistence` against a uniquely named disposable PostgreSQL database and MinIO bucket. It verifies import idempotency/hash readback/download, profile/draft restoration, optimistic conflicts, two private device sessions with owner isolation, real MP3/WAV/OGG/MP4/WebM uploads, exact range bytes/content types and server SHA-256, replay/expiry/truncation/oversize/spoof rejection, private byte-range playback, immutable submitted revisions, idempotent submission, reviewer access/version conflicts and persisted decision history after a fresh API lifecycle. Cleanup targets only the generated test DB/bucket; temporary probe files are checked for removal. Vitest tests verify cleanup occurs only after successful DB/archive verification, preserves unrelated browser data, and retains failed/concurrently changed records.

Manual nonvisual handoff: save a draft, reload, upload original audio/video, reload/play/seek, submit once, review with a reason, refresh/restart the API, and confirm profile/draft/media/submission/decision still exist. Check stale saves/decisions fail and another device session cannot read private media. No approval automatically publishes content.

## Account test setup and acceptance

After applying migration 0004 and refreshing the app services, run `python scripts/asante/accounts.py` in the host `asante-codex` environment. Test passwords live only in ignored `.env.asante-test-accounts` (0600), with keys `ASANTE_TEST_<DEMO|NOMSA|THABO|AMINA|REVIEWER>_PASSWORD`. No plaintext password belongs in committed docs or generated test reports. The setup is repeatable and must preserve changed drafts/password hashes/review decisions. Four known catalogue fixtures are linked by stable contributor FK; each contributor has an editable private draft. No review or publication is seeded automatically.

The API suite verifies Argon2 salt/verification, normalized email, forbidden role/owner fields, registration consent and explicit legacy linking, session rotation, logout/replay/expiry, session-bound CSRF token enforcement, generic wrong-password/unknown-user errors, persisted login throttling, role checks and removal of the key bypass. Real service cases check public profile privacy, story/profile links, private owner isolation, reviewer identity, seed preservation and re-login after a fresh API lifecycle. Website tests include rendered email/password forms; both sites pass TypeScript and production builds.

The named `http` job now includes `tests.e2e.test_accounts`: all five local accounts sign in through clean URLs, restore their own profile/drafts/published-story links, exercise the correct role boundary and sign out; one contributor cannot overwrite another contributor's draft. These checks create/revoke test sessions and update login counters, but do not change drafts/review decisions. With ASANTE_REQUIRE_SERVICES=1, missing account setup fails rather than skipping. CI provisions its own ignored credentials before running this job.

When `ASANTE_ENV=development`, the portal and reviewer login pages also load a private **Open a demo profile** dropdown from `/v1/auth/demo-accounts`. Selecting a contributor or reviewer profile calls the development-only `/v1/auth/demo-login` endpoint and routes to that role's workspace; passwords remain server-side in the ignored `.env.asante-test-accounts` file. The picker is unavailable outside the development environment.

### Stage A portal guide

Local browser walkthrough only: open `http://localhost/asante/portal/`, sign in as the Nomsa contributor, then follow the guide targets in order: `[data-guide="portal-role-landing"]` → `[data-guide="portal-new-chat"]` → `[data-guide="portal-shape"]` → `[data-guide="portal-research-brief"]` → `[data-guide="portal-save-note"]`. Create/save one draft while walking the shape and research-brief steps; do not upload or submit. `Play Portal Guide` restarts the versioned `asante.portalGuide.v1` preference. Stage B begins with research workers and remains a separate browser walkthrough.

### Stage B portal research workers

Local browser walkthrough only: open `http://localhost/asante/portal/`, sign in as Nomsa, select a saved draft with a completed research brief, then choose `Play Research Guide`. Follow the targets in order: `[data-guide="portal-run-planner"]` → `[data-guide="portal-watch-activity"]` → `[data-guide="portal-plan-decision"]` → `[data-guide="portal-run-researcher"]` → `[data-guide="portal-field-report"]`. Run the planner, open the recorded activity modal, explicitly accept or reject the plan, run the researcher, then open the field report and candidate sources. The guide persists in `asante.portalResearchGuide.v1`. Use the configured localhost worker backend; fixture/deterministic output must be labelled as fixture. Do not upload or submit.

### Stage C portal media drafts

Local browser walkthrough only: open `http://localhost/asante/portal/`, sign in as Nomsa, select one unsent draft, and choose `Play Media Guide`. Follow `[data-guide="portal-upload-open"]` → `[data-guide="portal-upload-consent"]` → `[data-guide="portal-upload-file"]` → `[data-guide="portal-upload-verified"]` → `[data-guide="portal-media-drafts"]`. Give storage/analysis consent, choose one short clip such as `/Users/vavu/Downloads/TestData/productionv2/folktale_45s.mp4`, upload once, wait for server verification, then inspect durable `mediaJobs`, `transcriptDraft` and translation states. The guide persists in `asante.portalMediaGuide.v1`. Keep queued/running/succeeded/unavailable labels honest; never claim draft captions are publishable. Do not submit or review the story. If the upload fails, stop and abandon that draft before retrying so duplicate media is not created.

### Stage D portal submit

Local browser walkthrough only: use the same unsent, verified-media draft after Stage C and choose `Play Submit Guide`. Follow `[data-guide="portal-submit-open"]` → `[data-guide="portal-submit-preview"]` → `[data-guide="portal-submit-consent"]` → `[data-guide="portal-submit-send"]` → `[data-guide="portal-submission-id"]`. Open Review & submit, inspect the server-built packet preview, confirm explicit human-review consent, send once, and record the returned submission id. Do not open the reviewer workspace in this stage; Stage E uses the captured packet separately.

Browser acceptance: sign in at /asante/portal/ as Nomsa, inspect her linked published story and public profile, edit/save/reload a private draft, upload a supported recording and submit with consent. In another browser session, sign in at /asante/review/ as the reviewer and inspect/play the packet and record a reasoned decision. Sign out and back in as each role to verify persistence. A contributor must not open the reviewer queue; wrong passwords must fail. Test a second contributor and confirm Nomsa's private draft/media is absent. Approval still does not publish automatically.

### Stage E reviewer packet guide

Local built-in-browser walkthrough only: open the submitted packet at `/asante/review/?submission={submission_id}` in a separate reviewer session and choose `Replay reviewer guide`. Follow `[data-guide="review-sign-in"]` → `[data-guide="review-queue-nav"]` → `[data-guide="review-packet"]` → `[data-guide="review-media-drafts"]` → `[data-guide="review-decision"]`. Inspect the frozen narrative, attribution, location, consent, original recording, HLS/media jobs, transcript and translation drafts; play the original recording when available. Stop before choosing approve, request changes, escalate, or reject: the decision remains a human gate.

### Map and listener playback

Local built-in-browser walkthrough only: open `/asante/` (it redirects to `/asante/map/`), confirm the Africa-focused map and catalogue render, select a story card, press Play, open the caption picker, and choose an available transcript/translation track. Confirm the playback surface exposes timed caption text and that the story location remains visible. The Next page-extension setting excludes `*.test.ts` files from route discovery so the public root route is not shadowed by `app/page.test.ts`.

### Real-world contributor submit flow (automated)

Prefer the HTTP e2e that hits the live local proxy (catches API/auth bugs without a disposable fixture API):

```bash
ASANTE_REQUIRE_SERVICES=1 ASANTE_BASE_URL=http://localhost \
  python -m unittest tests.e2e.test_contributor_submit_flow -v
```

It signs in as Nomsa, creates a project, rejects upload without consent, uploads `tests/fixtures/media/sample_video.mp4`, rejects upload replay and cross-contributor upload, previews+submits with a matching `preview_hash`, rejects a forged hash, confirms the contributor cannot open `/review/queue`, confirms the reviewer sees the pending packet (not published), and checks logout revocation.

Optional UI smoke (requires Playwright + Chrome + Node):

```bash
ASANTE_BASE_URL=http://localhost node tests/e2e/portal_submit_flow.mjs
```

Evidence lands under `logs/tests/e2e/portal-submit-flow/`. Research-room Playwright remains `tests/e2e/portal_research.mjs` with the disposable fixture API described above.

## AS-07/12 research browser journey

`app/websites/asante/app/components/ContributorWorkspace.test.tsx` runs real React/DOM button interactions in the named website check, using typed deterministic API fixtures. It covers creation/failure, questionnaire saves/reload, sequential versions, worker failures/retry, double starts and account/project switching.

For a browser journey with real server persistence and deterministic Python workers, refresh the live website first, then start the test-only API in a disposable container. This test process creates its own database and MinIO bucket, cleans them up on graceful stop, and never enables fixture workers in the normal API:

```bash
docker compose --env-file .env -f infrastructure/docker-compose.yml run --rm -d --no-deps \
  --name asante-research-browser-fixture -p 127.0.0.1:18083:8000 \
  -e ASANTE_BROWSER_FIXTURE=1 api python -m tests.e2e.research_fixture_api
ASANTE_RESEARCH_FIXTURE_URL=http://127.0.0.1:18083 node tests/e2e/portal_research.mjs
docker stop asante-research-browser-fixture
```

The browser script requires an installed Playwright module and Google Chrome. Set `ASANTE_PLAYWRIGHT_MODULE` to an installed module's absolute `index.mjs` path if it is not normally importable; `ASANTE_BROWSER_CHANNEL` can select another installed Playwright browser channel. It opens `http://localhost/asante/portal/` and forwards only that browser context's API requests to the disposable API. The live proxy/API configuration remains unchanged. `ASANTE_BASE_URL` can select another Nginx proxy URL. Screenshots, a Playwright trace and machine-readable results are generated under `logs/tests/e2e/portal-research-activity/`. These fixtures verify orchestration and persistence, not live evidence relevance or model quality.

The current browser fixture additionally verifies new-project/partial-questionnaire autosave, autosave failures/retry, live-readable delegation/collector events, the full activity popup and mobile layout. The website's DOM suite verifies queued edits during autosave, explicit profile-storage consent and no unintended worker starts. Older Step 1/Step 2 browser evidence remains under `logs/tests/e2e/portal-research/`.
