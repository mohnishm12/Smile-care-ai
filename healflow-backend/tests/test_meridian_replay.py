"""THE milestone test (implementation directive):

  A deterministic ranked decision list reconstructed entirely from replayed
  events. Delete every projector's state, replay every event, the Brief must
  become identical.

Also asserts: hash-chain integrity, and that every Brief item answers the
nine traceability questions.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

from src.config import get_settings
from src.meridian.brief import default_registry, generate_brief
from src.meridian.store import append, verify_chain

settings = get_settings()

TENANT = "clinic-test-kernel"
T0 = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)

# Kernel DDL bootstrap for the test database (conftest's create_all only knows
# ORM models; kernel tables live in migration 0004). Mirrors 0004 exactly.
KERNEL_DDL = """
CREATE TABLE IF NOT EXISTS healflow.meridian_events (
    event_id uuid PRIMARY KEY,
    stream_id varchar(128) NOT NULL,
    seq bigint NOT NULL,
    tenant_id varchar(64) NOT NULL,
    type varchar(96) NOT NULL,
    v integer NOT NULL DEFAULT 1,
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    actor jsonb NOT NULL,
    payload jsonb NOT NULL,
    causation_id uuid,
    correlation_id uuid,
    prev_hash varchar(64) NOT NULL DEFAULT '',
    hash varchar(64) NOT NULL,
    CONSTRAINT uq_meridian_stream_seq UNIQUE (stream_id, seq)
);
CREATE INDEX IF NOT EXISTS ix_meridian_events_replay
    ON healflow.meridian_events (recorded_at, stream_id, seq);
