"""seed AI assistant user

Revision ID: 0002
Revises: 0001
Create Date: 2026-01-01 00:00:01

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed identity used by src/ai.py — replies are authored by this user.
ASSISTANT_USER_ID = "00000000-0000-4000-8000-00000000a1a1"
ASSISTANT_EMAIL = "assistant@healflow.internal"


def upgrade() -> None:
    # Impossible-to-satisfy bcrypt hash — the assistant can never log in.
    op.execute(
        f"""
        INSERT INTO healflow.users (id, email, hashed_password, full_name, role, is_active)
        VALUES (
            '{ASSISTANT_USER_ID}',
            '{ASSISTANT_EMAIL}',
            '!disabled-login',
            'HealFlow Assistant',
            'staff',
            true
        )
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM healflow.users WHERE id = '{ASSISTANT_USER_ID}'")
