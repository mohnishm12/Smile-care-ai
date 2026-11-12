import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

from src.config import get_settings
from src.database import Base
from src.main import app

settings = get_settings()


@pytest.fixture(scope="session", autouse=True)
def _prepare_schema():
    sync_engine = create_engine(settings.database_sync_url)
    with sync_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS healflow"))
    Base.metadata.create_all(bind=sync_engine)
    yield
    with sync_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    sync_engine.dispose()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def unique_email() -> str:
    return f"test-{uuid.uuid4().hex[:10]}@example.com"
