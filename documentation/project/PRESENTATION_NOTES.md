# Asante presentation notes

Use this as a speaker cheat sheet. Prefer product language first; go deeper only if asked. Keep delivery details high-level — do not narrate internal stream formats or private infra names unless a judge explicitly asks how media is served.

Living implementation status remains in `documentation/ai/exec-plans/PLANS.md`.

## One-line pitch

Asante connects community audio and video stories to real places on a map, with contributor tools, AI assistance, and human review before publication.

## Demo path (suggested)

1. Open `/asante/` — map-first home, brand, discovery list, optional guide.
2. Toggle **Low data** in the top nav — explain still posters vs muted list previews.
3. Search / language filter → open a story → Play → transcript / translation when present.
4. Optional Locate — GPS is optional; stories stay available remotely.
5. Workspace (`/asante/portal/`) — sign in, draft, plan/research, upload, submit.
6. Review (`/asante/review/`) — reviewer decides; approve publishes to the catalogue.

Local accounts: create with `python scripts/asante/accounts.py` (passwords land in ignored `.env.asante-test-accounts`).

## Feature Q&A

### Map home

**What is the home experience?**  
A map-first listener surface: discovery list, pins, story drawer, optional onboarding guide. No separate marketing landing page before the map.

**Why GPS optional?**  
Location can add distances and focus the map, but discovery and playback must work from anywhere. Denial or unavailable geolocation never locks stories away.

**What does search / language filter do?**  
Client-side filtering of the published catalogue by text (title, place, contributor, language label) and original language code.

**What are the orange pins?**  
Published landmarks from the catalogue. Selecting a pin focuses that place’s stories in the list.

### Low data

**What is Low data?**  
A saved listener preference (`asante.lowData`, on by default) that reduces automatic media use.

**What changes when it is on?**  
- Story list keeps posters / placeholders — no muted autoplay previews on scroll or hover.  
- Full playback still waits for an explicit Play action.  
- The player avoids eager media preload.

**What changes when it is off?**  
Muted list previews may play for the most visible or hovered video card. Full story playback still starts only after Play.

**Is it a quality switch?**  
Not yet. It controls *when* media starts, not a separate quality ladder in the UI. Say “data-saving preference,” not “SD/HD.”

### Playback and language

**How does playback start?**  
Only after the listener chooses Play (or Play video for video stories). Catalogue cards do not download full media on render.

**Audio vs video?**  
Audio plays inline in the drawer. Video opens a focused playback surface after Play video.

**Transcript / translation?**  
When present, listeners can switch between original transcript and a reviewed translation. Missing translation stays “unavailable,” never a relabelled original.

**Demo story?**  
One clearly labelled synthetic audio demo exists for playback testing; it is not a verified heritage account.

### Contributor workspace (`/asante/portal/`)

**Who is it for?**  
Contributors with email/password accounts. Sessions are server-side and revocable.

**What can they do?**  
Manage profile attribution, create/edit story projects, save drafts, run planning/research assistance, upload media with consent, and submit a versioned packet for review.

**Does AI publish stories?**  
No. AI helps plan and process; humans keep authorship and publication decisions.

**Planning / research?**  
Workers return structured suggestions and sources through the Asante API. If a live model is configured and fails, the portal shows the failure instead of silently inventing a plan.

### Review desk (`/asante/review/`)

**Who can open it?**  
Reviewer-role accounts only. Contributor login is not enough.

**What happens on approve?**  
The approved packet can publish into the public catalogue so it appears on the map. An admin publication notice may be attempted when mail is configured.

**What stays human?**  
Consent, credit, evidence judgment, approve/reject, and any correction/withdrawal policy still in progress.

### Public contributor profiles

**What are `/asante/profiles/...`?**  
Public pages for a contributor’s published stories and attribution, linked from playback where available.

### Platform / architecture (if asked)

**Stack?**  
Next.js websites, FastAPI API, PostgreSQL/PostGIS catalogue, private object storage for media, MapLibre map, Docker Compose local stack behind an Nginx `/asante` path.

**Why PostGIS?**  
Landmarks and stories are geographic; nearby/distance queries belong in the database.

**AI workers?**  
Bounded Asante services for planning, research, transcription/translation/analysis jobs — with traces and human escalation, not unrestricted agents.

**Dashboard site?**  
`app/websites/dashboard` is the internal system surface; day-to-day review for this build is on `/asante/review/`.

### Honest limits (say these calmly)

- Some catalogue rows may still be illustrative until media is attached.  
- Provider SSO, email verification, and password recovery are prepared paths, not the primary local demo.  
- Withdrawal/correction and full hosted deployment are still open items in the plan.  
- Low data is a real preference wired to preview/preload behavior; multi-rendition “quality” switching is future work.

## Phrases to prefer / avoid

| Prefer | Avoid |
|---|---|
| Media loads after Play | Naming internal stream formats in the UI story |
| Saved low-data preference | “We detect Wi-Fi automatically” |
| Human review before publish | “The AI publishes stories” |
| GPS is optional | “You must share location to listen” |
| Reviewed translation when available | Pretending every story is fully translated |

## Quick URL checklist

- Listener map: `http://localhost/asante/`
- Contributor portal: `http://localhost/asante/portal/`
- Review desk: `http://localhost/asante/review/`
- API health: `http://localhost/asante/api/health`