CREATE TABLE IF NOT EXISTS healflow.meridian_checkpoints (
    projector varchar(96) PRIMARY KEY,
    last_event_id uuid NOT NULL,
    last_seq_key varchar(256) NOT NULL
);
CREATE TABLE IF NOT EXISTS healflow.meridian_applied (
    projector varchar(96) NOT NULL,
    event_id uuid NOT NULL,
    PRIMARY KEY (projector, event_id)
);
CREATE TABLE IF NOT EXISTS healflow.rm_recovery (
    stream_id varchar(128) PRIMARY KEY,
    tenant_id varchar(64) NOT NULL,
    episode varchar(128) NOT NULL,
    score integer NOT NULL,
    components jsonb NOT NULL,
    evidence jsonb NOT NULL,
    engine_version varchar(32) NOT NULL,
    computed_from_seq bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS healflow.rm_risk (
    stream_id varchar(128) NOT NULL,
    hazard varchar(64) NOT NULL,
    tenant_id varchar(64) NOT NULL,
    level varchar(16) NOT NULL,
    basis jsonb NOT NULL,
    rules_version varchar(32) NOT NULL,
    PRIMARY KEY (stream_id, hazard)
);
CREATE TABLE IF NOT EXISTS healflow.rm_trust (
    tenant_id varchar(64) NOT NULL,
    action_class varchar(96) NOT NULL,
    outcomes jsonb NOT NULL,
    engine_version varchar(32) NOT NULL,
    PRIMARY KEY (tenant_id, action_class)
);
CREATE TABLE IF NOT EXISTS healflow.rm_decisions (
    decision_id varchar(160) PRIMARY KEY,
    tenant_id varchar(64) NOT NULL,
    as_of timestamptz NOT NULL,
    rank integer NOT NULL,
    priority numeric(18,4) NOT NULL,
    body jsonb NOT NULL
);
"""


def _t(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


@pytest.fixture
def conn():
    engine = create_engine(settings.database_sync_url)
    with engine.begin() as connection:
        for statement in KERNEL_DDL.split(";"):
            if statement.strip():
                connection.execute(text(statement))
        for table in (
            "rm_decisions", "rm_trust", "rm_risk", "rm_recovery",
            "meridian_applied", "meridian_checkpoints",
        ):
            connection.execute(text(f"DELETE FROM healflow.{table}"))
        connection.execute(
            text("DELETE FROM healflow.meridian_events WHERE tenant_id = :t"),
            {"t": TENANT},
        )
        yield connection
    engine.dispose()


def seed_stream(conn) -> tuple[str, str]:
    """Two patients: one deteriorating post-extraction, one with an
    unacknowledged critical escalation. Plus ledger history for trust."""
    kittur = f"patient-{uuid.uuid4().hex[:8]}-{TENANT}"
    meera = f"patient-{uuid.uuid4().hex[:8]}-{TENANT}"
    actor_rt = {"kind": "runtime", "id": "meridian"}
    actor_pt = {"kind": "patient", "id": "self"}

    def emit(stream, type_, payload, at, actor=actor_rt):
        return append(
            conn, stream_id=stream, tenant_id=TENANT, type_=type_,
            payload=payload, actor=actor, occurred_at=at, recorded_at=at,
        )

    # Kittur: extraction follow-up, pain rising 3 → 6, one missed dose.
    emit(kittur, "FollowUpPlanStarted", {"treatment": "extraction", "days": 7}, _t(0))
    emit(kittur, "CheckinAsked", {"day": 1}, _t(2))
    emit(kittur, "CheckinAnswered", {"day": 1, "pain": 3, "symptoms": {}}, _t(3), actor_pt)
    emit(kittur, "DoseReminded", {"medication": "amoxicillin"}, _t(12))
    emit(kittur, "DoseMissed", {"medication": "amoxicillin"}, _t(13))
    emit(kittur, "CheckinAsked", {"day": 2}, _t(26))
    emit(
        kittur, "CheckinAnswered",
        {"day": 2, "pain": 6, "symptoms": {"swelling": True}}, _t(27), actor_pt,
    )

    # Meera: message then critical escalation, unacknowledged.
    emit(meera, "MessageReceived", {"body": "heavy bleeding"}, _t(30), actor_pt)
    emit(meera, "EscalationRaised", {"severity": "critical", "reason": "heavy bleeding"}, _t(30.01))

    # Ledger history: scheduling.book earns strong record (45 clean approvals).
    ledger = f"ledger-{TENANT}"
    for i in range(45):
        proposal = emit(
            ledger, "ActionProposed",
            {"action_class": "scheduling.book", "action": "book_review_appointment"},
            _t(-500 + i),
        )
        emit(
            ledger, "ActionApproved",
            {"action_class": "scheduling.book", "edited": False,
             "action_event_id": str(proposal.event_id)},
            _t(-500 + i + 0.1),
        )
    return kittur, meera


def project_and_brief(conn) -> list[dict]:
    registry = default_registry()
    registry.replay_all(conn, tenant_id=None)
    return generate_brief(conn, tenant_id=TENANT, as_of=_t(48))


def canonical(decisions: list[dict]) -> str:
    return json.dumps(decisions, sort_keys=True, default=str)


def test_replay_identity(conn):
    kittur, meera = seed_stream(conn)

    first = project_and_brief(conn)
    assert first, "brief must not be empty for a deteriorating patient"
    snapshot = canonical(first)

    # Delete every projector. Replay every event. Identical brief — the law.
    second = project_and_brief(conn)
    assert canonical(second) == snapshot

    # And a third time, to catch order-dependence flukes.
    third = project_and_brief(conn)
    assert canonical(third) == snapshot


def test_hash_chain_integrity(conn):
    kittur, meera = seed_stream(conn)
    assert verify_chain(conn, kittur)
    assert verify_chain(conn, meera)


def test_ranking_and_traceability(conn):
    kittur, meera = seed_stream(conn)
    decisions = project_and_brief(conn)

    # Unacknowledged critical escalation ranks absolutely first (hard law).
    top = decisions[0]
    assert top["hazard"] == "unacknowledged_escalation"
    assert top["level"] == "critical"
    assert top["stream_id"] == meera
    assert top["ranking"]["absolute_first"] is True

    # Kittur's deterioration is present with recovery context.
    kittur_items = [d for d in decisions if d["stream_id"] == kittur]
    assert any(d["hazard"] == "deterioration" for d in kittur_items)
    deterioration = next(d for d in kittur_items if d["hazard"] == "deterioration")
    assert deterioration["recovery_score"] is not None
    assert deterioration["recovery_score"] < 100

    # Trust earned: scheduling.book has 35 clean approvals → DRAFT tier
    # (n>=30, LB>=0.90; not ACT: n<100).
    assert deterioration["trust"]["tier"] == "DRAFT"

    # Every item answers the nine questions (implementation directive).
    for decision in decisions:
        assert decision["summary"]                      # why am I here
        assert decision["evidence"]                     # what evidence produced me
        assert all(isinstance(e, str) for e in decision["evidence"])  # event ids
        assert decision["rules_fired"]                  # which rules fired
        assert decision["model_id"]                     # which model participated
        assert 0.0 <= decision["confidence"] <= 1.0     # which confidence
        assert decision["trust"]["tier"] in ("ASK", "DRAFT", "ACT")  # trust tier
        assert decision["recommended_action"]["action"]  # recommended action
        assert decision["if_ignored"]                   # what happens if ignored
        assert decision["ranking"]["version"]           # traceable ranking
