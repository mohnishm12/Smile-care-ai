from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings

settings = get_settings()

# Celery workers use a plain sync engine (psycopg2) — async engines don't
# play well with Celery's prefork worker pool.
sync_engine = create_engine(settings.database_sync_url, pool_pre_ping=True, future=True)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


@contextmanager
def get_sync_db() -> Iterator[Session]:
    session = SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()
