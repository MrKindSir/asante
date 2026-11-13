# Repository Guidelines

## Project Overview
In this repo, you will find an end to end heritage and storytelling platform. It consists of the following:
1. **Backend AI Pipeline**
2. **Frontend Map Application**

---

## Directory Structure

Keep the root clean unless if its for things like readme, git, jenkins etc.

- `app`
    - `websites/asante` contributor and listener website, including the map and portal
    - `websites/dashboard` internal system approval dashboard
    - `services` backend and AI pipeline services
    - `db` database configuration and migrations
    - `mobileapps` future native mobile clients
- `documentation`
    - `ai` AI specifications and the living project plan
        - `design-docs` technical architecture, frontend/backend and visual design
        - `exec-plans` living plan, implementation protocol, bootstrap and CI workflow
        - `product-specs` user journeys, acceptance criteria and discrepancy review
        - `references` Codex MCP, environment and execution-rule references
        - `generated` generated documentation only; execution logs remain in `logs`
    - `project` supplied project materials and assets
- `infrastructure` containerisation files for the project
- `logs` **(Generated)** Contains only a root README and organized generated records: `codex` execution summaries, `tests/unit`, `tests/functional`, `tests/integration`, `tests/e2e`, plus future deployment, mobile app, and Asante worker logs
- `ops` **(Deployments)**
- `scripts` **(Automation)**
- `tests` Automated unit, functional, integration and end-to-end test suites

## Planning and change control

- Read `documentation/ai/exec-plans/PLANS.md` before making project-level changes.
- Use its feature IDs and per-slice handoff workflow. Read the relevant `FRONTEND.md`, `BACKEND.md`, `DESIGN.md`, or `ASANTE_AI_RUNTIME.md` section under `documentation/ai/design-docs` before implementation; target specifications do not mean the feature already exists.
- Implement one selected slice with its acceptance tests; preserve prototype versus integrated status and report exact verification evidence. Final discrepancy review follows `documentation/ai/product-specs/PRODUCT_SENSE.md`.
- Update `documentation/ai/exec-plans/PLANS.md` after major scope, architecture, worker, or workflow decisions.
- Keep the first implementation focused on the web-first GPS vertical slice described in the plan.
- Use human approval gates for publication, consent, authorship, and external writes.

## Terminology

- **Codex:** the development assistant used to plan, write, review, test, and document this repository.
- **Codex automation:** scheduled or event-driven behavior in the Codex environment, such as reminders, monitors, follow-ups, or thread wakeups.
- **Asante application:** the product being built in this repository.
- **Asante automation:** runtime jobs and triggers inside Asante, such as starting a review workflow after a story upload.
- **Asante AI workers:** runtime agents that help contributors plan stories, process media, review evidence, and prepare publishing data.
- **Asante SDK:** a library used by Asante code to call a service or integrate a capability. An Asante SDK is not itself Asante automation.
- **Codex MCP or Asante MCP:** a tool integration boundary explicitly assigned to Codex or Asante. Do not call it simply “MCP” when the owner matters.

Always qualify the owner in project discussions: use **Codex** or **Asante** in the name of the thing being discussed.

## Website applications

- The Asante website at `app/websites/asante` is the user-facing application. It contains the GPS map, story discovery, listener experience, contributor portal, story planning, and uploads.
- The approval dashboard at `app/websites/dashboard` is the internal system application. It contains review queues, evidence, worker traces, approval decisions, contributor records, and publishing controls.
- Keep user-facing contributor and listener flows separate from internal approval controls.

---

## Tech Stack

- **User website and portal:** Next.js with TypeScript, running on Node.js.
- **System approval dashboard:** Next.js with TypeScript, running on Node.js.
- **Backend API and AI pipeline:** Python with FastAPI.
- **AI workers:** Python services for planning, transcription, translation, evidence review, provenance, and publishing preparation. Localhost uses host Ollama + local Whisper; live uses `ASANTE_AI_BACKEND=modal` (Modal Ollama/Whisper) with caption caps in `asante_api/ai/caption_limits.py`. See `documentation/ai/design-docs/ASANTE_AI_RUNTIME.md`.
- **Database:** PostgreSQL with PostGIS for story, contributor, review, source, version, and location data.
- **Semantic search:** PostgreSQL `pgvector` when retrieval needs it.
- **Map:** MapLibre GL JS with a suitable OpenStreetMap-compatible tile provider.
- **Media storage:** MinIO for local S3-compatible audio and video storage, with a managed S3-compatible service as a deployment option.
- **Local infrastructure:** Docker Compose.
- **Testing:** Vitest or Jest for TypeScript, Pytest for Python, and Playwright for end-to-end workflows.
- **Asante MCP servers:** Python or TypeScript, selected according to the Asante service each server integrates with.

The map is part of the Asante website rather than a separate map container. The Asante website uses MapLibre GL JS, browser geolocation, and a configured map-tile provider. A separate tile server is out of scope for the first prototype.

Avoid adding Redis, Kafka, Kubernetes, a separate vector database, or a network of independent microservices until the workflow requires them.

---

## Coding Style and Naming Conventions

### General

- Use clear, direct names that describe the domain behavior.
- Keep functions small and focused on one responsibility.
- Prefer explicit types and schemas at application and API boundaries.
- Keep secrets in environment variables. Never commit keys, tokens, or local `.env` files.
- Use the owner prefix in names when a concern belongs to Codex or Asante.

