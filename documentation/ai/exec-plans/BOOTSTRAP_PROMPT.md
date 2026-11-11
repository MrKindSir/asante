# Asante bootstrap prompt

Use this prompt in Codex or a similar development tool from the repository root:

```text
You are setting up the Asante repository. Read AGENTS.md and documentation/ai/exec-plans/PLANS.md first. Keep Codex concerns separate from Asante concerns. Do not change or delete existing secrets, local Codex configuration, or user files without explicit permission.

1. Inspect the repository and verify that the current paths are app/websites/asante, app/websites/dashboard, infrastructure, documentation/ai, documentation/project, and tests.
2. Confirm the project Conda environment exists. If missing, create it with `conda env create --file scripts/codex/environment.yml`, then activate it with `conda activate asante-codex`. Confirm `python --version` reports Python 3.12. Use this environment for host-side Asante Codex scripts; GitHub CI and the Asante API container use their own Python 3.12 runtimes.
3. Confirm Docker is available. If the Docker daemon is not running, ask the developer to start Docker Desktop or the local Docker service.
4. Copy .env.example to .env only if .env does not exist. Preserve any existing .env values.
5. Start the local Asante stack with:
   docker compose --env-file .env -f infrastructure/docker-compose.yml up -d --build
6. Prepare the catalogue explicitly (migrations are not API startup side effects):
   docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api python -m alembic -c app/db/alembic.ini upgrade head
   docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api python -m app.db.seed
   docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api python -m app.db.seed_media
   Provision local test accounts with `python scripts/asante/accounts.py` from the activated host Conda environment. It generates/reuses .env.asante-test-accounts and does not print passwords.
   Optional review-desk fixtures from TestData (includes on-topic African stories and deliberate off-topic packets for the heritage gate):
   docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api python -m app.db.seed_review_submissions
   The `job-worker` service claims queued relevance/transcribe/translate/analyze jobs after submit.
   Wait for MinIO to be ready before seeding media; rerunning these commands preserves existing records and objects. Verify /asante/api/health/ready returns 200.
   Verify PostgreSQL is healthy, MinIO is running, the proxy is running, the Asante map responds on http://localhost/asante/, the Asante portal responds on http://localhost/asante/portal/, and the Asante dashboard responds on http://localhost/asante/review/.
7. Run the shared execution checks from the activated `asante-codex` environment:
   python scripts/codex/checks.py all
   This includes repository checks, fresh website/dashboard/API images, isolated tests, type checks, production compilation and strict live HTTP checks. It does not refresh running app containers; step 5 has already done that.
8. Read the generated JSON execution summary under logs/codex and its matching test evidence under logs/tests/<category>; report exact failures/skips.
9. For focused changes use the website, dashboard, api, contracts or http job instead of repeating all builds unnecessarily.
10. Codex MCP setup is optional for running Asante. If specifically authorized, run `python scripts/codex/checks.py mcp-setup` and then `mcp-verify` from the activated Conda environment; read documentation/ai/references/CODEX_MCP.md first. Do not provision Codex accounts or edit local Codex settings just to start the Asante app.
11. Verify /asante/api/health and run HTTP smoke tests with ASANTE_REQUIRE_SERVICES=1 so unavailable services fail. Use reviewer@asante.test and its generated password from the ignored .env.asante-test-accounts file for /asante/review/. Contributor accounts use the same password sign-in at /asante/portal/.
12. Report the exact services, URLs, tests, failures, and any required permissions. Do not claim success without checking the live routes. Profiles, saved drafts, submission snapshots and review decisions persist in PostgreSQL; original uploads and browser import backups persist in MinIO. Open /asante/portal/ to explicitly import and clear any old Asante browser records after verification. Email/password accounts and revocable sessions are implemented; provider SSO, email verification/recovery, derivative processing and live Asante AI integrations remain pending.
13. Update documentation/ai/exec-plans/PLANS.md only when setup state or project decisions change.
```

## Environment fallback

The prompt uses `.env` as the Asante fallback. The file is ignored by Git. Developers should copy `.env.example` to `.env` and add their own `OPENAI_API_KEY` and map provider token when those integrations are enabled.

## Platform notes

- macOS: start Docker Desktop, then run the prompt from Terminal or Codex.
- Linux: start the Docker service and ensure the current user can access the Docker socket.
- Windows: use Docker Desktop with the WSL2 backend and run the commands from PowerShell or WSL.
