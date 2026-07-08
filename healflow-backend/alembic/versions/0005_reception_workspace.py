"""reception workspace — AI pause state on patient profiles

Revision ID: 0005
Revises: 0004
Create Date: 2026-01-01 00:00:04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "patient_profiles",
        sa.Column("ai_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="healflow",
    )
    op.add_column(
        "patient_profiles",
        sa.Column(
            "last_read_by_staff_at", sa.DateTime(timezone=True), nullable=True
        ),
        schema="healflow",
    )
    # Which patient's conversation a message belongs to. For patient-sent
    # messages this equals sender_id; for assistant/staff messages it points
    # at the patient. Required for privacy scoping and the reception index.
    op.add_column(
        "messages",
        sa.Column(
            "conversation_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        schema="healflow",
    )
    op.create_index(
        "ix_healflow_messages_conversation",
        "messages",
        ["conversation_user_id", "created_at"],
        schema="healflow",
    )
    # Backfill: patient-authored messages own their conversation. Historic
    # assistant messages predate attribution and stay NULL (accepted).
    op.execute(
        """
        UPDATE healflow.messages m
        SET conversation_user_id = m.sender_id
        FROM healflow.users u
        WHERE u.id = m.sender_id AND u.role = 'patient'
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_healflow_messages_conversation", "messages", schema="healflow"
    )
    op.drop_column("messages", "conversation_user_id", schema="healflow")
    op.drop_column("patient_profiles", "last_read_by_staff_at", schema="healflow")
    op.drop_column("patient_profiles", "ai_paused", schema="healflow")
