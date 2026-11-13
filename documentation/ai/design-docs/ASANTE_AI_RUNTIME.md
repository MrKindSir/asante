# Asante AI worker implementation specification

Owns AS-11/12/13 and worker findings used by AS-14. See [PLANS.md](../exec-plans/PLANS.md) for dependencies and [BACKEND.md](BACKEND.md) for persistence/authorization.

## Runtime and current baseline

Codex is the development assistant for this repository. Asante uses server-side provider adapters at runtime; it does not call the local Codex application or read Codex memory, ExecRules or configuration.

Current integrated baseline (2026-11-11):

- Planner and researcher run from the contributor story chat through the Asante API (`POST /v1/workspace/projects/{id}/workers`), after the saved research questionnaire. The bounded activity view below records their actual handoffs and execution steps. The portal can open a live research-activity modal while a worker runs, including after a browser connection interrupt; completion is announced in chat.
- **Localhost AI:** leave `ASANTE_AI_BACKEND` empty. Planner/researcher/vision/text prefer host Ollama (`ASANTE_OLLAMA_*`). Transcription uses local `faster-whisper`. Optional cloud `ASANTE_AI_*` (Gemini or OpenAI-compatible) remains a fallback only when local Ollama is not configured for that call.
- **Live AI:** set `ASANTE_AI_BACKEND=modal`. The API never talks to host Ollama for that deployment. It calls the Modal Asante app through `asante_api.ai.live_modal` using `ASANTE_MODAL_BASE_URL` and `ASANTE_MODAL_SHARED_SECRET`. Modal runs Ollama (chat/vision) and Whisper (transcription) for Asante. Do not point live at localhost Ollama and do not share HubTweak Modal apps or secrets with Asante.
- When the configured provider is fake/off or unavailable, the planner uses the deterministic fixture. Empty research fails loud; it does not invent sources. Missing speech/provider results stay `unavailable`; workers never fabricate transcripts or captions.
- Research collectors cover web search, news RSS, pasted HTTPS URLs and social/video discovery (including the bundled YouTube seed catalogue under `asante_api/ai/data/`).
- A deterministic verifier produces `asante.verification.v1` findings for shared portal/dashboard checks. Workers cannot approve or publish.
- Provider keys and Modal secrets stay server-side / Modal secrets. Model IDs, caption caps and spend ceilings belong in Asante server configuration, not UI constants.
- Compose runs `api` and a separate `job-worker` process from the same API image for durable media/assessment jobs. Autonomous multi-agent teams and a public `/asante/talk/` Ollama gateway remain out of scope.

## Live Modal backend (operator contract)

Use this section when implementing or debugging live AI, transcription, translation or media jobs.

### Split of responsibility

| Environment | Text / vision | Transcription | Caption caps |
|---|---|---|---|
| Localhost (`ASANTE_AI_BACKEND` empty) | Host Ollama via `ASANTE_OLLAMA_BASE_URL` | Local `faster-whisper` | `ASANTE_CAPTION_SECONDS` default 180; `ASANTE_TRANSLATE_MAX_CUES` default 100 |
| Live (`ASANTE_AI_BACKEND=modal`) | Modal Ollama via `live_modal.py` | Modal Whisper via `live_modal.transcribe_wav_via_modal` | `ASANTE_LIVE_CAPTION_SECONDS` default 45; `ASANTE_LIVE_TRANSLATE_MAX_CUES` default 12; batch/deadline via `ASANTE_LIVE_TRANSLATE_*` |

Caps are implemented once in `asante_api/ai/caption_limits.py`. Every media job stores a `captionLimits` snapshot on input/result. Raise spend only by changing live env values and recreating `api` / `job-worker`; do not hard-code larger windows in UI or workers.

### Modal app

