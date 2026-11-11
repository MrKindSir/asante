# Asante frontend implementation specification

Use the feature registry in [PLANS.md](../exec-plans/PLANS.md), target contracts in [BACKEND.md](BACKEND.md) and visual rules in [DESIGN.md](DESIGN.md). This file breaks the website work into implementable slices. Prototype behavior is not authenticated or production behavior.

## Existing files and boundaries

| Existing file/area | Responsibility to preserve |
|---|---|
| `app/websites/asante/app/page.tsx` | Map entry route; no marketing page before the map |
| `app/components/MapView.tsx` within that website | Map lifecycle, catalogue, selection and current UI composition |
| `app/components/GuidedTour.tsx` | Moving, anchored tour and target spotlight |
| `app/components/StoryPlayer.tsx` | User-initiated media, transcript and saved position |
| `app/components/story-domain.ts` | Current types, catalogue filtering, media validation and API helper |
| `app/portal/page.tsx`, `app/components/ContributorWorkspace.tsx` | Contributor route and prototype workspace |
| `app/websites/dashboard/app/page.tsx`, `review-domain.ts` | Reviewer queue/detail and decision logic |
| Each website's `app/globals.css` | Shared look-and-feel tokens and layouts; central token consolidation belongs to AS-00 |
| Each website's `app/layout.tsx` | Figtree/Syne via `next/font`; CSS variables `--font-asante-sans` / `--font-asante-display` |

The shortened `app/components` paths above are relative to `app/websites/asante`. Keep all code in the two established website directories. Extract focused components/hooks when touched; do not invent a different root layout.

## Current look and feel (2026-11-07)

Quiet cartography, not cream editorial. Both the Asante website and the review dashboard share the same token set and type pairing documented in [DESIGN.md](DESIGN.md).

- Ground: cool stone `--paper` with soft radial wash; panels use translucent `--surface` and light blur over the map.
- Action: teal `--clay` for primary buttons, focus rings and selected pins; muted gold `--sun` only for tour spotlight.
- Type: Figtree for UI copy; Syne for brand wordmark and story/section headings.
- Shape: 6 px radius, square tags, restrained shadow; keep existing map/panel geometry contracts.
- Preserve route composition and class names when adjusting style; change tokens and surface treatment before inventing new layout chrome.

## AS-00 — frontend preparation

- **AS-00.a:** separate map lifecycle, catalogue loading, selection and permission behavior into focused hooks/components. Separate portal forms, worker results, upload preparation and submission preview. Separate review queue, packet details and decision form. Avoid a wholesale rewrite.
- **AS-00.b:** one typed API adapter per website owns proxy prefix, current v1 snake_case mapping and target v2 camelCase mapping, credentials, CSRF, request cancellation and safe errors. UI domain fields use camelCase. Validate required external fields at runtime rather than casting arbitrary JSON to a trusted domain object.
- Add a small shared style/token source only when both app builds/Docker contexts include it. Do not introduce cross-app imports that resolve on the host but fail in containers. Generated API types go to an existing shared responsibility or each app's generated area; document generation rather than hand-edit them.
- Criteria: existing route URLs and prototype tests survive extraction; stale responses do not overwrite current selection/drafts; status/error handling is testable without MapLibre/WebGL.

## Public routes and navigation

Keep `/asante/`, `/asante/portal/` and `/asante/review/` working. Target contributor sections may gain project/profile child routes inside the same website. Target review details may gain submission child routes inside the dashboard. Refresh and Back must restore the selected project/submission.

Next.js base paths are already configured. Internal Next route paths omit the base path; plain browser URLs include it. Do not double-prefix links, static assets or API requests. Test deep links through Nginx as well as root routes.

Local development supports both the clean Localhost proxy path (`http://localhost/asante/...`) and the direct Asante host port (`http://localhost:<ASANTE_HTTP_PORT>/asante/...`). The reviewer dashboard exposes a labelled switch that preserves the current review path, query and hash while changing route mode. Account role selects the workspace after sign-in: contributors go to `/asante/portal/`; reviewers go to `/asante/review/`. Server role checks remain authoritative.

## AS-03 / AS-04 — public map and discovery

### AS-03.a: catalogue adapter; AS-03.b: filters and pagination

Read the full public catalogue through bounded pages; all published stories remain reachable. Cursor paging, search and optional viewport filters follow BACKEND.md. A user in London or Sydney must be able to find and play a Johannesburg story.

