import uuid
from datetime import datetime
from enum import Enum

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class MessageChannel(str, Enum):
    SMS = "sms"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    CHAT = "chat"


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = {"schema": "healflow"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.users.id"), nullable=False
    )
    channel: Mapped[MessageChannel] = mapped_column(
        SAEnum(
            MessageChannel,
            name="message_channel",
            schema="healflow",
            # Store enum VALUES ("chat"), not Python member names ("CHAT"),
            # matching the type created by the alembic migration.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        default=MessageChannel.CHAT,
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # 384-dim embedding for similarity search (e.g. sentence-transformers MiniLM).
    # Nullable — populated asynchronously by a Celery task, not required for send/receive.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
