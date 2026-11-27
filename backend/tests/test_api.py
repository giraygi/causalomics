import io

import pytest

from app.simulate import simulate


@pytest.fixture(scope="module")
def sim_files():
    sim = simulate(seed=11)

    def to_bytes(frame, index):
        buf = io.StringIO()
        frame.to_csv(buf, index=index)
        return buf.getvalue().encode()

    return {
        "expression": ("expression.csv", to_bytes(sim.expression, True), "text/csv"),
        "annotation": ("annotation.csv", to_bytes(sim.annotation, False), "text/csv"),
        "edges": ("edges.csv", to_bytes(sim.edges, False), "text/csv"),
        "planted": set(sim.true_up) | set(sim.true_down),
    }


def _upload_dataset(client, headers, files):
    return client.post(
        "/api/datasets",
        headers=headers,
        files={"expression": files["expression"], "annotation": files["annotation"]},
        data={"name": "sim"},
    )


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def test_health_is_public(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_wrong_password_rejected(client):
    resp = client.post("/api/auth/login", data={"username": "tester", "password": "nope"})
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/datasets"),
        ("post", "/api/analyses"),
        ("get", "/api/analyses/x/results"),
        ("get", "/api/edges"),
    ],
)
def test_endpoints_require_token(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_invalid_token_rejected(client):
    resp = client.get("/api/datasets", headers={"Authorization": "Bearer not-a-token"})
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Full flow
# --------------------------------------------------------------------------- #
def test_upload_analyse_results_network(client, auth_headers, sim_files):
    resp = _upload_dataset(client, auth_headers, sim_files)
    assert resp.status_code == 201, resp.text
    dataset = resp.json()
    assert dataset["n_genes"] == 200
    assert dataset["groups"] == {"control": 6, "treated": 6}

    resp = client.post(
        "/api/analyses",
        headers=auth_headers,
        json={"dataset_id": dataset["id"], "reference_group": "control"},
    )
    assert resp.status_code == 202, resp.text
    analysis_id = resp.json()["id"]

    # TestClient runs background tasks before returning, so the job is finished.
    job = client.get(f"/api/analyses/{analysis_id}", headers=auth_headers).json()
    assert job["status"] == "done", job
    assert job["comparison_group"] == "treated"

    results = client.get(f"/api/analyses/{analysis_id}/results", headers=auth_headers).json()
    assert len(results) == 200
    significant = {
        r["gene"] for r in results if r["p_adjusted"] is not None and r["p_adjusted"] < 0.05
    }
    assert len(significant & sim_files["planted"]) >= 18

    csv_resp = client.get(
        f"/api/analyses/{analysis_id}/results", params={"format": "csv"}, headers=auth_headers
    )
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert csv_resp.text.splitlines()[0].startswith("gene,mean_reference")

    resp = client.post(
        "/api/edges", headers=auth_headers, files={"file": sim_files["edges"]}, data={"name": "e"}
    )
    assert resp.status_code == 201, resp.text
    edge_list_id = resp.json()["id"]

    network = client.get(
        f"/api/analyses/{analysis_id}/network",
        params={"edge_list_id": edge_list_id, "padj": 0.05, "min_abs_lfc": 1},
        headers=auth_headers,
    ).json()
    node_ids = {n["id"] for n in network["nodes"]}
    assert network["n_significant"] == len(node_ids) > 0
    assert node_ids <= significant
    # every edge connects two displayed (significant) genes
    assert all(e["source"] in node_ids and e["target"] in node_ids for e in network["edges"])
    assert len(network["edges"]) > 0


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #
def test_invalid_expression_file_returns_422(client, auth_headers):
    resp = client.post(
        "/api/datasets",
        headers=auth_headers,
        files={
            "expression": ("e.csv", b"gene,s1,s2\nG1,1,abc\n", "text/csv"),
            "annotation": ("a.csv", b"sample,group\ns1,A\ns2,B\n", "text/csv"),
        },
    )
    assert resp.status_code == 422
    assert "Non-numeric" in resp.json()["detail"]


def test_unknown_reference_group_returns_422(client, auth_headers, sim_files):
    dataset = _upload_dataset(client, auth_headers, sim_files).json()
    resp = client.post(
        "/api/analyses",
        headers=auth_headers,
        json={"dataset_id": dataset["id"], "reference_group": "nope"},
    )
    assert resp.status_code == 422


def test_unknown_dataset_returns_404(client, auth_headers):
    resp = client.post("/api/analyses", headers=auth_headers, json={"dataset_id": "missing"})
    assert resp.status_code == 404


def test_results_of_unknown_analysis_returns_404(client, auth_headers):
    resp = client.get("/api/analyses/missing/results", headers=auth_headers)
    assert resp.status_code == 404
