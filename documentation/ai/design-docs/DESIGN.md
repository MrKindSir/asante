# Asante design implementation contract

Revision: 2026-11-07. Apply with [FRONTEND.md](FRONTEND.md); feature order is in [PLANS.md](../exec-plans/PLANS.md). This is an implementable UI contract, not permission to redesign a screen during every feature task.

## Product hierarchy

1. Listener: immediately sees places and stories on a full map; can listen from anywhere.
2. Contributor: works in a separate project dashboard with visible ownership and review status.
3. Reviewer: compares an exact submission version with media, evidence and guideline findings.

Retain the place-led map entry and separate workspaces. Visual language is quiet cartography: cool stone grounds, deep teal action, clear hierarchy, no promotional hero. Avoid an inline contribution form on the map, a centred-only multi-page tour, or decorative worker activity presented as real.

## Look and feel

- Direction: professional and simple. The map is the primary surface; chrome stays light and secondary.
- Palette: cool green-stone paper, near-white surfaces, charcoal ink, teal primary (`--clay` token name retained for MapLibre), muted gold for spotlight only.
- Type: Figtree for body/controls, Syne for brand and story headings. Loaded through `next/font` as `--font-asante-sans` and `--font-asante-display`.
- Surfaces: floating map chrome uses translucent surfaces with a short blur; 6 px radius; restrained shadow; square-ish tags instead of pills.
- Motion: short hover/focus transitions on buttons and story rows; respect `prefers-reduced-motion`.
- Do not reintroduce cream paper, terracotta primary, Georgia/Arial stacks, or heavy card chrome for static content.

## Tokens and typography

| Token | Value | Meaning / intended use |
|---|---|---|
| `--brown` | `#3E4A45` | Cool secondary emphasis and quiet chrome text |
| `--clay` | `#0F6B63` | Primary action, focus ring and selected story/pin accent |
| `--sun` | `#C4A035` | Tour spotlight and sparse highlight only |
| `--ink` | `#121816` | Main text and workspace navigation |
| `--green` | `#2A6B4E` | Ready/published/pass states, accompanied by text |
| `--blue` | `#2A5F73` | Research, links, language and informational states |
| `--paper` | `#E6EBE8` | Page ground (soft stone, not cream) |
| `--surface` | `#F7FAF8` | Panel and overlay fill |
| `--muted` | `#5C6661` | Secondary copy |
| `--line` | `#C8D2CC` | Borders and separators |
| `--tint` | `#D4E2DC` | Soft selection and support fills |
| `--radius` | `6px` | Shared corner radius |

MapLibre paint reads computed tokens; no independent palette inside map code. AS-00 consolidates token ownership only after both Docker builds can consume the shared source. Do not create another palette file per component. Keep the `--clay` token name even though the value is teal, so map paint and existing class names stay stable.

Type scale: body 14–16 px, labels at least 12 px, secondary metadata at least 11 px, headings 24/32/40 px with responsive wrapping. Compact metadata is not a reason to make important state unreadable.

Use a 4 px spacing basis (4/8/12/16/24/32). Panels share radius, restrained shadows and one dominant action. Gold (`--sun`) is accent only with dark text nearby; never small text on pale gold. Verify actual text contrast; target 4.5:1 for normal text and 3:1 for large text and essential non-text boundaries.

## Layout contracts

### AS-04: map

- Map fills the available viewport with explicit width/height. The MapLibre container's library class must not collapse it or change it back to normal flow. Keep the resize observer.
- Desktop: floating header; left discovery panel about 340–380 px; right selected-story drawer about 320–380 px; map remains visible between them.
- Tablet: panels become collapsible before they obscure the entire map. Mobile: discovery list and story details use bounded sheets; an expanded sheet leaves usable map context or an explicit Map/List switch.
- Account for safe-area insets, browser address bars and short landscape screens. Test 360 px width, 768 px and 1440 px; add a short-height case, not only tall phone screenshots.
- Header controls must not overlap map attribution or navigation. Provider attribution remains visible; error banners and sheets cannot cover it.
- A selected story's location remains visible outside the covering panels. If several stories share a pin, expose the count/list rather than implying only one exists.
- Search, language and Show all are persistent discovery controls. Nearby, if added, is an explicit reversible filter.

### AS-05: anchored tour

