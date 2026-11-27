# Notes on the solution

## Main design decisions

- **Separation of concerns.** The statistics live in a pure Python module
  (`analysis.py`) with no web or database code, so they can be tested and reused on
  their own. The API, the importer and the tests all call the same functions.
- **FastAPI + PostgreSQL.** FastAPI gives typed request/response models, validation
  and Swagger docs for free. Uploads, analysis jobs and per-gene results are stored in
  PostgreSQL, so results survive restarts and application-only redeployments
  (`recreate_app_only`). The raw CSVs are stored with each dataset for reproducibility.
- **No graph database.** The networks here have a few hundred edges; edges are a
  simple table in PostgreSQL, filtered to significant genes in SQL and drawn in the
  browser with Cytoscape.js. Neo4j would add operational weight without benefit at this
  scale.
- **Asynchronous jobs, simply.** Starting an analysis returns `202` with a job ID; the
  computation runs as a FastAPI background task and the UI polls the status. This keeps
  the API contract ready for a real task queue without introducing one now.
- **Authentication.** A single user configured via environment variables, login
  returns a signed JWT (bearer token) required by every endpoint except health/login.
- **One-command start.** Docker Compose with health checks and development defaults:
  `docker compose --profile import up --build` also loads example data through the API.
  All resources carry a project label, so cleanup never touches other Docker objects.

## Statistical test and multiple-testing correction

- **Welch's t-test on log2(x+1) values.** Expression data are roughly log-normal, so
  the test is done on the log scale, where the mean difference is directly the log2
  fold change. Welch's version does not assume equal variances in the two groups,
  which is safer with 6 vs 6 samples than Student's t-test; with small n it is more
  powerful than the Mann–Whitney test, whose smallest attainable p-value with 6 vs 6
  is about 0.002 and which therefore resolves strong effects poorly after FDR correction.
- **Benjamini–Hochberg FDR.** In exploratory screens controlling the false discovery
  rate is the usual trade-off; Bonferroni (family-wise error) would be overly
  conservative for 200+ correlated tests. Genes with zero variance are reported with
  NaN and excluded from the correction.

## What I would improve or add with more time

- Moderated statistics (limma-style empirical Bayes variance shrinkage) – better for
  small n; count-based models (DESeq2/edgeR) for raw RNA-seq counts.
- Volcano plot, more than two groups / covariates, gene ID mapping for STRING exports.
- Database migrations (Alembic), a real task queue (RQ/Celery) for large datasets,
  multi-user accounts, HTTPS, frontend unit and end-to-end (Playwright) tests.

Deliberately left out: user management, HTTPS/reverse proxy for production,
Kubernetes.

## Tools used, including AI assistants, and how their output was checked

> **TODO – write this section yourself, honestly.** Suggested points:
> - The initial code draft was generated with Claude (Anthropic, Opus 5.5) based on a
>   written specification; Claude Code was used for … (fill in).
> - What you reviewed and changed by hand.
> - How you verified it: `make verify`, CI pipeline results, manual walkthrough of the
>   UI, checking the statistics against SciPy/statsmodels and the simulated truth,
>   reading every file.
