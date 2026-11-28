# CausalOmics take-home – rules for Claude Code

This repository is a complete first draft that has NOT been run yet. Goal: make it work
end-to-end without changing the architecture, then polish.

## Handling ambiguity & decisions
* **Minor/reversible choices:** Do not stop to ask. Pick the simplest, most idiomatic option
  that matches the existing codebase and log it in `DECISIONS.md` as `Decision — one-line reason`
  (no dates; git history has them).
* **Major/breaking choices:** Ask before writing code only if the choice changes a database
  schema, a public API contract, authentication/security behaviour, core architecture, or adds
  a new third-party dependency. Fixing or pinning existing dependencies is NOT major.
  Present 2–3 concrete options with a recommended default.
* **If no answer is available (unattended run):** log the question under "NEEDS DECISION" in
  `DECISIONS.md` with the recommended default, continue with steps that do not depend on it,
  and do not build on the undecided part.
* **Keep `DECISIONS.md` focused:** Only log choices that future developers or sessions need to
  know to maintain consistency. Skip trivial naming or formatting choices.

## Working mode
- Keep PROGRESS.md as a checklist. Commit after each step (conventional commits). Never `git push`.
- A step is done only when its check passes; show the command output as evidence.
- If a problem is not solved after 3 attempts, write it under "BLOCKED" in DECISIONS.md and move on.
- Never run `docker system prune`, `docker volume prune`, `docker volume rm`, `sudo`, or touch
  Docker resources without the label com.causalomics.project. Never commit `.env` or secrets.
- When compacting, keep: current step, open BLOCKED and NEEDS DECISION items, the check
  commands below.

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