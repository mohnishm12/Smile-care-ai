import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.models.message import MessageChannel


class MessageCreate(BaseModel):
    channel: MessageChannel = MessageChannel.CHAT
    body: str = Field(min_length=1, max_length=8000)


class MessageResponse(BaseModel):
    id: uuid.UUID
    sender_id: uuid.UUID
    conversation_user_id: uuid.UUID | None = None
    channel: MessageChannel
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}
