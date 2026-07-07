import hashlib
import uuid
from datetime import UTC, datetime

from src.celery_app import celery_app
from src.database_sync import get_sync_db
from src.models.message import Message

EMBEDDING_DIM = 384


def _placeholder_embedding(text: str) -> list[float]:
    """Deterministic pseudo-embedding derived from text hash.

    Placeholder for a real sentence-transformers/OpenAI embedding call —
    keeps the pgvector column populated and the similarity-search path
    exercisable end-to-end without bundling a model in the MVP.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    repeated = (digest * (EMBEDDING_DIM // len(digest) + 1))[:EMBEDDING_DIM]
    return [(b - 128) / 128.0 for b in repeated]


@celery_app.task(name="src.tasks.embed_message", bind=True, max_retries=3)
def embed_message(self, message_id: str) -> str:
    with get_sync_db() as db:
        message = db.get(Message, uuid.UUID(message_id))
        if message is None:
            return f"message {message_id} not found"
        message.embedding = _placeholder_embedding(message.body)
        db.commit()
    return f"embedded message {message_id}"


@celery_app.task(name="src.tasks.cleanup_expired_sessions")
def cleanup_expired_sessions() -> str:
    # Placeholder for session/refresh-token blacklist cleanup once that
    # store is added (e.g. Redis-backed revocation list).
    return f"cleanup ran at {datetime.now(UTC).isoformat()}"
