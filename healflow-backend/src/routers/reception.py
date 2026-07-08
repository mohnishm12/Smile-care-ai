"""Reception workspace API.

Staff-facing conversation console: conversation index, per-thread reads,
send-as-clinic (pauses the runtime), takeover/resume, and AI-suggested
replies (drafted, never auto-sent while paused).
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai import ASSISTANT_USER_ID, generate_agent_reply
from src.database import get_db
from src.deps import get_current_user
from src.models.care import Escalation, PatientProfile
from src.models.message import Message, MessageChannel
from src.models.user import User, UserRole
from src.routers.messages import STAFF_ROLES, manager
from src.schemas.message import MessageResponse
from src.tasks import embed_message

router = APIRouter(tags=["reception"])
logger = logging.getLogger("healflow.reception")


async def require_staff(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in STAFF_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Staff access required")
    return current_user


class ConversationSummary(BaseModel):
    patient_id: uuid.UUID
    patient_name: str
    last_message: str
    last_message_at: datetime
    last_sender_kind: str  # patient | assistant | staff
    unread_count: int
    ai_paused: bool
    high_priority: bool
    open_escalations: int


class SendBody(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class SuggestResponse(BaseModel):
    suggestion: str


@router.get("/api/reception/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
) -> list[ConversationSummary]:
    patients = (
        (
            await db.execute(
                select(User).where(User.role == UserRole.PATIENT, User.is_active)
            )
        )
        .scalars()
        .all()
    )
    summaries: list[ConversationSummary] = []
    for patient in patients:
        last = (
            await db.execute(
                select(Message)
                .where(
                    or_(
                        Message.conversation_user_id == patient.id,
                        Message.sender_id == patient.id,
                    )
                )
                .order_by(Message.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if last is None:
            continue

        profile = await db.get(PatientProfile, patient.id)
        read_watermark = profile.last_read_by_staff_at if profile else None
        unread_query = select(func.count()).select_from(Message).where(
            Message.sender_id == patient.id
        )
        if read_watermark is not None:
            unread_query = unread_query.where(Message.created_at > read_watermark)
        unread = (await db.execute(unread_query)).scalar_one()

        open_escalations = (
            await db.execute(
                select(func.count())
                .select_from(Escalation)
                .where(
                    Escalation.patient_id == patient.id,
                    Escalation.acknowledged.is_(False),
                )
            )
        ).scalar_one()

        if last.sender_id == patient.id:
            sender_kind = "patient"
        elif last.sender_id == ASSISTANT_USER_ID:
            sender_kind = "assistant"
        else:
            sender_kind = "staff"

        summaries.append(
            ConversationSummary(
                patient_id=patient.id,
                patient_name=patient.full_name,
                last_message=last.body[:160],
                last_message_at=last.created_at,
                last_sender_kind=sender_kind,
                unread_count=unread,
                ai_paused=bool(profile and profile.ai_paused),
                high_priority=bool(profile and profile.high_priority),
                open_escalations=open_escalations,
            )
        )
    summaries.sort(key=lambda s: (-s.open_escalations, s.last_message_at), reverse=False)
    summaries.sort(key=lambda s: s.last_message_at, reverse=True)
    summaries.sort(key=lambda s: s.open_escalations, reverse=True)
    return summaries


async def _get_or_create_profile(db: AsyncSession, patient: User) -> PatientProfile:
    profile = await db.get(PatientProfile, patient.id)
    if profile is None:
        profile = PatientProfile(user_id=patient.id)
        db.add(profile)
        await db.flush()
    return profile


async def _load_patient(db: AsyncSession, patient_id: uuid.UUID) -> User:
    patient = await db.get(User, patient_id)
    if patient is None or patient.role != UserRole.PATIENT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    return patient


@router.post("/api/reception/conversations/{patient_id}/read")
async def mark_read(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
) -> dict:
    patient = await _load_patient(db, patient_id)
    profile = await _get_or_create_profile(db, patient)
    profile.last_read_by_staff_at = datetime.now(UTC)
    await db.commit()
    return {"ok": True}


@router.post("/api/reception/conversations/{patient_id}/takeover")
async def takeover(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(require_staff),
) -> dict:
    patient = await _load_patient(db, patient_id)
    profile = await _get_or_create_profile(db, patient)
    profile.ai_paused = True
    await db.commit()
    logger.info("Conversation %s taken over by %s", patient_id, staff.email)
    return {"ai_paused": True}


@router.post("/api/reception/conversations/{patient_id}/resume")
async def resume_ai(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(require_staff),
) -> dict:
    patient = await _load_patient(db, patient_id)
    profile = await _get_or_create_profile(db, patient)
    profile.ai_paused = False
    await db.commit()
    logger.info("Conversation %s resumed to AI by %s", patient_id, staff.email)
    return {"ai_paused": False}


@router.post(
    "/api/reception/conversations/{patient_id}/send",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_as_clinic(
    patient_id: uuid.UUID,
    payload: SendBody,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(require_staff),
) -> Message:
    """Staff reply into a patient conversation. Sending manually pauses the
    runtime for this thread — a human has taken the wheel."""
    patient = await _load_patient(db, patient_id)
    profile = await _get_or_create_profile(db, patient)
    profile.ai_paused = True

    message = Message(
        sender_id=staff.id,
        conversation_user_id=patient.id,
        channel=MessageChannel.CHAT,
        body=payload.body,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    try:
        embed_message.delay(str(message.id))
    except Exception:
        logger.warning("Could not enqueue embed for staff message %s", message.id)

    await manager.broadcast_message(
        MessageResponse.model_validate(message).model_dump(mode="json"),
        conversation_user_id=patient.id,
    )
    return message


@router.post(
    "/api/reception/conversations/{patient_id}/suggest",
    response_model=SuggestResponse,
)
async def suggest_reply(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
) -> SuggestResponse:
    """Draft what the runtime WOULD say — shown to staff, never sent."""
    patient = await _load_patient(db, patient_id)
    result = await db.execute(
        select(Message)
        .where(
            or_(
                Message.conversation_user_id == patient.id,
                Message.sender_id == patient.id,
            )
        )
        .order_by(Message.created_at.desc())
        .limit(12)
    )
    recent = list(reversed(result.scalars().all()))
    history = [
        {
            "role": "user" if m.sender_id == patient.id else "assistant",
            "content": m.body,
        }
        for m in recent
    ]
    if not history:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No conversation yet")
    if history[-1]["role"] != "user":
        history.append({"role": "user", "content": "(no new patient message)"})
    suggestion = await generate_agent_reply(db, patient, history)
    return SuggestResponse(suggestion=suggestion)
