from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime
    n_genes: int
    n_samples: int
    groups: dict[str, int]


class EdgeListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime
    n_edges: int


class AnalysisCreate(BaseModel):
    dataset_id: str
    reference_group: str | None = Field(
        default=None, description="Group used as baseline; log2FC = comparison - reference."
    )
    log_transform: bool = Field(
        default=True, description="Apply log2(x+1). Disable if values are already log-scale."
    )


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    status: Literal["queued", "running", "done", "failed"]
    error: str | None
    reference_group: str | None
    comparison_group: str | None
    log_transform: bool
    created_at: datetime
    finished_at: datetime | None


class GeneResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gene: str
    mean_reference: float
    mean_comparison: float
    log2_fold_change: float
    t_statistic: float | None
    p_value: float | None
    p_adjusted: float | None


class NetworkNode(BaseModel):
    id: str
    log2_fold_change: float
    p_adjusted: float | None


class NetworkEdge(BaseModel):
    source: str
    target: str
    score: float | None


class NetworkOut(BaseModel):
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]
    n_significant: int
    max_abs_log2_fold_change: float