Render loading, empty catalogue, no filter match, request failure and partial map failure as different states. Debounce text queries and cancel stale requests. Retain the last good list with a visible stale/error message when a refresh fails.

### AS-04.a: map/pin/list consistency

1. Keep MapLibre in a browser-only component; initialize/remove once per mount.
2. Explicitly size the container and override the library's relative-position rule with sufficient specificity. ResizeObserver calls map.resize after container changes.
3. Attach GeoJSON sources/layers only after style readiness; populate them after either data or style becomes ready. Recreated styles/maps must not lose pins.
4. Cluster dense results; expose pin meaning with labels/list alternatives. A landmark with several stories shows a chooser, not an arbitrary hidden selection.
5. Selecting a story centres its published location and opens its drawer. Account for desktop side panels/mobile bottom sheet so the selected location remains visible.
6. Show the published location and coordinate precision in details even if tile rendering fails. Private contributor coordinates must never enter the public map model.
7. Show all clears optional filters and restores an overview; it does not require or erase GPS consent.

Tests: one map lifecycle per mount, delayed data/style arrival, style retry, multi-story landmark, filter/selection consistency, container resize, missing WebGL and map/list fallback. Browser acceptance: actual visible map and selected pin; HTTP 200 alone is insufficient.

### AS-04.b: optional location and explicit proximity

Request browser location only after the explanatory action. States: off/requesting/granted/denied/unavailable/timed_out. Display an accuracy circle and a coarse accuracy label. Keep precise coordinates transient unless separately consented.

GPS adds distance and may recenter; it does not replace the global catalogue with a nearby-only query. Position-based playback is available only through a separate explicit opt-in, uses foreground location while enabled, and selects a playable story within 150 m. Turning the control off or leaving the page stops position updates and any position-started playback. GPS denial still leaves global discovery and manual playback available.

Tests: denial/timeout still permit global search and remote playback; coordinates supplied as a valid pair; accuracy radius preserved; unmount cancels watch subscriptions if active updates are added.

## AS-05 — moving onboarding tour

### AS-05.a: anchored steps and geometry

| Step | Stable target | Behavior |
|---|---|---|
| 0 | No target | Centred welcome; explain location is optional |
| 1 | `data-tour="search"` | Move beside search: “Get started here” |
| 2 | `data-tour="location"` | Move to location control; allow or continue without |
| 3 | `data-tour="story"`; list fallback | Highlight a real available story; open its details |
| 4 | `data-tour="contribute"` | Move to contributor entry; create profile or keep exploring |

Use the actual element bounding rect and spotlight hole. Highlighted controls remain clickable; surrounding dimmer cannot cover the active target. Recalculate after scroll, resize, responsive layout, async catalogue changes and target replacement. Prefer a non-overlapping side, then flip/clamp to the viewport. Missing targets use a visible fallback or defer with an explanation; never point at an empty coordinate.

### AS-05.b: state and accessibility

Keep versioned local state; current corrected tour is version 2. Support Next, Back, Skip, close, Escape, reload/resume and Replay. Only the welcome is modal; an anchored step must permit keyboard access to its highlighted control. Return focus predictably on dismissal, label step/progress, and respect reduced motion. A new version must not interpret an old centred-only guide as verified completion.

Tests: position beside each target, top/right/mobile viewport bounds, missing/replaced target, corrupted preferences, completed/replayed guide, tab sequence and underlying control clicks. User/browser review must prove that the popup actually moves between elements.

## AS-06 — remote story playback

### AS-06.a: audio and resilient player

The current synthetic demo remains clearly labelled. Add real published assets via AS-10/16.

- Drawer contains title, place, approved credit, original language, media type, publication/source status and playable/unavailable state.
- Attach a media source only after explicit Play, except when the listener has enabled position-based auto-play and a playable story is within 150 m. Do not download story recordings when catalogue cards render.
- Use native controls or an accessible wrapper. Support pause/seek, ranged delivery, safe saved position, transcript, unavailable media and retry. Clear a finished saved position; key positions by story revision/asset so a correction cannot resume at an unrelated timestamp.
- Selecting a different story stops the old player and releases resources. Position-started playback is allowed only under the explicit opt-in described in AS-04.b; list refresh alone never starts playback.
- Persist optional low-data preference; describe actual behavior. Do not advertise quality switching until derivatives exist.

### AS-06.b: video, captions and translation