- Source: `app/services/ai/modal/asante_ollama_app.py`
- Deploy helper: `scripts/asante/deploy_modal_ollama.sh`
- Deploy: create Modal secret `asante-modal-auth` with `ASANTE_MODAL_SHARED_SECRET`, then `python -m modal deploy app/services/ai/modal/asante_ollama_app.py`
- Set live Compose/env `ASANTE_MODAL_BASE_URL` to the printed ASGI URL and the same shared secret
- Auth: bearer shared secret on every Modal route; unauthorized calls fail closed
- Cold start can take minutes; live Modal HTTP timeouts must stay long enough for GPU warm-up. Do not “fix” cold starts by falling through to Gemini or host Ollama on live
- Live Whisper uses `ASANTE_MODAL_WHISPER_MODEL` (a Modal/Hugging Face model name such as `tiny`), separate from localhost `ASANTE_WHISPER_MODEL` paths. Transcription requests use `ASANTE_MODAL_TRANSCRIBE_TIMEOUT` (default 240 seconds) and retain safe configuration, authentication, timeout, provider and no-speech reasons in the draft result.

### Durable media jobs

Compose service `job-worker` claims PostgreSQL `processing_jobs` with leases (`FOR UPDATE SKIP LOCKED`).

Job types:

| Type | When enqueued | Notes |
|---|---|---|
| `transcribe` | Verified draft media upload, and again on submit if missing | First `caption_seconds()` of speech only; clips cues to `translate_max_cues()` |
| `translate` | Same as transcribe | Waits until sibling `transcribe` is not queued/running; preserves cue times; bounded batch/deadline |
| `analyze` | Video only | Bounded keyframes; scene observations are not heritage proof |
| `assessment` | Submit only | Requires a frozen submission packet; never runs on draft-only jobs |

Draft vs submission:

- Verified media upload (`PUT /v1/uploads/{id}/content` for `purpose=media`) calls `enqueue_project_media_jobs`. Those jobs have `submission_id = NULL` and appear on the draft chat as `mediaJobs` / `transcriptDraft` / `translations`.
- Submit promotes matching draft jobs for the same `upload_id` onto the submission (avoids repeating Modal spend), then ensures assessment + any missing media jobs exist.
- Replacing draft media cancels superseded queued/running draft jobs and enqueues a fresh capped set.
- Backfill existing drafts that already have verified media and no jobs: `scripts/asante/backfill_draft_media_jobs.py` inside the API container.

### Rules for future job / Modal prompts

1. Keep localhost and live backends separate. Never make live depend on host Ollama or change localhost to require Modal.
2. Keep HubTweak MinIO, Modal apps and secrets out of Asante changes.
3. Prefer extending `caption_limits.py`, `live_modal.py` and `jobs.py` over adding a second vector DB, Redis or microservices.
4. Empty/unavailable speech or provider failure must remain explicit; do not invent transcript text, captions or sources.
5. Do not auto-publish drafts. Human review gates remain for publication, consent and authorship.
6. After live code changes that touch AI/jobs, rebuild/recreate `api` and `job-worker`, confirm `caption_limits_snapshot()` on both, and check new job payloads include the live caps.

### Recorded research activity (2026-11-10 authorized extension)

The chat activity view now reads owner-scoped planner/researcher runs. Each activity event contains an ID, UTC timestamp, actor, kind, concise factual message and bounded details. Events are persisted during execution into the existing result JSONB (at most 80 events, 12 detail strings of 2,000 characters each per event), then retained with final outputs on success, failure or stale cancellation. Reads expose the saved input revision/brief and actual planner questions handed to the researcher. The progress sink is request-scoped; collectors emit only actions/outcomes they actually performed. It does not expose private model reasoning, invent peer discussion, add worker permissions or start new jobs. Existing runs without events retain honest historical-status labels. Partial autosaved briefs are allowed, but worker start still requires a complete question/brief.

## AS-11 — durable runs and execution harness

### AS-11.a: schemas, access and fake adapter

Persist an immutable input snapshot, revision/input hash and run record before execution. Expose owner/reviewer-scoped run status. Establish deterministic provider fakes with success, partial/uncertain output, invalid schema, timeout, quota and cancelled cases.

