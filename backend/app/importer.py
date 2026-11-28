"""Data import service.

Loads input data into a running instance *through the REST API* (so the import
exercises the same validation as the UI), then starts an analysis:

    python -m app.importer --api http://backend:8000/api --data-dir /data

If the data directory has expression.csv / annotation.csv / edges.csv they are
used, otherwise simulated data (200 genes, 6 vs 6 samples) is generated.
Re-running is safe: an existing dataset with the same name is not imported again.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
from pathlib import Path

import httpx

from app.simulate import simulate


def wait_for_api(client: httpx.Client, timeout_s: int = 120) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if client.get("/health").status_code == 200:
                return
        except httpx.TransportError:
            pass
        if time.monotonic() > deadline:
            sys.exit("API did not become healthy in time")
        time.sleep(2)


def load_inputs(data_dir: Path) -> dict[str, tuple[str, bytes]]:
    names = {"expression": "expression.csv", "annotation": "annotation.csv", "edges": "edges.csv"}
    if all((data_dir / f).is_file() for f in names.values()):
        print(f"Using files from {data_dir}")
        return {key: (fname, (data_dir / fname).read_bytes()) for key, fname in names.items()}

    print("No input files found; generating simulated data")
    sim = simulate()
    out = {}
    for key, frame, index in (
        ("expression", sim.expression, True),
        ("annotation", sim.annotation, False),
        ("edges", sim.edges, False),
    ):
        buf = io.StringIO()
        frame.to_csv(buf, index=index)
        out[key] = (names[key], buf.getvalue().encode())
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default=os.getenv("IMPORT_API_URL", "http://backend:8000/api"))
    parser.add_argument("--data-dir", default=os.getenv("IMPORT_DATA_DIR", "/data"))
    parser.add_argument(
        "--dataset-name", default=os.getenv("IMPORT_DATASET_NAME", "example-dataset")
    )
    parser.add_argument("--username", default=os.getenv("APP_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("APP_PASSWORD", "admin"))
    parser.add_argument("--force", action="store_true", help="import even if the dataset exists")
    args = parser.parse_args()

    with httpx.Client(base_url=args.api, timeout=60) as client:
        wait_for_api(client)
        token = client.post(
            "/auth/login", data={"username": args.username, "password": args.password}
        )
        token.raise_for_status()
        client.headers["Authorization"] = f"Bearer {token.json()['access_token']}"

        existing = [d for d in client.get("/datasets").json() if d["name"] == args.dataset_name]
        if existing and not args.force:
            print(f"Dataset '{args.dataset_name}' already exists ({existing[0]['id']}); skipping.")
            return

        files = load_inputs(Path(args.data_dir))
        resp = client.post(
            "/datasets",
            files={"expression": files["expression"], "annotation": files["annotation"]},
            data={"name": args.dataset_name},
        )
        if resp.status_code != 201:
            sys.exit(f"Dataset upload failed: {resp.status_code} {resp.text}")
        dataset = resp.json()
        print(f"Dataset {dataset['id']}: {dataset['n_genes']} genes, groups {dataset['groups']}")

        analysis_resp = client.post("/analyses", json={"dataset_id": dataset["id"]})
        if analysis_resp.status_code != 202:
            sys.exit(f"Analysis start failed: {analysis_resp.status_code} {analysis_resp.text}")
        job = analysis_resp.json()

        resp = client.post(
            "/edges",
            files={"file": files["edges"]},
            data={"name": f"{args.dataset_name}-edges", "analysis_id": job["id"]},
        )
        if resp.status_code != 201:
            sys.exit(f"Edge list upload failed: {resp.status_code} {resp.text}")
        print(f"Edge list {resp.json()['id']}: {resp.json()['n_edges']} edges")

        for _ in range(120):
            job = client.get(f"/analyses/{job['id']}").json()
            if job["status"] in ("done", "failed"):
                break
            time.sleep(1)
        print(f"Analysis {job['id']}: {job['status']} {job.get('error') or ''}".rstrip())
        if job["status"] != "done":
            sys.exit(1)


if __name__ == "__main__":
    main()