- Launch video into a focused playback popup with a modal header/close control; closing pauses the video and restores focus to its Play button.
- The popup offers translated-caption choices returned for that published story. Show only timed caption tracks that exist; selecting a language renders its cue against `video.currentTime`. Empty, unavailable and loading states must not substitute full translation text as timed captions.
- With AS-10, choose progressive media or HLS based on asset capabilities; use native HLS when available or a compatible maintained client selected/pinned in that slice. Handle manifest/segment authorization failures.
- Load a poster and accessible text before playback, not full video bytes. Offer available renditions/audio alternatives; low-data mode must change actual selected delivery.
- Keep original and translated versions distinct. AS-13 supplies transcript/timed captions and reviewed language availability. Missing translation is “unavailable/request pending”, never a relabelled original.
- Audio playback also offers the published story's timed caption choices and shows the cue active at `audio.currentTime` in a centered overlay below the map navigation, while the language control stays with the audio player. The review player shows timed draft captions for both media formats. A provider failure appears as unavailable language status rather than an empty choice presented as complete.
- Do not promise reliable Wi-Fi detection; when the browser cannot report network type, use manual data preference and a video confirmation.

Tests: no src/request before Play; stop on selection change; ranges/seek/resume/revision change; invalid saved position; audio/video errors; video popup close/focus; caption language choice and cue synchronization; missing/failed captions; unsupported stream fallback; translation pending/failure; no precise-location gate.

## AS-02 / AS-07 — account and contributor projects

### AS-02 frontend integration

Provide entry/sign-in/sign-up/recovery/logout and expired-session states through the selected identity provider contract. Keep tokens out of browser storage. Protect portal data through server authorization; hiding navigation is not access control.

The current server profile belongs to an email/password account; provider SSO, verified email and password recovery remain targets. The portal offers an explicit import action for old browser records and refuses profile/project conflicts. Future provider sign-in must offer an import preview and must never silently assign browser drafts to another user. Switching provider accounts must clear private UI caches and pending requests.

### AS-07.a: profile, overview and project selection

Profile fields: display name, attribution name, bio and supported language preferences. Overview uses owner-scoped project/status/activity records, not hard-coded counters. Open projects by stable ID; Back/refresh restore the selected route.

### AS-07.b: editor and draft management

Create/rename/duplicate/archive/continue; save title, landmark or chosen published location, story intent, audience, format, original language, sensitivity and narrative. Show saved/saving/offline/failed/conflict states. Keep unsaved text on an API failure; do not report a failed save as saved.

Use expectedVersion for optimistic concurrency. A conflict offers reload/copy/resolve; it must not overwrite a newer revision. Duplicate resets consent/submission/approval. An archived project remains recoverable according to the agreed policy.

Tests: two contributor accounts; unauthorized IDs; reload persistence; import consent; switch-user cache clearing; duplicate resets; failed save; conflict; long names and empty inputs.

## AS-08 / AS-12 — contributor control and research room

Current portal baseline: contributors work in the existing story chat. Planner and researcher remain project workers; their stored plan and candidate sources feed the field-report document described below.

Render Asante workers as bounded roles: planner, researcher, language, structure, provenance and submission checker. Enabled roles are backed by available worker types, not decorative success badges. Language/structure/provenance/submission tiles stay unavailable until those slices land.

- Primary actions: **Prepare a story plan** and **Find evidence sources**. Both call the durable project workers API after saving a dirty draft when needed.
- Show planner suggestion status, fixture versus AI-assisted labelling, run/trace reference, questions/outline and accept/reject. Rejection must not silently alter the story brief.
- Evidence notebook collects an optional claim/question and source URL to guide research; pasting a URL does not verify a claim.
- Researcher results list candidate sources with title, URL, collector/platform, excerpt and status. Web, news and social/video candidates are human-interpreted evidence only.
- Never turn a provider or collector failure into fabricated sources. Empty research must surface as failure, not as a confident empty success.

### Recorded research activity and form autosave

The contributor chat includes a compact activity bubble showing the recorded planner→researcher handoff and recent execution steps. **View full research activity** opens the complete recorded activity in a scrollable modal: saved brief/revision, factual assignments and methods, real collector actions/results, queries, retrieval states, uncertainties, candidate sources and run/trace IDs. The popup provides activity summaries and outputs, not private model reasoning or fabricated worker dialogue. Earlier runs without detailed events are labelled accordingly. Polling and opening the popup are read-only and never start workers.

