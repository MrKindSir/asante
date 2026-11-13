# Asante - Heritage and Storytelling Platform

Asante uses GPS to connect community stories to landmarked places. Contributors can use AI workers to plan and upload supported video or audio stories in approved languages. A human-governed AI workflow helps review claims, prepare translations, track contributions, and preserve authorship.

The current project plan and implementation status are maintained in [documentation/ai/exec-plans/PLANS.md](documentation/ai/exec-plans/PLANS.md).

## License

Asante was developed for a competition and is available under the custom
[Asante Educational Use License](LICENSE). Use, modification, and sharing are
permitted solely for noncommercial learning, teaching, educational research,
learning experiments, and evaluation or demonstration of this competition entry.
Commercial use requires separate written permission from the relevant copyright
holders. This is source-available software with use restrictions, not an
unrestricted open-source license.

These terms remain applicable to this version unless separate permission is
granted. Future releases may use updated terms; there is no automatic change to
commercial-use permission. Third-party software and contributor content retain
their own licenses and consent requirements. See [LICENSE](LICENSE) for the full
terms.

## Project structure

- `app/websites/asante/` user-facing map, story discovery, contributor portal, planning, and uploads
- `app/websites/dashboard/` internal system approval dashboard
- `app/services/api/` Asante API and first non-GUI vertical slice
- `app/services/` backend and AI pipeline services
- `app/db/` database configuration and migrations
- `app/mobileapps/` future native mobile clients
- `documentation/ai/` AI specifications and the living project plan
- `documentation/project/` supplied capstone and onboarding materials
- `infrastructure/` local infrastructure and containers
- `lib/sdk/` shared Asante SDK adapters
- `logs/` generated run records
- `ops/` deployment material
- `scripts/` Asante automation scripts
- `tests/` automated tests


## Getting started

From the repository root, copy `.env.example` to `.env` if needed and start the Asante stack:

```bash
docker compose --env-file .env -f infrastructure/docker-compose.yml up -d --build
```

Open the Asante website at `http://localhost/asante/`, the contributor portal at `http://localhost/asante/portal/`, and the Asante approval dashboard at `http://localhost/asante/review/`.

The Asante API is available through the proxy at `http://localhost/asante/api/health` and supports nearby landmark/story queries under `/asante/api/v1/`.

The current Asante UI includes map onboarding, story discovery, account sign-in, persistent contributor profiles/drafts, planning previews, real media uploads, public contributor profiles, and a reviewer account workspace. The browser test checklist and current integration limits are in [tests/README.md](tests/README.md) and [documentation/ai/design-docs/FRONTEND.md](documentation/ai/design-docs/FRONTEND.md).

For a standalone run or live demo, Asante's proxy uses host port `80` and serves the clean URLs above. When sharing port `80` with another local reverse proxy, set `ASANTE_HTTP_PORT=8082` in the ignored root `.env`; keep Asante's internal `/asante` routes enabled and route that path to port `8082`. Return the value to `80` for standalone/live-demo mode, after ensuring no other server owns port `80`. The internal website ports are not part of normal user URLs.

After migrations/catalogue/media setup, run `python scripts/asante/accounts.py` from the activated `asante-codex` environment to create reusable local contributor/reviewer accounts. Generated passwords remain in ignored `.env.asante-test-accounts`; do not commit that file.

The reproducible setup instructions are in [documentation/ai/exec-plans/BOOTSTRAP_PROMPT.md](documentation/ai/exec-plans/BOOTSTRAP_PROMPT.md).

GitHub Actions and local proxy setup are documented in [documentation/ai/exec-plans/GITHUB_CI.md](documentation/ai/exec-plans/GITHUB_CI.md).

Create the project Conda environment with `conda env create --file scripts/codex/environment.yml`, activate it with `conda activate asante-codex`, then run reproducible development checks with `python scripts/codex/checks.py all`. Codex read-only PostgreSQL/MinIO tools, setup and permission verification are documented in [documentation/ai/references/CODEX_MCP.md](documentation/ai/references/CODEX_MCP.md).



## Dashbboard



## Mobile App



## Notes

Presentation speaker notes and feature Q&A: [documentation/project/PRESENTATION_NOTES.md](documentation/project/PRESENTATION_NOTES.md).
