"""Business logic shared by the API routes and the background worker."""

import logging
import math
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import analysis as de
from app.db import SessionLocal
from app.models import Analysis, Edge, EdgeList, GeneResult

log = logging.getLogger(__name__)


def _none_if_nan(value: float) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return float(value)


def run_analysis(analysis_id: str) -> None:
    """Background task: compute differential expression and store per-gene results."""
    with SessionLocal() as session:
        job = session.get(Analysis, analysis_id)
        if job is None:
            return
        job.status = "running"
        session.commit()
        try:
            dataset = job.dataset
            expression = de.load_expression(dataset.expression_csv.encode())
            annotation = de.load_annotation(dataset.annotation_csv.encode())
            table, design = de.differential_expression(
                expression,
                annotation,
                reference_group=job.reference_group,
                log_transform=job.log_transform,
            )
            session.add_all(
                GeneResult(
                    analysis_id=job.id,
                    gene=row.gene,
                    mean_reference=float(row.mean_reference),
                    mean_comparison=float(row.mean_comparison),
                    log2_fold_change=float(row.log2_fold_change),
                    t_statistic=_none_if_nan(row.t_statistic),
                    p_value=_none_if_nan(row.p_value),
                    p_adjusted=_none_if_nan(row.p_adjusted),
                )
                for row in table.itertuples(index=False)
            )
            job.reference_group = design.reference
            job.comparison_group = design.comparison
            job.status = "done"
        except de.AnalysisInputError as exc:
            job.status = "failed"
            job.error = str(exc)
        except Exception:  # pragma: no cover - unexpected errors are logged, not leaked
            log.exception("Analysis %s failed", analysis_id)
            job.status = "failed"
            job.error = "Unexpected error during analysis; see server logs."
        job.finished_at = datetime.now(timezone.utc)
        session.commit()


def build_network(
    session: Session,
    analysis_id: str,
    edge_list_id: str,
    padj_threshold: float,
    min_abs_lfc: float,
) -> dict:
    """Significant genes as nodes; edges from the edge list between significant genes only."""
    results = session.scalars(
        select(GeneResult).where(
            GeneResult.analysis_id == analysis_id,
            GeneResult.p_adjusted.is_not(None),
            GeneResult.p_adjusted < padj_threshold,
        )
    ).all()
    significant = {r.gene: r for r in results if abs(r.log2_fold_change) >= min_abs_lfc}

    edges = []
    if significant:
        genes = list(significant)
        rows = session.scalars(
            select(Edge).where(
                Edge.edge_list_id == edge_list_id,
                or_(Edge.gene_a.in_(genes), Edge.gene_b.in_(genes)),
            )
        ).all()
        edges = [
            {"source": e.gene_a, "target": e.gene_b, "score": e.score}
            for e in rows
            if e.gene_a in significant and e.gene_b in significant
        ]

    nodes = [
        {"id": g, "log2_fold_change": r.log2_fold_change, "p_adjusted": r.p_adjusted}
        for g, r in sorted(significant.items())
    ]
    max_abs = max((abs(n["log2_fold_change"]) for n in nodes), default=0.0)
    return {
        "nodes": nodes,
        "edges": edges,
        "n_significant": len(nodes),
        "max_abs_log2_fold_change": max_abs,
    }


def store_edge_list(session: Session, name: str, edges_df) -> EdgeList:
    edge_list = EdgeList(name=name, n_edges=len(edges_df))
    session.add(edge_list)
    session.flush()
    session.add_all(
        Edge(
            edge_list_id=edge_list.id,
            gene_a=row.gene_a,
            gene_b=row.gene_b,
            score=_none_if_nan(row.score),
        )
        for row in edges_df.itertuples(index=False)
    )
    session.commit()
    return edge_list