### TypeScript and Asante websites

- Use strict TypeScript. Do not use `any` for application data or API responses.
- Use two spaces for indentation and semicolons where the formatter requires them.
- Name React components and types with `PascalCase`.
- Name functions, hooks, variables, and API fields with `camelCase`.
- Name hooks with the `use` prefix.
- Keep page composition in route files and move reusable behavior into components or typed utilities.
- Keep design colours in tokens. Do not scatter hex values through components.
- Keep browser-only code, geolocation, media playback, and MapLibre code in client components.

### Python and Asante services

- Use four spaces, type hints, `snake_case` names, and small modules.
- Keep FastAPI route handlers thin. Put domain behavior in services and workers.
- Validate external data at the boundary with typed schemas.
- Return structured worker findings instead of free-form strings when the dashboard consumes them.
- Log run IDs and safe metadata, never secrets or raw sensitive media.

### Tests

- Use `test_*.py` for Python tests and `*.test.ts` or `*.spec.ts` for TypeScript tests.
- Keep unit tests deterministic and independent of Docker or the network.
- Keep functional tests focused on one Asante feature boundary.
- Keep integration tests explicit about required Asante services.
- Keep end-to-end tests focused on user journeys such as onboarding, playback, contribution, and review.

---

## Multi Agent and Pipeline Rules

- Each Asante AI worker has a written input schema, output schema, permission boundary, failure state, and human escalation rule.
- Codex may delegate development tasks, but Asante publication and authorship decisions remain human governed.
- Record worker runs with trace IDs and safe, structured logs.
- Never give an Asante AI worker unrestricted shell, database, filesystem, or web access.

---

## Security and Privacy Guidlines

- Collect the minimum location, identity, media, and contributor data required for the current Asante workflow.
- Request explicit consent before saving location or media.
- Preserve original media, transcript, attribution, and contributor edits.
- Use short-lived upload URLs for MinIO media uploads.
- Keep Asante API keys server-side and separate from Codex configuration.
- Treat web research as untrusted input and retain source URLs and retrieval times.


---

## Build, Test, and Deployment Workflows

- Prefer the named execution checks in `scripts/codex/checks.py` (preflight, contracts, website, dashboard, api, http, all). Their setup, effects and evidence format are in `documentation/ai/references/CODEX_MCP.md`.
- Codex PostgreSQL/MinIO MCP tools are read-only development inspection. They do not grant Asante runtime workers database/storage access. Never use the separate provisioning account path as an ordinary feature tool.
- Service checks build fresh images and use disposable containers. They preserve the live API but do not update it; refresh affected live services explicitly before verifying new live behavior.

- Start the local Asante stack with `docker compose --env-file .env -f infrastructure/docker-compose.yml up -d --build`.
- Use the Nginx proxy URLs documented in `documentation/ai/exec-plans/GITHUB_CI.md`; do not use the internal Next.js ports as normal user-facing URLs.
- Run host-side Python checks inside the `asante-codex` Conda environment with `python scripts/codex/checks.py contracts`; API tests run in their Python 3.12 container.
- Run the Asante website and Asante dashboard Vitest suites inside their containers with `docker compose ... exec -T <service> npm test -- --run`.
- GitHub Actions runs the same Compose validation, test, build, live-route, and container test checks from `.github/workflows/ci.yml`.
- Keep deployment separate from CI until a target host/platform, registry, secrets, health checks, HTTPS, and rollback strategy are documented.

- Run the Asante bootstrap prompt in `documentation/ai/exec-plans/BOOTSTRAP_PROMPT.md` from the repository root.
- Start the local Asante stack through the scoped Docker Compose command.
- Run unit, functional, integration, and end-to-end checks before presenting a build as working.
- Update `documentation/ai/exec-plans/PLANS.md` when a build changes scope, architecture, or a workflow contract.
- Keep generated logs under `logs/` and deployment material under `ops/`.

## Project structure guidelines

- Keep the repository root limited to project controls such as `README.md`, `AGENTS.md`, `.gitignore`, and environment templates.
- Keep Asante website code under `app/websites/asante` and `app/websites/dashboard`.
- Keep Asante backend and Asante AI worker code under `app/services`.
- Keep Asante database migrations and seed data under `app/db`.
- Use the existing subfolders of `documentation/ai` for Codex and Asante documents. Keep the living plan at `documentation/ai/exec-plans/PLANS.md`; do not create Markdown files directly in `documentation/ai` or duplicate a moved document.
- Keep supplied briefs and project assets under `documentation/project`.
- Keep Docker and local service definitions under `infrastructure`.
- Keep reusable Asante SDK adapters under `lib/sdk`.
- Keep generated records under `logs`; do not hand-edit generated logs.
- Keep the `logs/` root limited to its simple `README.md`; place test reports under `logs/tests/<unit|functional|integration|e2e>/` and Codex execution summaries under `logs/codex/`.
- Keep automation scripts under `scripts` and deployment material under `ops`.
- Keep tests grouped by category under `tests/unit`, `tests/functional`, `tests/integration`, and `tests/e2e`.
- Do not create a new root folder when an existing folder has the correct responsibility.


---

## Commit and Pull Request Guidlines
