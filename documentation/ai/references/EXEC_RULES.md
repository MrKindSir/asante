# Codex ExecRules for Asante

## Purpose

These are Codex permissions for managing the local Asante Docker Compose stack. They control the Codex development workflow. They do not grant permissions to the running Asante application.

## Allowed Codex commands

The user-level Codex rules at `~/.codex/rules/default.rules` currently allow these scoped Asante Compose command families from the repository root:

```text
docker compose --env-file .env -f infrastructure/docker-compose.yml start
docker compose --env-file .env -f infrastructure/docker-compose.yml stop
docker compose --env-file .env -f infrastructure/docker-compose.yml restart
docker compose --env-file .env -f infrastructure/docker-compose.yml up ...
docker compose --env-file .env -f infrastructure/docker-compose.yml ps ...
docker compose --env-file .env -f infrastructure/docker-compose.yml logs ...
docker compose --env-file .env -f infrastructure/docker-compose.yml exec ...
```

The same scoped `down ...` command is approval-gated.

The `down` prefix prompts for approval. Since Codex rules match command prefixes and apply the strictest matching decision, appended volume/image-removal flags remain approval-gated too. Never add an automatic allow for `down -v`, `down --volumes`, `docker volume rm/prune`, or `down --rmi`.

Unattended Codex commands now include read-only Git inspection (`git status`, `git diff`, `git log`, `git show`), scoped Compose configuration validation and image builds, and the named project checks (`preflight`, `contracts`, `website`, `dashboard`, `api`, `http`, `all`) through `/opt/anaconda3/bin/conda run --no-capture-output -n asante-codex python scripts/codex/checks.py`. The API job creates and drops only a uniquely named temporary test database. Keep publication, deployment, Git add/commit/push, dependency installation outside the pinned image build, Codex MCP provisioning/configuration, database volume removal, and commands with arbitrary shell or SQL as approval-required actions.

Codex tool approval prompts and `default.rules` are related but separate layers. An approval-prefix shown by the app may be session/tool-specific; this file documents the persistent user rule file. The Conda executable path is machine-specific and may need updating on another computer.

## Source of truth

The Codex execution runner `python scripts/codex/checks.py <allowlisted-job>` runs inside the `asante-codex` Conda environment and wraps scoped Compose checks. It does not grant shell/SQL execution through Codex MCP. The active rules were validated with `codex execpolicy check`; restart Codex to load changes. Tool-call approval prefixes granted by a user are separate from the documented rule file and may vary by machine.

The project MCP launcher needs Docker access to run an isolated stdio container. Its seven tools remain read-only regardless of Docker's administrative setup commands. Setup/provisioning and negative permission verification are explicit CLI jobs, not exposed MCP tools.

The active Codex rules are stored outside the repository at:

```text
~/.codex/rules/default.rules
```

The repository cannot enforce local Codex rules. Back up the current file before updating it, validate rules with `codex execpolicy check`, then restart Codex for the rules to load. Keep this document aligned with the active local file when the rules change.

## Backup

The earlier Asante Docker-rule backup is:

```text
.codex-backup/2026-11-05/default.rules.before-asante-docker
```

The latest pre-change rules backup is:

```text
.codex-backup/2026-11-07/default.rules.before-common-asante-checks
```