Story details, research questionnaire (including incomplete answers), and story notes autosave after a short typing pause. Profile autosave requires explicit storage consent. Keep inputs usable during background saves, preserve newer edits and failed saves, serialize writes using returned versions, show visible save state and retry, and flush pending form edits before closing or explicitly starting research. New project autosave retains the form and stable ID. Submitted projects remain read-only. Credentials, uploads, submission, and publication require explicit actions.

In the contributor chat composer, the notes field starts at the same 44 px height as Upload recording (40 px on mobile), can resize vertically to 240 px (180 px on mobile), and keeps longer text scrollable beyond that height.

### Field-report plan document

The project plan is presented as a structured field report, not a chat transcript. **View plan** opens a PDF-like report with the current project title/place, summary, editable sections, attributed research references and any charts, tables or related images present in the stored plan/research output. **Edit plan** opens the same document model with section-level fields and debounced autosave; preserve current values and surface save/conflict failures. Download offers PDF, plain text and JSON for the current saved document. A share popup creates a read-only `/asante/plans/{token}/` link and manages existing-account collaborators with viewer/editor roles. Anonymous users and viewers cannot edit; editor access requires the matching signed-in account. Submitted projects remain frozen, and sharing does not accept a plan or publish a story. Do not invent sources or claim that unavailable related images exist.

Tests: stale worker result, failed run, duplicated click, conflicting/missing source, accept/reject ownership and preservation of original text.

## AS-09 / AS-10 — upload workspace

### AS-09 frontend slices

Request an upload intent for the current owned revision, show file/duration/format limits, get required consent, upload through the actual presigned URL and call server completion verification. Show separate selecting/uploading/verifying/processing/ready/failed/cancelled states. Local checksum/preview is not a verified upload.

Support progress and cancellation; expired URL retry creates or renews the correct intent. Do not assume a Docker hostname is browser-reachable. Revoke object URLs on file/project switch/unmount.

### AS-10 frontend integration

Render processing status, poster, derivative availability and transcript/caption readiness. After a verified draft upload, the workspace projects `mediaJobs`, `transcriptDraft` and `translations` from durable jobs (capped live Modal path; see ASANTE_AI_RUNTIME). Show queued/running/succeeded/unavailable honestly; never invent caption text in the UI. Block publication-related readiness while processing/verification failed. Retain original filename/credit without exposing private bucket keys.

Tests: real upload from browser origin, cancellation, expiry, format spoof, progress, server rejection, reload recovery, asset/project mismatch and cleanup of object URLs.

## AS-14 — submission preview and feedback

- **Implemented 2026-11-10:** the submit popup loads the API-built packet preview from the saved project version, shows the saved field report, narrative, claim, source excerpts/retrieval state, consent scope, media identity and linked planner/researcher traces, and submits the returned preview hash. Unsaved edits must be saved and the preview reloaded before send. A stale hash receives a conflict. The popup says submission is for human review and is not publication.
- **Remaining:** richer typing for transcript/translation/review feedback fields, duplicate in-flight network UX, and browser verification of the full journey. Never render a local approximation as the authoritative frozen packet.
- Feedback view shows reviewer questions/reasons for the submitted version. Resubmit creates a revised packet; retain prior decisions and originals. Do not reset consent or reuse approval silently.
- Tests: missing/revoked consent, missing media, expired session, double submit, API failure, revision conflict and stale preview.

## AS-15 / AS-16 — internal reviewer website

### AS-15.a: queue and packet detail

**Implemented 2026-11-11:** authenticated reviewer detail shows submitted story title/description/claim/location, original media, English transcript or labeled translation draft, video scene observations, and an optional contributor-attached PDF. The assessment worker compares those allowed inputs and exact transcript/PDF/scene excerpts only; contributor research, briefs, source URLs, plans/reports and worker traces stay private and are absent from reviewer packets/model input. Assessment/provider/prompt/hash and media-job states are wired to durable jobs; empty results show queued/running/unavailable state instead of placeholder metadata. Findings and approval availability use the API-owned versioned review policy. Model interpretations are decision support, not independent fact-checking or an authenticity verdict.

The review queue has a custom status dialog, a collapsible submission rail, and submission selection restored from the URL. The first sidebar item is Dashboard with workload and publication summaries; decision history includes the published video catalogue. Review packet sections are collapsible. Worker-run trace detail is intentionally omitted from the reviewer dashboard.

