# Asante AI worker implementation specification

Owns AS-11/12/13 and worker findings used by AS-14. See [PLANS.md](../exec-plans/PLANS.md) for dependencies and [BACKEND.md](BACKEND.md) for persistence/authorization.

## Runtime and current baseline

Codex is the development assistant for this repository. Asante uses server-side provider adapters at runtime; it does not call the local Codex application or read Codex memory, ExecRules or configuration.

Current integrated baseline (2026-11-09):

- Planner and researcher run from the contributor story chat through the Asante API (`POST /v1/workspace/projects/{id}/workers`), after the saved research questionnaire. The bounded activity view below records their actual handoffs and execution steps.
- Live providers are Gemini or another OpenAI-compatible endpoint via `ASANTE_AI_*`. When the provider is fake/off or has no API key, the planner uses the deterministic fixture. Empty research fails loud; it does not invent sources.
- Research collectors cover web search, news RSS, pasted HTTPS URLs and social/video discovery (including the bundled YouTube seed catalogue under `asante_api/ai/data/`).
- A deterministic verifier produces `asante.verification.v1` findings for shared portal/dashboard checks. Workers cannot approve or publish.
- Provider keys stay server-side. Model IDs, purpose-specific limits and spend ceilings belong in Asante server configuration, not UI constants.
- The contributor chat, existing field-report/export/share flow, and bounded research-activity view are authorized additions. Autonomous multi-agent teams and a public `/asante/talk/` Ollama gateway remain out of scope. The separately authorized AS-13 video slice uses the submission job worker and reviewer dashboard; it does not change the Research-room planner/researcher path.

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

Current Research-room planner/researcher runs execute inside the API request path and record `worker_runs`. Compose starts a `job-worker` process from the API image for durable submission jobs: bounded submission assessment, audio/video transcription and video analysis. Results remain separate from the frozen packet. Broad lease/retry/cancel harness remains AS-11.b work.

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

Video upload, transcription and analysis are implemented as an AS-13 submission-job slice. Translation remains a specified target and is not claimed as live.

### AS-13.a: transcription

After AS-09/10 verification, read a scoped original/normalized audio asset. Preserve original media and detected/declared language separately. Store timed segments, speaker labels only when supported, uncertain names/terms and provider metadata. Permit a contributor-corrected transcript as a new version with links to the original draft.

The current video path uses local `faster-whisper` on an extracted mono 16 kHz WAV and stores language, backend, text and timed segments as a private packet draft. Missing Whisper or speech yields an explicit unavailable draft; contributor narrative and original media remain unchanged. General long-form chunk reconciliation remains unfinished.

### AS-13.b: translation

Translate an exact source transcript revision into an approved language. Cache by source hash, target language and provider/prompt version. Return text/timed-caption draft plus ambiguous idioms and untranslated names. Changes to the source invalidate derivative readiness.

The listener sees original versus translation and reviewed/draft/unavailable state. Do not expose an unreviewed private derivative simply because a listener requested it. Never replace the original recording or credit.

### AS-13.c: video analysis

Extract a mono 16 kHz speech WAV and a bounded set of timestamped keyframes with AS-10. The current implementation caps visual analysis at four frames and stores their timestamps with a reviewer-facing draft. ASR uses local faster-whisper; Ollama is preferred for configured visual/text analysis, with cloud fallback only when local Ollama is not configured. Missing providers or empty results remain explicitly unavailable rather than fixture-success claims.

Visual observations are model interpretations, not historical verification or identity attribution. The current worker samples at most four frames, prefers configured Ollama for vision/text and uses a configured cloud provider only when Ollama is absent. Missing providers or empty output remain unavailable. Media/worker failures surface separately from missing evidence.

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
| Deterministic provenance | Frozen packet only: revision, consent, attribution, media/checksum refs, submitted source metadata, relevant worker run IDs. No web/network/model authority. | `asante.assessment.v1` readiness checks, input hash and timestamp. Missing references are incomplete/blocked; checksums are integrity references, never authenticity proof. | Reviewer resolves technical/consent blockers or escalates missing provenance. |
| Claim/evidence comparison | Bounded frozen narrative, edited report and at most 50 submitted source records/excerpts. Provider receives untrusted story/source data; cannot write projects, decisions, publication or media. No extra web collection. | Claim types and `supported`, `contradicted`, `insufficient_evidence`, `not_assessed`; only submitted source IDs and exact excerpts. Timeout, provider unavailable and malformed output remain distinct states. | Pending, missing, invalid or unavailable result blocks approval; reviewer escalates. Evidence concerns and uncertainty require human judgment. |

One unique PostgreSQL assessment job is enqueued in the submission transaction. A lease must be present and unexpired before progress/result writes. Derived results stay in job records, preserving packet bytes and contributor authorship. Keyword heritage checks are advisory attention only. This slice has deterministic fake/unit coverage only; it does not establish provider accuracy, authenticity assessment, plagiarism detection, deepfake detection or cultural acceptance.