Current implementation persists `worker_runs` for planner/researcher with runId/traceId, input/result payloads, provider model and safe errors. Full Pydantic/TypeScript envelope parity and cancel endpoints remain open work.

Target request:

```text
projectId, revisionId, workerType, inputReferences[],
requestedLanguages[], options, expectedVersion
```

The authenticated actor and authorized input refs are resolved server-side. A client cannot set the run owner, provider model, spending ceiling, arbitrary tool permissions or publication action.

Target result envelope (camelCase JSON):

```text
runId, traceId, projectId, revisionId, workerType,
schemaVersion, promptVersion, status, inputHash, inputReferences[],
findings[], suggestions[], evidenceReferences[], uncertainties[],
recommendedNextAction, requiresHumanReview,
startedAt, finishedAt, providerModel, toolVersions,
usage, safeError
```

Use structured findings: check/type, severity, text, claim/source/media references and rationale. Numeric confidence is nullable, accompanied by its definition/calibration method; do not invent precise confidence for uncalibrated judgments.

Freeze these nested contracts with the AS-11.a Pydantic/TypeScript schemas: finding has findingId, kind, severity (info/attention/blocking), message, references[] and rationale; suggestion has suggestionId, kind, proposedContent, sourceSpanRefs[], status (pending/accepted/edited/rejected) and contributorDecisionRef; uncertainty has affectedReference, explanation and suggestedHumanCheck. Worker severity alone is not a publication decision; AS-14's versioned guideline owns pass/attention/blocked outcomes.

### AS-11.b: bounded jobs, retries and visibility

Target: one Asante worker process sharing the API code/image, with PostgreSQL jobs/leases and `FOR UPDATE SKIP LOCKED` acquisition. Persist a job and its triggering domain event in the same transaction. Do not rely on in-process background tasks for work that must survive restart.

Current Research-room planner/researcher runs execute inside the API request path and record `worker_runs`. Compose starts a `job-worker` process from the API image for durable media and assessment jobs: draft upload transcription/translation(/analyze), submission assessment, and any missing media jobs at submit time. Results remain separate from the frozen packet and are also projected onto draft workspace projects for the contributor chat. Workers append a bounded `workerTrail` of timestamped lifecycle, progress, output, and retry events to the job result for authenticated reviewer visibility. Trail entries contain safe process summaries, not hidden model reasoning, raw prompts, contributor research or raw submitted documents. Broad lease/retry/cancel harness remains AS-11.b work.

- States: queued/running/succeeded/failed/cancelled; record attempt history and lease expiry.
- Deduplicate by actor/project/revision, input hash, worker type and relevant schema/prompt version. Explicit “run again” records intent; accidental repeated clicks must not duplicate charges.
- Enforce cancellation and lease ownership before committing output. A stale run cannot overwrite a newer revision.
- Retry only transient failures with bounded backoff; no automatic retry of invalid consent, unauthorized inputs or permanent schema failures.
- Proposed initial limits: one active run per project/worker type, two retries after the first attempt, per-tool timeouts, bounded output size and a configured per-project/day spend ceiling. Confirm provider-specific request limits separately.
- Usage records actual returned usage/cost estimate basis. If usage cannot be established after a timeout, record unknown and avoid blind expensive retries.
- Log IDs, state, duration and safe errors; keep private text/media in authorized storage, not logs.

Done when: crash/restart recovery, expired lease, duplicate enqueue, partial provider failure, cancellation, stale result rejection, budget exhaustion and owner isolation all have tests.

## Worker permissions and contracts

