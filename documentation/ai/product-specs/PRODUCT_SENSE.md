# Asante acceptance and discrepancy review

Use after individual slices and for AS-18, the full website review. [PLANS.md](../exec-plans/PLANS.md) owns feature status; [FRONTEND.md](../design-docs/FRONTEND.md), [BACKEND.md](../design-docs/BACKEND.md), [DESIGN.md](../design-docs/DESIGN.md) and [ASANTE_AI_RUNTIME.md](../design-docs/ASANTE_AI_RUNTIME.md) own expected behavior.

## What counts as evidence

| Evidence | Establishes | Does not establish |
|---|---|---|
| Domain/unit/render tests | Rules, transformations, schemas and initial markup | Actual map rendering, clicking, scrolling or audio decoding |
| HTTP smoke tests | Proxy/route and basic query/media responses | Working tour geometry or a completed user journey |
| Real PostgreSQL/MinIO integration tests | Persistence, ownership queries and real object lifecycle | Correct visual affordances |
| Provider fake / recorded fixture | Deterministic orchestration and failure handling | Live model quality or language support |
| Browser traces/screenshots/interactions | Layout, controls, target placement and journey behavior | Complete backend authorization coverage |
| Fluent human language review | Meaning and cultural/linguistic suitability for reviewed cases | General correctness across all languages/content |

A completed production build is compilation evidence. A button label or mocked success is not feature evidence. Report unavailable tests or dependencies as unverified rather than passing.

## AS-18.a — regression harness and user browser checks

Add real Playwright journey tests under tests/e2e when configured; retain and correctly name the current HTTP smoke tests. Use deterministic database/media fixtures and fake Asante AI responses by default. Test accounts have distinct contributor and reviewer identities; fixture authentication cannot be enabled in normal runtime.

Use at least 360 px, 768 px, 1440 px and a short landscape viewport. Add reduced-motion and keyboard-only cases. Live external model calls are a separate opt-in evaluation.

| Case ID | Required observation | Related feature |
|---|---|---|
| AC-01 | First visit shows a real full map; no marketing page first; tiles failing leaves a usable list | AS-04 |
| AC-02 | Welcome centres; later guide moves to search/location/story/contributor with real spotlight targets | AS-05 |
| AC-03 | Back/Skip/Escape/resume/replay work; target survives async loading, resize and scroll; keyboard can reach it | AS-05 |
| AC-04 | No GPS, denied GPS and distant GPS all permit discovering South African story locations | AS-03/04 |
| AC-05 | A selected pin/list item opens the correct story; multiple stories at one landmark remain reachable | AS-04 |
| AC-06 | Posters load without fetching original recordings; video opens in a popup; available translated caption choices stay synced to video time; manual Play or explicit position auto-play within 150 m starts playback | AS-06/10/13 |
| AC-07 | Real sign-in/profile; two contributors cannot access each other's projects, assets or runs | AS-02/07 |
| AC-08 | Create/save/reload/duplicate project works against the server; conflict and failed save preserve work | AS-07 |
| AC-09 | Original narrative/media/credit are retained; contributor explicitly accepts/rejects suggestions and consent scopes | AS-08/12 |
| AC-10 | Actual MinIO upload completes and verifies; expired/spoofed/cancelled/failed media never appears ready | AS-09/10 |
| AC-11 | Worker outputs show inputs, sources, uncertainty and run state; stale/cancelled/failed runs do not fabricate success | AS-11/12/13 |
| AC-12 | Packet preview matches the frozen server revision and submitted attribution/consent/media/claims | AS-14 |
| AC-13 | Reviewer opens that same packet with original media, evidence, guideline version and blocking reasons | AS-15 |
| AC-14 | Unauthorized/stale/duplicate decisions fail correctly; review reason and identity persist | AS-02/15 |
| AC-15 | Approved exact revision becomes publicly discoverable/playable only after deliberate publication | AS-16 |
| AC-16 | Withdrawal removes catalogue and new media delivery; corrections keep old evidence and require re-review | AS-16 |
| AC-17 | Fresh setup follows the bootstrap prompt; migrations/seeds/CI run without hand repairs or committed secrets | AS-17 |
| AC-18 | Mobile/desktop/keyboard states use Asante tokens, readable controls, visible attribution and accurate status copy; the discovery panel shows a thumbnail for every story | DESIGN; AS-04–16 |