**Remaining:** queue pagination, actual interactive keyframe review, and focused 360px/desktop browser evidence.

Separate deterministic blockers from attention findings and worker recommendations. Show guideline version and exact packet/revision. Evidence links are untrusted content; never render retrieved HTML as trusted application markup.

### AS-15.b: reasoned human decision

Approve/request changes/reject/escalate actions use server state, expectedVersion and packet hash. Disable invalid actions with specific reasons; still handle server denial/races. Show decision result/audit only after persistence succeeds.

### AS-16 frontend integration

Provide deliberate publication confirmation/preview, contributor withdrawal and correction/resubmission flows. Public map reflects the approved revision after publication. A withdrawn story cannot keep playing through a newly requested URL/segment.

Tests: role denial, queue filters, stale packet, server-side blocker despite enabled button, failed decision, duplicate action, publication/withdrawal and old-version history.

## Verification and handoff

Use the exact commands in tests/README.md and GITHUB_CI.md. Domain/render tests run without a browser; real API/storage cases belong to service integration tests. Add Playwright journey tests in AS-18 without confusing them with current HTTP smoke checks.

For each slice hand over: feature ID; changed files; contract/fixture mode; checks with results/skips; remaining integration boundaries; route and short browser reproduction steps. The user carries out ongoing visual testing. The later Codex discrepancy review follows PRODUCT_SENSE.md.

## Current persistence integration (2026-11-07)

The portal now opens an owner-scoped private device session and loads its profile/projects from the API. Profile saves, explicit Save draft, duplicate, planning suggestions and submission references persist server-side. Unsaved text stays on screen on save failure; stale drafts return a visible conflict. Submitted revisions are frozen and must be duplicated for further edits. Full provider sign-in/recovery and archive/merge-conflict UI remain targets.

Original file selection asks for upload/analysis consent, uploads through a five-minute same-origin API intent with progress/cancel, and shows server-verified media metadata only after successful completion. Original playback uses an owner-protected streaming URL and survives reload. The submission action requires verified uploaded media and explicit consent. The dashboard reads durable packets/decisions, passes the expected review version, and plays private media using a ten-minute HttpOnly review-media cookie obtained with the local reviewer key. Public publishing remains separate.

Portal import presents saved browser records and offers Import and clear Asante browser storage. The server stores a raw private MinIO backup plus typed DB records; the client verifies DB readback and backup hash before removing only captured unchanged Asante local/session storage keys. A download link provides the original archive. Failed or conflicting imports retain browser data. Future tour progress, low-data preference and playback position persist through the API rather than repopulating localStorage. This migration moves old text/preferences; the old preview never saved original file bytes.

## Current account UI (2026-11-07)

The contributor portal offers email/password sign-in, explicit contributor registration with storage consent, and sign-out. An existing device workspace can be linked only by explicit registration consent using its current capability and attribution. Account changes/sign-out clear private profile/project/media state; delayed saves cannot repopulate a different account's UI. Saved data is loaded from the server after each sign-in, so closing an incognito window no longer loses access once the user signs in again. Email changes/recovery are not implemented.

The portal sidebar links to the signed-in public contributor profile, and Overview separates owned published stories from private project drafts. Story details link to `/asante/profiles/{profileId}/`; the profile page lists only public stories with explicit-play players. Private emails/bios/drafts are never displayed on that page. The four existing fixture catalogue stories are explicitly linked to their test contributor accounts; their media-availability labels remain accurate.

The dashboard has account email/password sign-in and sign-out. The authenticated role routes contributors to the portal and reviewers to the review dashboard; opening the wrong workspace redirects based on the server role. Server role checks protect queue, decision and media requests. Old shared reviewer-key instructions are superseded. Account sessions are shared across same-origin tabs: use separate normal/incognito windows for simultaneous contributor/reviewer testing, or sign out before switching accounts. Focus refresh clears inappropriate cached data when another tab changes the account. Role changes do not move story ownership. Broader visual acceptance remains the user's review. The dashboard provides a labelled switch between the clean Localhost path and the configured direct port.

Evidence comparison and each media-worker draft section provide a Worker trail popup with the worker's safe input summary, provider/status, timestamped recorded checkpoints and saved output. The trail reports observable actions and outcomes rather than private model reasoning; contributor research, raw PDF text and prompts remain hidden. Older jobs without checkpoint history show only their persisted lifecycle timestamps and are labeled accordingly.