| Worker | Inputs | Structured output | Allowed tools / failure behavior |
|---|---|---|---|
| Asante planner | Contributor brief, audience, location and approved languages | Story questions, outline, production checklist, missing inputs | Text model only initially; no publication or unbounded web access |
| Asante researcher | Contributor-approved questions/claims, approved source policy | Source records, retrieval times, excerpts/hashes, claim links and unresolved conflicts | Bounded search/fetch adapter; failed retrieval remains unavailable or fails loud when empty |
| Asante verifier | Frozen packet, project plan/research/media readiness, prior worker runs | `asante.verification.v1` findings with blocking/attention/info severities | Deterministic service; no model call; cannot approve or publish |
| Asante structure worker | Contributor-owned narrative revision | Suggested ordering/transitions with referenced spans | No silent rewrite; accept/edit/reject creates a contributor decision |
| Asante language worker | Verified original media/transcript, requested language | Timed transcript, translation draft, uncertain segments/terms | Scoped media read and language API; no overwrite of originals |
| Asante provenance recorder | Contributor decisions, source/media/revision refs | Append-only contribution/version links | Deterministic service; no model call needed |
| Asante submission checker | Frozen packet and guideline version | Deterministic blockers plus separately identified AI findings | Read-only packet; cannot approve, publish or change consent |

Use direct provider calls for bounded single operations. Add an agent SDK only for a demonstrated multi-step/tool handoff need, behind these same schemas and permission boundaries. A network of autonomous agents is not required for the Research room baseline.

## AS-12 — planning and research

### AS-12.a: planner and contributor decisions

Accept a validated brief for a specific project; generate a structured plan with questions, outline, recording tasks, attribution/consent checklist and unknowns. Store it as a suggestion separate from the narrative. Accept/edit/reject belongs to the contributor and is versioned. Rejected suggestions remain in the audit trail without changing the story.

Portal entry: Research room **Prepare a story plan**.

Tests: culturally specific names/terms preserved, required fields, schema validation, failed/fake provider fixture path, stale revision, rejected plan not applied and deterministic replay fixture.

### AS-12.b: research and evidence comparison

Require approved research questions/claims where supplied and a bounded source policy. Proposed initial bounds: about twelve candidate sources per run; at most a small concurrent fetch set; explicit request/body/time limits. Implement URL validation and redirects before enabling real fetches: HTTPS, public destinations only, no localhost/private/cloud-metadata addresses, re-check DNS/redirect destinations and limit redirects. Treat retrieved instructions as untrusted content.

Source record: title, URL, publisher/host, retrievedAt when known, safe excerpt, content hash, retrieval/collector status, optional platform for social/video, and applicable usage/licence notes. Do not fabricate missing dates or turn a search snippet into a full-source reading.

Claims distinguish sourced factual assertions, personal memory, oral history, opinion and unverified material. Link supporting/contradicting/contextual sources with a rationale when that comparison exists. Conflicting sources and absent corroboration remain explicit for human interpretation.

Portal entry: Research room **Find evidence sources**, guided by the evidence notebook claim/URL fields.

Tests: conflicting/absent sources, unsafe redirected URL, prompt injection in source text, invalid source link, empty-result failure, seed social catalogue fallback and no external write permissions.

## AS-13 — language and video

Audio/video transcription, timed translation and video analysis run as durable `processing_jobs`. They start when draft media is verified, not only after submit. Public catalogue captions still require human-approved publication values; worker drafts are never auto-published.

### AS-13.a: transcription

After AS-09/10 verification, read a scoped original/normalized audio asset. Preserve original media and detected/declared language separately. Store timed segments, uncertain names/terms and provider metadata. Permit a contributor-corrected transcript as a new version with links to the original draft.

Current path extracts mono 16 kHz speech, clips to `caption_seconds()`, then runs Whisper (local on localhost; Modal on live). Results store language, backend, text, timed segments and `coveredSeconds` as a private draft on the job (and on the draft project projection). Missing Whisper or speech yields an explicit unavailable draft; contributor narrative and original media remain unchanged. General long-form chunk reconciliation remains unfinished.

### AS-13.b: translation