- Welcome is centred. Search/location/story/contribution steps move to their real elements.
- A spotlight outlines the target; the target stays clickable. The dimmer covers surrounding areas only.
- Position is measured from the live target rect. Prefer free space beside it, flip when needed, clamp to viewport and recalculate after scroll/resize/target replacement.
- A tooltip must not cover its own target. On constrained screens, shorten explanatory copy or use an anchored sheet with a visible connection; do not silently return every step to the centre.
- Use concise action-based copy: “Get started here”, “Use my location”, “Choose a story”. Show progress, Back, Skip/close and Replay.
- Welcome traps focus while modal; anchored steps allow focus to their target. Escape dismisses; focus returns to a useful control. Missing/empty data must not leave the guide pointing to nothing.

### AS-07–14: contributor workspace

- Persistent navigation: Overview, Projects, Research, Editor, Upload, Submission/Feedback, Profile. Use selected-project context so users know which story is being changed.
- Overview counters come from actual owner data. Empty states offer one relevant next action.
- Forms use visible labels, required hints and inline field errors. Save/processing/submission state appears close to the relevant action.
- Story text, Asante AI suggestions and reviewer feedback are visually distinct and attributed. Acceptance of a suggestion is an explicit contributor action.
- Upload shows actual states: local preview, uploading, verifying, processing, ready. Do not use a green ready state for a file selected only in the browser.
- Submission preview places original language, credit and consent beside Send for review. Publishing is never implied by successful submission.

### AS-15/16: reviewer workspace

- Queue plus selected packet on desktop; queue/detail navigation on mobile. Preserve filters and return position.
- Display revision, packet/guideline version and freshness before decisions.
- Keep original media/transcript close to claims/source evidence. Use expandable sections for secondary metadata, not to hide blockers.
- Separate Blocked, Attention and Pass. Use icon/text and color together. A URL or an AI recommendation must not appear as a “verified” badge.
- Decision controls show why an action is disabled. Reason entry is required. No success toast or audit entry before the server confirms persistence.
- Publication preview shows the exact public projection: title, place precision, credit, language, original/translated media and evidence status.

## Component states implementers must cover

| Component | Required states |
|---|---|
| Catalogue/list | loading, populated, empty catalogue, no matches, failed refresh, stale last good list |
| Map | initializing, visible, style/tile error, WebGL unavailable, retry, resized, selected location |
| Tour | welcome, anchored step, missing target, paused/resumed, completed, skipped, replayed |
| Player | unavailable, ready before Play, loading, playing, paused, ended, seeking, error/retry |
| Account/session | signed out, authenticating, authenticated, expired, role denied, recovery pending/failure |
| Editor | clean, dirty, saving, saved, offline/failed, version conflict |
| Upload | selected/local preview, uploading/progress, cancelled, verifying, processing, ready, failed/expired |
| Asante worker | preview fixture, queued, running, succeeded, uncertain, failed, cancelled, retrying |
| Submission/review | draft preview, submitting, pending review, changes requested, escalated, rejected, approved |
| Publication | unpublished, publishing, published, withdrawal pending/withdrawn, correction in review |

Use domain status plus a short explanation. Loading/error/unavailable cannot all be represented by a disabled button with no reason.

## Accessibility and interaction

- Semantic buttons/links, visible labels and meaningful headings; no click-only div controls.
- Aim for 44×44 px touch targets even when an icon is smaller. Focus indicators remain visible against every surface.
- Every essential map action has a list/form alternative. Keyboard users can select a story and open playback.
- Drawers have an accessible name and close action; modal focus behavior matches whether the rest of the page is intentionally unavailable.
- Announce permission, upload, save and review state changes without flooding a live region on every progress tick.
- Captions/timed text and transcripts when available; never autoplay. Original versus translated content is stated in text.
- Respect reduced motion for fly-to transitions, focus movement and tooltip repositioning. Do not rely on animation to explain state.

## Data-use and content honesty

No media source is attached until explicit playback. Posters/text can be prepared separately. A low-data toggle must change delivery or explain which behavior is currently available. Unknown network type cannot be described as known Wi-Fi.

Keep synthetic demo, illustrative story, worker preview, translation draft and published human-reviewed content visibly distinct. Do not add fabricated sources, charts, confidence scores, contributor activity or review counts to fill a screen.

## Design implementation and review gates

1. AS-00: inventory existing tokens/components; normalize formatting as a bounded refactor without changing product behavior.
2. AS-04/05/06: prove map/list/player geometry and the anchored tour at the three widths plus a short screen; preserve remote listening.
3. AS-07/09/12/14: prove contributor task completion with real states, failed network requests and long content.
4. AS-15/16: prove readable evidence/decision flow, blocking reasons and exact publication preview.
5. AS-18: compare the implemented journeys against this contract, not against a generated screenshot alone.

For a visual finding record route, viewport, active feature/state, expected behavior, actual behavior, screenshot and reproduction steps. User browser testing is the current verification owner; Codex's later discrepancy review adds independent browser evidence when requested.
