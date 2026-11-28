from sqlalchemy import inspect, text

from app import db


def test_init_db_migrates_existing_edge_lists_idempotently(monkeypatch):
    legacy_engine = db.make_engine("sqlite+pysqlite:///:memory:")
    with legacy_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE edge_lists ("
                "id VARCHAR(36) PRIMARY KEY, "
                "name VARCHAR(200) NOT NULL, "
                "created_at DATETIME NOT NULL, "
                "n_edges INTEGER NOT NULL)"
            )
        )

    monkeypatch.setattr(db, "engine", legacy_engine)
    db.init_db()
    db.init_db()

    columns = {column["name"] for column in inspect(legacy_engine).get_columns("edge_lists")}
    assert "analysis_id" in columns
    indexes = {index["name"] for index in inspect(legacy_engine).get_indexes("edge_lists")}
    assert "ix_edge_lists_analysis_id" in indexes

    legacy_engine.dispose()
