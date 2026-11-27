"""Parsing of gene-gene interaction lists (simulated or exported from STRING)."""

import pandas as pd

from app.analysis import AnalysisInputError, CsvSource, _read_csv


def load_edges(source: CsvSource) -> pd.DataFrame:
    """Return a DataFrame with columns gene_a, gene_b, score (score may be NaN).

    Accepted layouts (comma, tab or semicolon separated, with header):
      * gene_a, gene_b[, score]
      * any two ID columns followed by an optional numeric score column, e.g. STRING's
        "#node1  node2 ... combined_score" export. STRING scores on a 0-1000 scale are
        rescaled to 0-1.
    Self-loops and duplicate (undirected) edges are removed.
    """
    df = _read_csv(source, dtype=str)
    if df.shape[1] < 2:
        raise AnalysisInputError("Edge list needs at least two columns (gene_a, gene_b).")

    cols = {c.strip().lower().lstrip("#"): c for c in df.columns}
    a_col = cols.get("gene_a") or cols.get("node1") or df.columns[0]
    b_col = cols.get("gene_b") or cols.get("node2") or df.columns[1]
    score_col = cols.get("score") or cols.get("combined_score")
    if score_col is None and df.shape[1] >= 3:
        candidate = df.columns[-1]
        if pd.to_numeric(df[candidate], errors="coerce").notna().all():
            score_col = candidate

    out = pd.DataFrame(
        {
            "gene_a": df[a_col].astype(str).str.strip(),
            "gene_b": df[b_col].astype(str).str.strip(),
            "score": pd.to_numeric(df[score_col], errors="coerce") if score_col else float("nan"),
        }
    )
    out = out[(out.gene_a != "") & (out.gene_b != "") & (out.gene_a != out.gene_b)]
    if out["score"].max(skipna=True) > 1:
        out["score"] = out["score"] / 1000.0

    # undirected: keep one row per unordered pair
    key = out.apply(lambda r: tuple(sorted((r.gene_a, r.gene_b))), axis=1)
    out = out.loc[~key.duplicated()].reset_index(drop=True)
    if out.empty:
        raise AnalysisInputError("Edge list contains no valid edges.")
    return out
