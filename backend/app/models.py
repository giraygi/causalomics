import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Dataset(Base):
    """An uploaded expression table + sample annotation (raw CSV kept for reproducibility)."""

    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expression_csv: Mapped[str] = mapped_column(Text)
    annotation_csv: Mapped[str] = mapped_column(Text)
    n_genes: Mapped[int] = mapped_column(Integer)
    n_samples: Mapped[int] = mapped_column(Integer)
    groups: Mapped[dict] = mapped_column(JSON)  # {"control": 6, "treated": 6}

    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class EdgeList(Base):
    __tablename__ = "edge_lists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    n_edges: Mapped[int] = mapped_column(Integer)

    edges: Mapped[list["Edge"]] = relationship(cascade="all, delete-orphan")


class Edge(Base):
    __tablename__ = "edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    edge_list_id: Mapped[str] = mapped_column(
        ForeignKey("edge_lists.id", ondelete="CASCADE"), index=True
    )
    gene_a: Mapped[str] = mapped_column(String(100), index=True)
    gene_b: Mapped[str] = mapped_column(String(100), index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|done|failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comparison_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    log_transform: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dataset: Mapped[Dataset] = relationship(back_populates="analyses")
    results: Mapped[list["GeneResult"]] = relationship(cascade="all, delete-orphan")


class GeneResult(Base):
    __tablename__ = "gene_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    gene: Mapped[str] = mapped_column(String(100))
    mean_reference: Mapped[float] = mapped_column(Float)
    mean_comparison: Mapped[float] = mapped_column(Float)
    log2_fold_change: Mapped[float] = mapped_column(Float)
    t_statistic: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_adjusted: Mapped[float | None] = mapped_column(Float, nullable=True)
