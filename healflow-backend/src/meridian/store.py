"""L1 — Clinical Event Store.

Append-only, per-stream sequenced, hash-chained. The only write path is
`append`. Events are never mutated or deleted (constitution #46/#47).
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class Event:
    """The envelope (architecture §3.1). Immutable by construction."""

    event_id: uuid.UUID
    stream_id: str
    seq: int
    tenant_id: str
    type: str
    v: int
    occurred_at: datetime
    recorded_at: datetime
    actor: dict[str, Any]
    payload: dict[str, Any]
    causation_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None
    prev_hash: str = ""
    hash: str = field(default="")


def _canonical(event: Event) -> bytes:
    body = {
        "event_id": str(event.event_id),
        "stream_id": event.stream_id,
        "seq": event.seq,
        "tenant_id": event.tenant_id,
        "type": event.type,
        "v": event.v,
        "occurred_at": event.occurred_at.isoformat(),
        "actor": event.actor,
        "payload": event.payload,
        "prev_hash": event.prev_hash,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def chain_hash(event: Event) -> str:
    return hashlib.sha256(_canonical(event)).hexdigest()


class ConcurrencyError(Exception):
    """expected_seq did not match the stream head."""


def append(
    conn: Connection,
    *,
    stream_id: str,
    tenant_id: str,
    type_: str,
    payload: dict[str, Any],
    actor: dict[str, Any],
    occurred_at: datetime,
    recorded_at: datetime,
    expected_seq: int | None = None,
    v: int = 1,
    causation_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
) -> Event:
    """Append one event with optimistic concurrency and hash chaining.

    `recorded_at` is explicit (no wall clock in the kernel) so tests and
    replays are deterministic; the API layer passes real time.
    """
    head = conn.execute(
        text(
            "SELECT seq, hash FROM healflow.meridian_events "
            "WHERE stream_id = :sid ORDER BY seq DESC LIMIT 1"
        ),
        {"sid": stream_id},
    ).first()

    head_seq = head[0] if head else 0
    prev_hash = head[1] if head else ""
    if expected_seq is not None and expected_seq != head_seq:
        raise ConcurrencyError(f"{stream_id}: expected {expected_seq}, head is {head_seq}")

    event = Event(
        event_id=uuid.uuid4(),
        stream_id=stream_id,
        seq=head_seq + 1,
        tenant_id=tenant_id,
        type=type_,
        v=v,
        occurred_at=occurred_at,
        recorded_at=recorded_at,
        actor=actor,
        payload=payload,
        causation_id=causation_id,
        correlation_id=correlation_id,
        prev_hash=prev_hash,
    )
    hashed = Event(**{**event.__dict__, "hash": chain_hash(event)})

    conn.execute(
        text(
            "INSERT INTO healflow.meridian_events "
            "(event_id, stream_id, seq, tenant_id, type, v, occurred_at, recorded_at,"
            " actor, payload, causation_id, correlation_id, prev_hash, hash) "
            "VALUES (:event_id, :stream_id, :seq, :tenant_id, :type, :v, :occurred_at,"
            " :recorded_at, CAST(:actor AS jsonb), CAST(:payload AS jsonb),"
            " :causation_id, :correlation_id, :prev_hash, :hash)"
        ),
        {
            "event_id": str(hashed.event_id),
            "stream_id": hashed.stream_id,
            "seq": hashed.seq,
            "tenant_id": hashed.tenant_id,
            "type": hashed.type,
            "v": hashed.v,
            "occurred_at": hashed.occurred_at,
            "recorded_at": hashed.recorded_at,
            "actor": json.dumps(hashed.actor),
            "payload": json.dumps(hashed.payload),
            "causation_id": str(hashed.causation_id) if hashed.causation_id else None,
            "correlation_id": str(hashed.correlation_id) if hashed.correlation_id else None,
            "prev_hash": hashed.prev_hash,
            "hash": hashed.hash,
        },
    )
    return hashed


def _row_to_event(row: Any) -> Event:
    return Event(
        event_id=uuid.UUID(str(row.event_id)),
        stream_id=row.stream_id,
        seq=row.seq,
        tenant_id=row.tenant_id,
        type=row.type,
        v=row.v,
        occurred_at=row.occurred_at,
        recorded_at=row.recorded_at,
        actor=row.actor,
        payload=row.payload,
        causation_id=uuid.UUID(str(row.causation_id)) if row.causation_id else None,
        correlation_id=uuid.UUID(str(row.correlation_id)) if row.correlation_id else None,
        prev_hash=row.prev_hash,
        hash=row.hash,
    )


def read_stream(conn: Connection, stream_id: str) -> list[Event]:
    rows = conn.execute(
        text(
            "SELECT * FROM healflow.meridian_events "
            "WHERE stream_id = :sid ORDER BY seq"
        ),
        {"sid": stream_id},
    ).fetchall()
    return [_row_to_event(r) for r in rows]


def read_all(conn: Connection, tenant_id: str | None = None) -> list[Event]:
    """Global order for replay: (recorded_at, stream_id, seq) — deterministic."""
    where = "WHERE tenant_id = :tid" if tenant_id else ""
    rows = conn.execute(
        text(
            f"SELECT * FROM healflow.meridian_events {where} "
            "ORDER BY recorded_at, stream_id, seq"
        ),
        {"tid": tenant_id} if tenant_id else {},
    ).fetchall()
    return [_row_to_event(r) for r in rows]


def verify_chain(conn: Connection, stream_id: str) -> bool:
    """Recompute the hash chain; True iff untampered."""
    prev = ""
    for event in read_stream(conn, stream_id):
        expected = chain_hash(
            Event(**{**event.__dict__, "prev_hash": prev, "hash": ""})
        )
        if event.prev_hash != prev or event.hash != expected:
            return False
        prev = event.hash
    return True