The 2026-11-10 AS-14/15 slice now freezes the exact saved project revision and presents the same plan/report/source/media/consent/worker references in contributor preview and reviewer packet. It adds deterministic readiness findings, bounded submitted-source comparison, explicit provider failure states and a shared server-owned approval policy. Unit and deterministic fake-provider results do not establish live provider accuracy, cultural acceptance or authenticity accuracy. The reviewer browser journey, PostgreSQL/MinIO restart/lease matrix, live-provider evaluation, provider SSO/recovery, full AS-13 language/video evaluation and withdrawal/correction remain open. Fixture planner output and candidate research sources must not be treated as AC-11 live completion without evidence of run status, source retrieval state and uncertainty.

The 2026-11-10 discovery update reuses the existing poster database field, adds published poster streaming and upload-generated video/audio thumbnails, and makes proximity auto-play an explicit foreground-location opt-in. The updated browser acceptance remains pending; audible playback may still require a manual Play gesture when browser policy blocks auto-play.

## End-to-end demonstration paths

1. **Remote listener:** fresh browser → moving guide → deny GPS → find a distant landmark → inspect location/credit → play and seek a published asset → inspect original transcript and available translation.
2. **Contributor:** sign in as A → create a story project → plan/research → accept/edit/reject suggestions → upload original media → review consent/credit and packet → submit → reload and see status.
3. **Reviewer and publication:** sign in as reviewer → open A's exact packet → compare claims/sources/media → request changes → A creates a revised submission → reviewer approves → deliberately publish → remote listener sees that version.
4. **Ownership and withdrawal:** contributor B is denied A's private resources → A withdraws publication → public catalogue and new playback requests fail → correction starts a new review without destroying prior attribution.

A real vertical slice needs one consented, playable story, one actual persisted submission and one human decision path. Label synthetic fixtures and unavailable translations honestly.

## AS-18.b — independent Codex review

The user currently performs ongoing UI web tests. At the user's later request, Codex reviews the implemented website against the blueprint and accumulated test evidence. Start with a discrepancy report; implementation fixes are separate authorized slices unless the request includes them.

Review prompt:

```text
Review the current Asante implementation for AS-18.
Read AGENTS.md, documentation/ai/exec-plans/PLANS.md and the relevant acceptance/specification sections.
Compare the current code and running app against AC-01 through AC-18.
Inspect APIs, real storage/ownership boundaries, failure paths and actual browser behavior.
Distinguish implemented, prototype, failed and unverified features.
Use deterministic accounts/media and configured test services. Do not spend on external
AI providers, deploy, alter credentials, publish real stories or delete user data
unless this review request explicitly authorizes it.
Record browser evidence for map dimensions, moving tour, location-independent discovery,
media controls, mobile layouts and contributor/reviewer task completion.
Check persisted records and authorization independently of UI messages.
Report reproducible findings with severity, feature/AC ID, route/viewport,
expected versus actual behavior, file/line references and evidence paths.
Identify missing tests and the smallest repair slice; do not redesign unrelated features.
Do not mark absent browser/provider/storage evidence as passed.
```

## Finding and repair format

```text
Finding: [short title]
Severity: P0 / P1 / P2 / P3
Feature / acceptance case:
Environment, role, route, viewport:
Reproduction steps:
Expected:
Actual:
Evidence: file:line, test command/output, screenshot/trace when applicable
Impact and smallest repair slice:
Retest cases:
```

P0: unauthorized publication/data exposure or destructive loss. P1: core journey blocked, wrong ownership/version or inaccessible essential control. P2: materially incorrect behavior/layout/state with a workaround. P3: minor clarity/consistency issue. Use impact and reproducibility, not visual preference alone.

For an unverified area, record the missing service/provider/browser evidence and the next check needed. For each repair, link its test and rerun the affected journey; close a finding only with observed evidence.

## Implementation handoff

Provide the selected feature/slice, changed paths, exact commands/results/skips, fixture-versus-live boundaries, database/API compatibility changes, remaining gaps and browser reproduction steps. Include unresolved design choices instead of silently making them. This lets the next reviewer inspect a bounded change without replaying the whole conversation.

## Local account acceptance handoff (2026-11-07)

Use the generated development credentials described in tests/README.md; never copy them into committed documents. Verify contributor sign-in and sign-out, password failure, restoration after closing/reopening an incognito session and re-signing in, distinct account-owned drafts/media, and public story→profile links without private data. Verify a contributor is denied review access, a reviewer can open exact submitted packets and private media, and recorded decisions retain the reviewer account identity. Public profiles list only published catalogue stories, not private projects or submissions. Use separate browser sessions for simultaneous contributor/reviewer roles. Email verification, forgotten-password recovery, provider SSO, revised-submission and deliberate public publication acceptance remain pending. Automated evidence is in PLANS.md; visual/use-case acceptance remains with the user.
