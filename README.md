# CausalOmics – differential expression web app

A small web application that makes a two-group differential expression analysis
available to users without coding skills:

1. **Analysis module** (`backend/app/analysis.py`): per-gene log2 fold change,
   Welch's t-test and Benjamini–Hochberg FDR correction.
2. **REST API** (FastAPI): upload input files, start an analysis, poll its status,
   fetch results (JSON or CSV) and a network of significant genes. JWT-protected.
3. **Browser UI** (React): upload, run, sortable/filterable results table and an
   interactive gene–gene network (Cytoscape.js) coloured by fold change.
4. **Engineering**: unit + API tests, Docker Compose (one command), GitLab CI and
   GitHub Actions, Ansible roles for deploy / import / clean.

Design decisions and limitations are summarised in [NOTE.md](NOTE.md).

---

## Quick start

Requirements: **Docker** with the Compose plugin (Docker Desktop on macOS/Windows).
Nothing else needs to be installed on the host.

```bash
git clone <this repository> && cd causalomics-de
docker compose --profile import up --build
```

Open <http://localhost:8080> and sign in with **admin / admin** (development defaults).
The `import` profile loads an example dataset (200 genes, 6 vs 6 samples) and an edge
list, and runs a first analysis, so results are visible right away.

Without example data: `docker compose up --build`, then upload the files from
`data/sample/` in the UI.

| URL | |
| --- | --- |
| <http://localhost:8080> | Web UI (nginx, proxies `/api`) |
| <http://localhost:8080/api/docs> | Interactive API documentation (Swagger) |
| <http://localhost:8001/api/health> | Backend directly |

Stop with `docker compose down` (data is kept in the `pgdata` volume) or
`make clean-all` to remove everything including data.

### Configuration

All settings have development defaults. For anything beyond local use, copy
`.env.example` to `.env` and set at least `APP_PASSWORD`, `JWT_SECRET` and
`POSTGRES_PASSWORD`.

---

## Using the application

**Analysis tab** – upload an expression table and a sample annotation, pick the
reference group, start the analysis. The table can be sorted by any column, filtered
by gene name and adjusted p-value, and downloaded as CSV.

**Network tab** – upload (or select) a gene–gene edge list, choose thresholds
(adjusted p, |log2 FC|) and display the significant genes. Node colour: blue = lower,
red = higher in the comparison group; click a node for its values.

### Input formats

Comma-, tab- or semicolon-separated text with a header row.

`expression.csv` – genes as rows, samples as columns (linear scale by default; untick
"Apply log2(x+1)" for data that is already log-transformed):

```
gene,ctrl_1,ctrl_2,ctrl_3,ctrl_4,ctrl_5,ctrl_6,treat_1,...
GENE001,816.47,612.05,681.95,652.62,750.03,1009.38,700.32,...
```

`annotation.csv` – exactly two groups, at least two samples each:

```
sample,group
ctrl_1,control
treat_1,treated
```

`edges.csv` – `gene_a,gene_b[,score]`. STRING exports (`#node1 node2 ... combined_score`)
are accepted as well; scores on a 0–1000 scale are rescaled to 0–1.

The sample files were generated with `python -m app.simulate ../data/sample` (run in
`backend/`, fixed seed).

### API example (curl)

