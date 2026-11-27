# CausalOmics take-home – rules for Claude Code

This repository is a complete first draft that has NOT been run yet. Goal: make it work
end-to-end without changing the architecture, then polish.

## Working mode
- Do not ask questions. For ambiguous points choose the simplest reasonable option and
  record it in DECISIONS.md (decision + one-line reason).
- Keep PROGRESS.md as a checklist. Commit after each step (conventional commits). Never `git push`.
- A step is done only when its check passes; show the command output as evidence.
- If a problem is not solved after 3 attempts, write it under "BLOCKED" in DECISIONS.md and move on.
- Never run `docker system prune`, `docker volume prune`, `docker volume rm`, `sudo`, or touch
  Docker resources without the label com.causalomics.project. Never commit `.env` or secrets.
- When compacting, keep: current step, open BLOCKED items, the check commands below.

## Host tooling
Only Docker (with compose) and git are installed on the host. Do not install Python, Node or
Ansible locally; run everything in containers.

## Steps
1. `make test-backend` passes (ruff + pytest in the backend test image).
2. `make test-frontend` passes (tsc + vite build). Commit the generated `frontend/package-lock.json`.
3. `docker compose --profile import up --build -d`; importer exits 0; `make smoke` passes.
4. Browser walkthrough: login, upload data/sample files, run analysis, sort table, network tab.
5. Ansible in a container: syntax check, then deploy/import/clean against localhost with a
   different project name and ports; verify that data survives `recreate_app_only=true`.
6. Review README.md accuracy. Do not write NOTE.md's "Tools used" section; the author writes it.

## Key commands
- `make test`, `make up`, `make import`, `make smoke`, `make verify`, `make clean`
- Statistics: Welch t-test on log2(x+1), Benjamini-Hochberg; see backend/app/analysis.py.

## Out of scope
User management, HTTPS, Neo4j, Kubernetes, additional statistical methods.
