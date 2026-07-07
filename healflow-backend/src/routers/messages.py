import logging
import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.deps import get_current_user
from src.models.message import Message
from src.models.user import User
from src.schemas.message import MessageCreate, MessageResponse
from src.security import decode_token
from src.tasks import embed_message

router = APIRouter(tags=["messages"])
logger = logging.getLogger("healflow.messages")


@router.get("/api/messages", response_model=list[MessageResponse])
async def list_messages(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, le=200),
) -> list[Message]:
    result = await db.execute(
        select(Message).order_by(Message.created_at.desc()).limit(limit)
    )
    return list(reversed(result.scalars().all()))


@router.post("/api/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Message:
    message = Message(sender_id=current_user.id, channel=payload.channel, body=payload.body)
    db.add(message)
    await db.commit()
    await db.refresh(message)

    try:
        embed_message.delay(str(message.id))
    except Exception:
        # Broker unavailable must not fail the API write — embedding is
        # best-effort async enrichment, not part of the send contract.
        logger.warning("Could not enqueue embed task for message %s", message.id, exc_info=True)

    await manager.broadcast(MessageResponse.model_validate(message).model_dump(mode="json"))
    return message


class ConnectionManager:
    def __init__(self) -> None:
        self.active: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active.discard(websocket)

    async def broadcast(self, payload: dict) -> None:
        stale = []
        for connection in self.active:
            try:
                await connection.send_json(payload)
            except RuntimeError:
                stale.append(connection)
        for connection in stale:
            self.disconnect(connection)


manager = ConnectionManager()


async def _authenticate_ws(token: str) -> uuid.UUID:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise jwt.PyJWTError("wrong token type")
    return uuid.UUID(payload["sub"])


@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket, token: str = Query(...)) -> None:
    try:
        await _authenticate_ws(token)
    except (jwt.PyJWTError, ValueError, KeyError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; inbound chat messages go through
            # POST /api/messages (persisted + embedded), this socket is
            # push-only for broadcasting new messages to connected clients.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.get("/api/messages/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> Message:
    message = await db.get(Message, message_id)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    return message
