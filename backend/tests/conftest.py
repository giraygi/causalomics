import os

# Must be set before the app (and its engine) is imported.
# CI can point TEST_DATABASE_URL at a real PostgreSQL service.
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("APP_USERNAME", "tester")
os.environ.setdefault("APP_PASSWORD", "secret-pass")
os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-long-enough-1234567890")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as test_client:  # runs the lifespan -> creates tables
        yield test_client
    Base.metadata.drop_all(engine)


@pytest.fixture()
def auth_headers(client):
    resp = client.post(
        "/api/auth/login",
        data={"username": os.environ["APP_USERNAME"], "password": os.environ["APP_PASSWORD"]},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
