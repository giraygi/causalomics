"""Simulated input data: expression table, sample annotation and gene-gene edge list.

Used by the importer service, the tests and `python -m app.simulate <outdir>`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class SimulatedData:
    expression: pd.DataFrame  # genes x samples, linear scale
    annotation: pd.DataFrame  # columns: sample, group
    edges: pd.DataFrame  # columns: gene_a, gene_b, score
    true_up: list[str]
    true_down: list[str]


def simulate(
    n_genes: int = 200,
    n_per_group: int = 6,
    n_up: int = 10,
    n_down: int = 10,
    effect_log2: float = 2.0,
    noise_sd: float = 0.4,
    n_random_edges: int = 250,
    seed: int = 42,
) -> SimulatedData:
    rng = np.random.default_rng(seed)
    genes = [f"GENE{i:03d}" for i in range(1, n_genes + 1)]
    control = [f"ctrl_{i}" for i in range(1, n_per_group + 1)]
    treated = [f"treat_{i}" for i in range(1, n_per_group + 1)]

    # Baseline log2 expression per gene, then sample-level noise.
    baseline = rng.uniform(4.0, 11.0, size=n_genes)
    log_expr = baseline[:, None] + rng.normal(0.0, noise_sd, size=(n_genes, 2 * n_per_group))

    de_idx = rng.choice(n_genes, size=n_up + n_down, replace=False)
    up_idx, down_idx = de_idx[:n_up], de_idx[n_up:]
    log_expr[up_idx, n_per_group:] += effect_log2
    log_expr[down_idx, n_per_group:] -= effect_log2

    linear = np.clip(2.0**log_expr - 1.0, 0.0, None).round(3)
    expression = pd.DataFrame(linear, index=pd.Index(genes, name="gene"), columns=control + treated)
    annotation = pd.DataFrame(
        {
            "sample": control + treated,
            "group": ["control"] * n_per_group + ["treated"] * n_per_group,
        }
    )

    # Edge list: a random background network plus a denser module among the DE genes,
    # so the network view shows connected significant genes.
    edges: set[tuple[str, str]] = set()
    while len(edges) < n_random_edges:
        a, b = rng.choice(n_genes, size=2, replace=False)
        edges.add(tuple(sorted((genes[a], genes[b]))))
    de_genes = [genes[i] for i in de_idx]
    for i, g in enumerate(de_genes):
        for h in rng.choice(de_genes, size=3, replace=False):
            if h != g:
                edges.add(tuple(sorted((g, h))))
        edges.add(tuple(sorted((g, de_genes[(i + 1) % len(de_genes)]))))
    edge_list = sorted(edges)
    edge_df = pd.DataFrame(edge_list, columns=["gene_a", "gene_b"])
    edge_df["score"] = rng.uniform(0.4, 0.99, size=len(edge_df)).round(3)

    return SimulatedData(
        expression=expression,
        annotation=annotation,
        edges=edge_df,
        true_up=sorted(genes[i] for i in up_idx),
        true_down=sorted(genes[i] for i in down_idx),
    )


def write_files(data: SimulatedData, outdir: Path) -> dict[str, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    paths = {
        "expression": outdir / "expression.csv",
        "annotation": outdir / "annotation.csv",
        "edges": outdir / "edges.csv",
    }
    data.expression.to_csv(paths["expression"])
    data.annotation.to_csv(paths["annotation"], index=False)
    data.edges.to_csv(paths["edges"], index=False)
    return paths


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "data/sample")
    written = write_files(simulate(), target)
    for name, path in written.items():
        print(f"{name}: {path}")
