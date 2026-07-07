"""initial schema — users, messages

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types explicitly, then reference them with create_type=False
    # in the column definitions — otherwise create_table() implicitly issues a
    # second CREATE TYPE and fails with DuplicateObjectError.
    postgresql.ENUM(
        "admin", "clinic_admin", "doctor", "staff", "patient",
        name="user_role", schema="healflow",
    ).create(op.get_bind(), checkfirst=True)

    postgresql.ENUM(
        "sms", "email", "whatsapp", "chat",
        name="message_channel", schema="healflow",
    ).create(op.get_bind(), checkfirst=True)

    user_role = postgresql.ENUM(
        "admin", "clinic_admin", "doctor", "staff", "patient",
        name="user_role", schema="healflow", create_type=False,
    )
    message_channel = postgresql.ENUM(
        "sms", "email", "whatsapp", "chat",
        name="message_channel", schema="healflow", create_type=False,
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column(
            "role", user_role, nullable=False, server_default="patient"
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="healflow",
    )
    op.create_index("ix_healflow_users_email", "users", ["email"], schema="healflow")

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sender_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("healflow.users.id"),
            nullable=False,
        ),
        sa.Column(
            "channel", message_channel, nullable=False, server_default="chat"
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="healflow",
    )


def downgrade() -> None:
    op.drop_table("messages", schema="healflow")
    op.drop_table("users", schema="healflow")
    postgresql.ENUM(name="message_channel", schema="healflow").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="user_role", schema="healflow").drop(op.get_bind(), checkfirst=True)
