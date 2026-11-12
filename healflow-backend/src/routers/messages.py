import asyncio
import logging
import uuid

import jwt
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai import ASSISTANT_EMAIL, ASSISTANT_USER_ID, generate_agent_reply
from src.config import get_settings
from src.database import async_session_maker, get_db
from src.deps import get_current_user
from src.models.care import PatientProfile
from src.models.message import Message, MessageChannel
from src.models.user import User, UserRole
from src.schemas.message import MessageCreate, MessageResponse
from src.security import decode_token
from src.tasks import embed_message

settings = get_settings()

router = APIRouter(tags=["messages"])
logger = logging.getLogger("healflow.messages")

STAFF_ROLES = (UserRole.STAFF, UserRole.DOCTOR, UserRole.CLINIC_ADMIN, UserRole.ADMIN)


@router.get("/api/messages", response_model=list[MessageResponse])
async def list_messages(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, le=200),
    patient_id: uuid.UUID | None = Query(default=None),
) -> list[Message]:
    """Patients see ONLY their own conversation. Staff may pass patient_id
    to read a specific conversation (reception workspace uses this)."""
    query = select(Message).order_by(Message.created_at.desc()).limit(limit)
    if current_user.role in STAFF_ROLES:
        if patient_id is not None:
            query = query.where(
                or_(
                    Message.conversation_user_id == patient_id,
                    Message.sender_id == patient_id,
                )
            )
    else:
        query = query.where(
            or_(
                Message.conversation_user_id == current_user.id,
                Message.sender_id == current_user.id,
            )
        )
    result = await db.execute(query)
    return list(reversed(result.scalars().all()))


@router.post(
    "/api/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED
)
async def create_message(
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Message:
    message = Message(
        sender_id=current_user.id,
        conversation_user_id=current_user.id,
        channel=payload.channel,
        body=payload.body,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    try:
        embed_message.delay(str(message.id))
    except Exception:
        # Broker unavailable must not fail the API write — embedding is
        # best-effort async enrichment, not part of the send contract.
        logger.warning("Could not enqueue embed task for message %s", message.id, exc_info=True)

    await manager.broadcast_message(
        MessageResponse.model_validate(message).model_dump(mode="json"),
        conversation_user_id=current_user.id,
    )

    profile = await db.get(PatientProfile, current_user.id)
    ai_paused = bool(profile and profile.ai_paused)

    if (
        settings.ai_reply_enabled
        and not ai_paused
        and message.channel == MessageChannel.CHAT
        and current_user.id != ASSISTANT_USER_ID
        and current_user.role == UserRole.PATIENT
    ):
        # Fire-and-forget: the patient's message returns immediately; the
        # assistant reply arrives over the WebSocket when it's ready.
        asyncio.create_task(_send_assistant_reply(message.id))

    return message


async def _ensure_assistant_user(db: AsyncSession) -> None:
    if await db.get(User, ASSISTANT_USER_ID) is None:
        db.add(
            User(
                id=ASSISTANT_USER_ID,
                email=ASSISTANT_EMAIL,
                hashed_password="!disabled-login",
                full_name="HealFlow Assistant",
                role=UserRole.STAFF,
            )
        )
        await db.commit()


async def _send_assistant_reply(trigger_message_id: uuid.UUID) -> None:
    try:
        async with async_session_maker() as db:
            await _ensure_assistant_user(db)

            trigger = await db.get(Message, trigger_message_id)
            if trigger is None:
                return
            patient = await db.get(User, trigger.sender_id)
            if patient is None:
                return
            # Capture the id as a plain value: tool failures inside the agent
            # (e.g. double-booking IntegrityError) roll the session back and
            # expire ORM instances — patient.id would raise afterwards.
            patient_id = patient.id

            # Conversation history: this patient's thread (all senders).
            result = await db.execute(
                select(Message)
                .where(
                    or_(
                        Message.conversation_user_id == patient_id,
                        Message.sender_id == patient_id,
                    )
                )
                .order_by(Message.created_at.desc())
                .limit(12)
            )
            recent = list(reversed(result.scalars().all()))

            history = [
                {
                    "role": "user" if m.sender_id == patient_id else "assistant",
                    "content": m.body,
                }
                for m in recent
            ]
            if not history or history[-1]["role"] != "user":
                return

            reply_text = await generate_agent_reply(db, patient, history)

            reply = Message(
                sender_id=ASSISTANT_USER_ID,
                conversation_user_id=patient_id,
                channel=MessageChannel.CHAT,
                body=reply_text,
            )
            db.add(reply)
            await db.commit()
            await db.refresh(reply)

        try:
            embed_message.delay(str(reply.id))
        except Exception:
            logger.warning("Could not enqueue embed task for reply %s", reply.id, exc_info=True)

        await manager.broadcast_message(
            MessageResponse.model_validate(reply).model_dump(mode="json"),
            conversation_user_id=patient_id,
        )
    except Exception:
        # Reply generation is best-effort; never crash the event loop task.
        logger.warning(
            "Assistant reply failed for message %s", trigger_message_id, exc_info=True
        )


class ConnectionManager:
    """Identity-aware connections: patients receive only their own
    conversation; staff connections receive every conversation."""

    def __init__(self) -> None:
        self.active: dict[WebSocket, tuple[uuid.UUID, bool]] = {}

    async def connect(self, websocket: WebSocket, user_id: uuid.UUID, is_staff: bool) -> None:
        await websocket.accept()
        self.active[websocket] = (user_id, is_staff)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active.pop(websocket, None)

    async def broadcast_message(
        self, payload: dict, *, conversation_user_id: uuid.UUID | None
    ) -> None:
        stale = []
        for connection, (user_id, is_staff) in list(self.active.items()):
            if (
                not is_staff
                and conversation_user_id is not None
                and user_id != conversation_user_id
            ):
                continue
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
        user_id = await _authenticate_ws(token)
    except (jwt.PyJWTError, ValueError, KeyError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with async_session_maker() as db:
        user = await db.get(User, user_id)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket, user_id, user.role in STAFF_ROLES)
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
    current_user: User = Depends(get_current_user),
) -> Message:
    message = await db.get(Message, message_id)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    if current_user.role not in STAFF_ROLES:
        owner = message.conversation_user_id or message.sender_id
        if owner != current_user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    return message
