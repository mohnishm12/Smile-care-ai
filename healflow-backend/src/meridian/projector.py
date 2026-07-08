"""L2 — Projector framework.

A projector is a pure, idempotent fold: apply(conn, event) writing ONLY to the
read models it owns. reset() drops its state entirely; replay() reconstructs
it from the stream. CI's replay-identity test is the law here (E3).
"""

from abc import ABC, abstractmethod

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.meridian.store import Event, read_all


class Projector(ABC):
    """Base for all projectors and projection-time engines."""

    #: unique name, used as the checkpoint key
    name: str
    #: event types this projector folds; others are skipped
    handles: frozenset[str]
    #: rm_* tables owned exclusively by this projector
    owned_tables: tuple[str, ...]

    @abstractmethod
    def apply(self, conn: Connection, event: Event) -> None: ...

    def reset(self, conn: Connection) -> None:
        for table in self.owned_tables:
            conn.execute(text(f"DELETE FROM healflow.{table}"))
        conn.execute(
            text("DELETE FROM healflow.meridian_checkpoints WHERE projector = :p"),
            {"p": self.name},
        )

    def checkpoint(self, conn: Connection, event: Event) -> None:
        conn.execute(
            text(
                "INSERT INTO healflow.meridian_checkpoints "
                "(projector, last_event_id, last_seq_key) "
                "VALUES (:p, :eid, :key) "
                "ON CONFLICT (projector) DO UPDATE "
                "SET last_event_id = :eid, last_seq_key = :key"
            ),
            {
                "p": self.name,
                "eid": str(event.event_id),
                "key": f"{event.recorded_at.isoformat()}|{event.stream_id}|{event.seq}",
            },
        )

    def seen(self, conn: Connection, event: Event) -> bool:
        """Idempotence guard: has this event already been folded?"""
        row = conn.execute(
            text(
                "SELECT 1 FROM healflow.meridian_applied "
                "WHERE projector = :p AND event_id = :eid"
            ),
            {"p": self.name, "eid": str(event.event_id)},
        ).first()
        return row is not None

    def mark(self, conn: Connection, event: Event) -> None:
        conn.execute(
            text(
                "INSERT INTO healflow.meridian_applied (projector, event_id) "
                "VALUES (:p, :eid) ON CONFLICT DO NOTHING"
            ),
            {"p": self.name, "eid": str(event.event_id)},
        )

    def reset_applied(self, conn: Connection) -> None:
        conn.execute(
            text("DELETE FROM healflow.meridian_applied WHERE projector = :p"),
            {"p": self.name},
        )


class Registry:
    def __init__(self) -> None:
        self._projectors: list[Projector] = []

    def register(self, projector: Projector) -> None:
        if any(p.name == projector.name for p in self._projectors):
            raise ValueError(f"duplicate projector {projector.name}")
        self._projectors.append(projector)

    @property
    def all(self) -> list[Projector]:
        return list(self._projectors)

    def dispatch(self, conn: Connection, event: Event) -> None:
        for projector in self._projectors:
            if event.type in projector.handles and not projector.seen(conn, event):
                projector.apply(conn, event)
                projector.mark(conn, event)
                projector.checkpoint(conn, event)

    def reset_all(self, conn: Connection) -> None:
        for projector in self._projectors:
            projector.reset(conn)
            projector.reset_applied(conn)

    def replay_all(self, conn: Connection, tenant_id: str | None = None) -> int:
        """Full rebuild: reset every projector, fold every event in
        deterministic global order. Returns event count."""
        self.reset_all(conn)
        events = read_all(conn, tenant_id)
        for event in events:
            self.dispatch(conn, event)
        return len(events)