Translate timed transcript cues into approved languages (`en` / `zu` / `st`, excluding the source). Preserve cue start/end times. Cap cues with `translate_max_cues()`, batch with `translate_batch_size()`, and stop at `translate_deadline_seconds()`. Live uses Modal chat; localhost prefers host Ollama. Partial/unavailable results stay explicit. Changes to the source invalidate derivative readiness.

The listener sees original versus translation and reviewed/draft/unavailable state only after human publication. Do not expose an unreviewed private derivative simply because a listener requested it. Never replace the original recording or credit.

### AS-13.c: video analysis

Extract a mono 16 kHz speech WAV and a bounded set of timestamped keyframes with AS-10. The current implementation caps visual analysis at four frames and stores their timestamps with a reviewer-facing draft. ASR follows the transcription backend above; vision prefers Modal Ollama on live and host Ollama on localhost. Missing providers or empty results remain explicitly unavailable rather than fixture-success claims.

Visual observations are model interpretations, not historical verification or identity attribution. Media/worker failures surface separately from missing evidence.

## Evaluations and live-integration gate

Keep evaluation fixtures under existing test categories; generated run evidence belongs in logs. Do not create another root experiment framework before it is needed.

| Capability | Required cases / measurements |
|---|---|
| Planning | Output schema, preservation of contributor intent, actionable tasks, missing-input disclosure |
| Research | Real source availability, URL validity, claim-link correctness, contradictory evidence, unsafe fetch rejection, empty-result failure |
| Transcription | Clean/noisy speech, accents, code-switching, names/dates, silence; compare to consented reference transcripts |
| Translation | Meaning, attribution, names/idioms, uncertainty; fluent human assessment in each promised language |
| Video | Sampling coverage/timestamps, incorrect inference, bounded bytes/frames/cost |
| Harness | Retry amplification, duplicate runs, unknown usage, latency, cancellation and budget cap |

For each approved language, define a fixture set, reference annotations, reviewer and acceptance threshold before claiming support. Automated similarity/word-error metrics can inform review but cannot establish cultural or semantic correctness alone.

Default CI uses fakes and fixtures without external AI spend. Live evaluation is a separate opt-in command with bounded inputs, explicit consent, configured ceiling and recorded model/config versions. Handoff must say whether evidence came from a fake, a live provider or human language review.

## AS-14 — submission assessment worker contract (implemented, bounded)

| Worker mode | Input and permission boundary | Output and explicit failure | Human escalation |
|---|---|---|---|
| Deterministic provenance | Frozen packet allowlist: revision, consent, attribution, media/checksum refs, English transcript availability and supporting PDF extraction state. Never contributor research, research briefs, plans, reports, source URLs or worker traces. | `asante.assessment.v2` readiness checks and an input hash over only the allowed reviewer evidence. Checksums are integrity references, never authenticity proof. | Reviewer resolves technical/consent blockers or escalates missing provenance. |
| Submission evidence comparison | Bounded story title, description, claim, submitted location, original contributor narrative, completed English transcript (or explicitly labeled English translation draft), optional extracted text from the first ten PDF pages, and bounded video scene observations. No contributor research or web/network collection. Provider receives untrusted content and cannot write projects, decisions, publication or media. | Claim states `supported`, `contradicted`, `insufficient_evidence`, or `not_assessed`; exact quotes must match supplied transcript/PDF/scene evidence IDs. “Supported” means consistent with this submission only, not independently verified. Timeout, provider unavailable, missing text and malformed output remain distinct. | Assessment waits until transcription, translation and scene-analysis jobs are terminal. Reviewers handle uncertainty; no worker decides authenticity or approval. |

One unique PostgreSQL assessment job is enqueued in the submission transaction. A lease must be present and unexpired before progress/result writes. A schema/prompt-version migration requeues assessment jobs for undecided packets so their results are rebuilt from the allowlisted input. Derived results stay in job records, preserving packet bytes and contributor authorship. Keyword heritage checks are advisory attention only. This slice does not establish provider accuracy, authenticity assessment, plagiarism detection, deepfake detection or cultural acceptance.
