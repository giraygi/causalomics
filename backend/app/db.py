from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        # In-memory SQLite for tests: one shared connection across threads.
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, pool_pre_ping=True)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    # Schema is created on startup. With more time: Alembic migrations.
    from app import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("edge_lists")}
    if "analysis_id" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE edge_lists ADD COLUMN analysis_id "
                    "VARCHAR(36) REFERENCES analyses(id) ON DELETE CASCADE"
                )
            )
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_edge_lists_analysis_id "
                "ON edge_lists (analysis_id)"
            )
        )


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