```bash
API=http://localhost:8080/api
TOKEN=$(curl -s -X POST $API/auth/login -d "username=admin&password=admin" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
AUTH="Authorization: Bearer $TOKEN"

# upload
DATASET=$(curl -s -H "$AUTH" -F expression=@data/sample/expression.csv \
  -F annotation=@data/sample/annotation.csv $API/datasets | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# start the analysis (runs in the background) and check its status
JOB=$(curl -s -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"dataset_id\": \"$DATASET\", \"reference_group\": \"control\"}" $API/analyses \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -H "$AUTH" $API/analyses/$JOB

# results as JSON or CSV
curl -s -H "$AUTH" "$API/analyses/$JOB/results?format=csv" | head
```

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/auth/login` | form `username`, `password` → bearer token |
| POST | `/api/datasets` | multipart `expression`, `annotation`, optional `name` |
| GET | `/api/datasets` | list datasets |
| POST | `/api/edges` | multipart `file`, optional `name` |
| GET | `/api/edges` | list edge lists |
| POST | `/api/analyses` | `{dataset_id, reference_group?, log_transform?}` → 202 |
| GET | `/api/analyses/{id}` | status: queued / running / done / failed |
| GET | `/api/analyses/{id}/results` | `?format=json\|csv` |
| GET | `/api/analyses/{id}/network` | `?edge_list_id=…&padj=0.05&min_abs_lfc=1` |
| GET | `/api/health` | liveness (no auth) |

---

## Tests

```bash
make test          # backend: ruff + pytest in Docker; frontend: type-check + build
make verify        # tests, start the stack, smoke-test UI and API
```

- `backend/tests/test_analysis.py` – statistics on simulated data with known truth
  (planted genes are found, few false positives), Welch t-test against SciPy, BH
  against hand-computed values and `statsmodels`, input validation.
- `backend/tests/test_api.py` – authentication, the full upload → analyse → results →
  network flow, error responses.

Locally the API tests use in-memory SQLite; CI runs them against PostgreSQL
(`TEST_DATABASE_URL`).

Without Docker: `cd backend && pip install -r requirements-dev.txt && pytest`.

### Continuous integration

- **GitLab** (`.gitlab-ci.yml`): lint (ruff, Ansible syntax, ansible-lint) → test
  (pytest with a PostgreSQL service, frontend build) → build (Docker images) →
  deploy (manual, Ansible).
- **GitHub Actions** (`.github/workflows/ci.yml`): the same tests plus an end-to-end
  job that starts the compose stack with the importer and smoke-tests it.

---

## Deployment with Ansible

Ansible (≥ 2.15) and the `community.docker` collection are needed on the control node.
Every setting lives in `ansible/group_vars/all.yml`.

```bash
cd ansible
ansible-galaxy collection install -r requirements.yml

ansible-playbook site.yml                            # deploy (db, backend, frontend)
ansible-playbook site.yml -e recreate_app_only=true  # rebuild backend + frontend, keep the database
ansible-playbook site.yml --tags import              # load example data via the importer
ansible-playbook site.yml --tags clean               # remove this project's Docker artifacts
```

| Role | What it does |
| --- | --- |
| `deploy` | optionally installs Docker, fetches the code (`source_mode`: inplace / git / local), writes `.env`, runs `docker compose up --build`, waits for `/api/health` |
| `import` | runs the importer container (when `run_import: true` or `--tags import`) |
| `clean_project` | removes only containers, networks and built images labelled `com.causalomics.project=<project_name>`; volumes only with `clean_remove_volumes: true`; tagged `never`, so it runs only with `--tags clean` |

**`recreate_app_only: true`** rebuilds and force-recreates only `backend` and
`frontend` (`--no-deps`). The database container and the `pgdata` volume are not
touched, so uploaded data and results survive an application update.

By default the inventory targets `localhost` and deploys the checked-out repository in
place. For a server: add it to `inventory.ini`, set `source_mode: git`, `git_repo`,
and vault the passwords (`ansible-vault encrypt_string`).

---

## Project structure

```
backend/          FastAPI app, analysis module, importer, tests, Dockerfile
  app/analysis.py   statistics (no web dependencies)
  app/simulate.py   simulated expression data + edge list
  app/importer.py   data import service (loads data through the API)
frontend/         React + Vite + TypeScript, nginx config, Dockerfile
data/sample/      example input files
ansible/          playbook, group_vars/all.yml, roles deploy/import/clean_project
docker-compose.yml, Makefile, .gitlab-ci.yml, .github/workflows/ci.yml
```
