"""meridian kernel — event store, checkpoints, read models

Revision ID: 0004
Revises: 0003
Create Date: 2026-01-01 00:00:03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # L1 — the clinical event store. Append-only: no UPDATE/DELETE grants in prod.
    op.create_table(
        "meridian_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stream_id", sa.String(128), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("type", sa.String(96), nullable=False),
        sa.Column("v", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", postgresql.JSONB(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("stream_id", "seq", name="uq_meridian_stream_seq"),
        schema="healflow",
    )
    op.create_index(
        "ix_meridian_events_replay",
        "meridian_events",
        ["recorded_at", "stream_id", "seq"],
        schema="healflow",
    )
    op.create_index(
        "ix_meridian_events_type", "meridian_events", ["type"], schema="healflow"
    )

    # L2 — projector bookkeeping
    op.create_table(
        "meridian_checkpoints",
        sa.Column("projector", sa.String(96), primary_key=True),
        sa.Column("last_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_seq_key", sa.String(256), nullable=False),
        schema="healflow",
    )
    op.create_table(
        "meridian_applied",
        sa.Column("projector", sa.String(96), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("projector", "event_id"),
        schema="healflow",
    )

    # L3 — read models (disposable; owned by exactly one projector each)
    op.create_table(
        "rm_recovery",
        sa.Column("stream_id", sa.String(128), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("episode", sa.String(128), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("components", postgresql.JSONB(), nullable=False),  # [{kind, delta, evidence:[event_id]}]
        sa.Column("evidence", postgresql.JSONB(), nullable=False),  # all contributing event ids
        sa.Column("engine_version", sa.String(32), nullable=False),
        sa.Column("computed_from_seq", sa.BigInteger(), nullable=False),
        schema="healflow",
    )
    op.create_table(
        "rm_risk",
        sa.Column("stream_id", sa.String(128), nullable=False),
        sa.Column("hazard", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("level", sa.String(16), nullable=False),  # none|watch|high|critical
        sa.Column("basis", postgresql.JSONB(), nullable=False),  # [{rule, evidence:[event_id]}]
        sa.Column("rules_version", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("stream_id", "hazard"),
        schema="healflow",
    )
    op.create_table(
        "rm_trust",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("action_class", sa.String(96), nullable=False),
        sa.Column("outcomes", postgresql.JSONB(), nullable=False),  # [{kind, at, evidence}]
        sa.Column("engine_version", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "action_class"),
        schema="healflow",
    )
    op.create_table(
        "rm_decisions",
        sa.Column("decision_id", sa.String(160), primary_key=True),  # deterministic key
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Numeric(18, 4), nullable=False),
        sa.Column("body", postgresql.JSONB(), nullable=False),  # full traceable item
        schema="healflow",
    )


def downgrade() -> None:
    for table in (
        "rm_decisions", "rm_trust", "rm_risk", "rm_recovery",
        "meridian_applied", "meridian_checkpoints", "meridian_events",
    ):
        op.drop_table(table, schema="healflow")
