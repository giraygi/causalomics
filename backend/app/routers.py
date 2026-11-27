import csv
import io
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import analysis as de
from app import schemas, services
from app.auth import create_access_token, require_user, verify_credentials
from app.config import Settings, get_settings
from app.db import get_session
from app.edges_io import load_edges
from app.models import Analysis, Dataset, EdgeList, GeneResult

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

public = APIRouter()
protected = APIRouter(dependencies=[Depends(require_user)])


# --------------------------------------------------------------------------- #
# Public
# --------------------------------------------------------------------------- #
@public.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok"}


@public.post("/auth/login", response_model=schemas.Token, tags=["auth"])
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], settings: SettingsDep):
    if not verify_credentials(form.username, form.password, settings):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    return schemas.Token(access_token=create_access_token(form.username, settings))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _read_upload(upload: UploadFile, settings: Settings) -> str:
    data = await upload.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"{upload.filename} is larger than {settings.max_upload_mb} MB",
        )
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"{upload.filename} is not UTF-8 text"
        ) from None


def _get_or_404(session: Session, model, obj_id: str):
    obj = session.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} {obj_id} not found")
    return obj


# --------------------------------------------------------------------------- #
# Datasets
# --------------------------------------------------------------------------- #
@protected.post(
    "/datasets",
    response_model=schemas.DatasetOut,
    status_code=status.HTTP_201_CREATED,
    tags=["datasets"],
)
async def upload_dataset(
    session: SessionDep,
    settings: SettingsDep,
    expression: Annotated[UploadFile, File(description="Genes as rows, samples as columns")],
    annotation: Annotated[UploadFile, File(description="Columns: sample, group")],
    name: Annotated[str | None, Form()] = None,
):
    expression_csv = await _read_upload(expression, settings)
    annotation_csv = await _read_upload(annotation, settings)
    try:
        expr = de.load_expression(expression_csv.encode())
        ann = de.load_annotation(annotation_csv.encode())
        design = de.resolve_design(expr, ann)
    except de.AnalysisInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None

    dataset = Dataset(
        name=name or expression.filename or "dataset",
        expression_csv=expression_csv,
        annotation_csv=annotation_csv,
        n_genes=expr.shape[0],
        n_samples=expr.shape[1],
        groups={
            design.reference: len(design.reference_samples),
            design.comparison: len(design.comparison_samples),
        },
    )
    session.add(dataset)
    session.commit()
    return dataset


@protected.get("/datasets", response_model=list[schemas.DatasetOut], tags=["datasets"])
def list_datasets(session: SessionDep):
    return session.scalars(select(Dataset).order_by(Dataset.created_at.desc())).all()


@protected.get("/datasets/{dataset_id}", response_model=schemas.DatasetOut, tags=["datasets"])
def get_dataset(dataset_id: str, session: SessionDep):
    return _get_or_404(session, Dataset, dataset_id)


# --------------------------------------------------------------------------- #
# Edge lists
# --------------------------------------------------------------------------- #
@protected.post(
    "/edges",
    response_model=schemas.EdgeListOut,
    status_code=status.HTTP_201_CREATED,
    tags=["network"],
)
async def upload_edges(
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="Columns: gene_a, gene_b[, score]")],
    name: Annotated[str | None, Form()] = None,
    analysis_id: Annotated[str | None, Form()] = None,
):
    text = await _read_upload(file, settings)
    try:
        edges_df = load_edges(text.encode())
    except de.AnalysisInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    if analysis_id is not None:
        _get_or_404(session, Analysis, analysis_id)
    return services.store_edge_list(
        session, name or file.filename or "edges", edges_df, analysis_id=analysis_id
    )


@protected.get("/edges", response_model=list[schemas.EdgeListOut], tags=["network"])
def list_edge_lists(session: SessionDep, analysis_id: str | None = None):
    query = select(EdgeList).order_by(EdgeList.created_at.desc())
    if analysis_id is not None:
        _get_or_404(session, Analysis, analysis_id)
        query = query.where(
            or_(EdgeList.analysis_id == analysis_id, EdgeList.analysis_id.is_(None))
        )
    return session.scalars(query).all()


# --------------------------------------------------------------------------- #
# Analyses
# --------------------------------------------------------------------------- #
@protected.post(
    "/analyses",
    response_model=schemas.AnalysisOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["analyses"],
)
def start_analysis(body: schemas.AnalysisCreate, session: SessionDep, background: BackgroundTasks):
    dataset = _get_or_404(session, Dataset, body.dataset_id)
    if body.reference_group is not None and body.reference_group not in dataset.groups:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"reference_group must be one of: {', '.join(dataset.groups)}",
        )
    job = Analysis(
        dataset_id=dataset.id,
        reference_group=body.reference_group,
        log_transform=body.log_transform,
    )
    session.add(job)
    session.commit()
    # Runs after the response is sent. For long jobs / many users: a task queue (e.g. Celery/RQ).
    background.add_task(services.run_analysis, job.id)
    return job


@protected.get("/analyses", response_model=list[schemas.AnalysisOut], tags=["analyses"])
def list_analyses(session: SessionDep, dataset_id: str | None = None):
    query = select(Analysis).order_by(Analysis.created_at.desc())
    if dataset_id:
        query = query.where(Analysis.dataset_id == dataset_id)
    return session.scalars(query).all()


@protected.get("/analyses/{analysis_id}", response_model=schemas.AnalysisOut, tags=["analyses"])
def get_analysis(analysis_id: str, session: SessionDep):
    return _get_or_404(session, Analysis, analysis_id)


def _finished_analysis(session: Session, analysis_id: str) -> Analysis:
    job = _get_or_404(session, Analysis, analysis_id)
    if job.status != "done":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Analysis is '{job.status}'; results are not available"
        )
    return job


@protected.get(
    "/analyses/{analysis_id}/results",
    response_model=list[schemas.GeneResultOut],
    tags=["analyses"],
)
def get_results(
    analysis_id: str,
    session: SessionDep,
    format: Annotated[str, Query(pattern="^(json|csv)$")] = "json",
):
    _finished_analysis(session, analysis_id)
    rows = session.scalars(
        select(GeneResult).where(GeneResult.analysis_id == analysis_id).order_by(GeneResult.id)
    ).all()
    if format == "json":
        return rows

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    fields = list(schemas.GeneResultOut.model_fields)
    writer.writerow(fields)
    for row in rows:
        writer.writerow(["" if getattr(row, f) is None else getattr(row, f) for f in fields])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="results_{analysis_id}.csv"'},
    )


@protected.get(
    "/analyses/{analysis_id}/network", response_model=schemas.NetworkOut, tags=["network"]
)
def get_network(
    analysis_id: str,
    session: SessionDep,
    edge_list_id: str,
    padj: Annotated[float, Query(gt=0, le=1)] = 0.05,
    min_abs_lfc: Annotated[float, Query(ge=0)] = 1.0,
):
    _finished_analysis(session, analysis_id)
    edge_list = _get_or_404(session, EdgeList, edge_list_id)
    if edge_list.analysis_id not in (None, analysis_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Edge list not found for this analysis")
    return services.build_network(session, analysis_id, edge_list_id, padj, min_abs_lfc)
