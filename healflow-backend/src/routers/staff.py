"""Staff dashboard endpoints: analytics, escalations, timelines, AI summaries.

Every route requires a staff-level role (doctor, staff, clinic_admin, admin).
Paths are absolute — include this router without a prefix.
"""

import uuid
from datetime import UTC, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import staff_ai
from src.ai import ASSISTANT_USER_ID
from src.database import get_db
from src.deps import get_current_user
from src.models import (
    Appointment,
    AppointmentStatus,
    Clinic,
    Doctor,
    Escalation,
    Feedback,
    FollowUpCheckin,
    FollowUpPlan,
    MedicationLog,
    MedicationSchedule,
    Message,
    User,
)
from src.models.message import MessageChannel
from src.models.user import UserRole

router = APIRouter(tags=["staff"])

STAFF_ROLES = {UserRole.DOCTOR, UserRole.STAFF, UserRole.CLINIC_ADMIN, UserRole.ADMIN}


async def require_staff(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in STAFF_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Staff access required")
    return current_user


def _today_range() -> tuple[datetime, datetime]:
    start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


async def _count(db: AsyncSession, stmt: Select) -> int:
    return int((await db.execute(stmt)).scalar_one() or 0)


def _appointment_dict(appointment: Appointment, patient_name: str, doctor_name: str) -> dict:
    return {
        "id": str(appointment.id),
        "patient_id": str(appointment.patient_id),
        "patient_name": patient_name,
        "doctor_name": doctor_name,
        "scheduled_at": appointment.scheduled_at.isoformat(),
        "status": appointment.status.value,
    }


def _escalation_dict(escalation: Escalation, patient_name: str) -> dict:
    return {
        "id": str(escalation.id),
        "patient_name": patient_name,
        "severity": escalation.severity.value,
        "reason": escalation.reason,
        "trigger_text": escalation.trigger_text,
        "created_at": escalation.created_at.isoformat(),
        "acknowledged": escalation.acknowledged,
    }


@router.get("/api/analytics/overview")
async def analytics_overview(
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
) -> dict:
    now = datetime.now(UTC)
    start, end = _today_range()
    week_ago = now - timedelta(days=7)

    todays_appointments = await _count(
        db,
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.scheduled_at >= start,
            Appointment.scheduled_at < end,
            Appointment.status != AppointmentStatus.CANCELLED,
        ),
    )
    missed_appointments = await _count(
        db,
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.scheduled_at >= start,
            Appointment.scheduled_at < end,
            Appointment.status == AppointmentStatus.NO_SHOW,
        ),
    )
    completed_today = await _count(
        db,
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.scheduled_at >= start,
            Appointment.scheduled_at < end,
            Appointment.status == AppointmentStatus.COMPLETED,
        ),
    )
    clinic = (
        (
            await db.execute(
                select(Clinic).where(Clinic.is_active).order_by(Clinic.created_at).limit(1)
            )
        )
        .scalars()
        .first()
    )

    raw_avg = (
        await db.execute(
            select(func.avg(Feedback.rating)).where(Feedback.created_at >= now - timedelta(days=30))
        )
    ).scalar_one()
    avg_rating = round(float(raw_avg), 2) if raw_avg is not None else None

    asked = await _count(
        db,
        select(func.count())
        .select_from(FollowUpCheckin)
        .where(FollowUpCheckin.asked_at >= week_ago),
    )
    responded = await _count(
        db,
        select(func.count())
        .select_from(FollowUpCheckin)
        .where(FollowUpCheckin.asked_at >= week_ago, FollowUpCheckin.responded_at.is_not(None)),
    )

    patient_messages = await _count(
        db,
        select(func.count())
        .select_from(Message)
        .join(User, User.id == Message.sender_id)
        .where(
            Message.channel == MessageChannel.CHAT,
            Message.created_at >= week_ago,
            User.role == UserRole.PATIENT,
        ),
    )
    assistant_messages = await _count(
        db,
        select(func.count())
        .select_from(Message)
        .where(
            Message.channel == MessageChannel.CHAT,
            Message.created_at >= week_ago,
            Message.sender_id == ASSISTANT_USER_ID,
        ),
    )

    open_escalations = await _count(
        db,
        select(func.count()).select_from(Escalation).where(Escalation.acknowledged.is_(False)),
    )

    return {
        "todays_appointments": todays_appointments,
        "missed_appointments": missed_appointments,
        "revenue": completed_today * (clinic.consultation_fee if clinic else 0),
        "currency": clinic.currency if clinic else "INR",
        "avg_rating": avg_rating,
        "followup_completion_rate": round(responded / asked, 3) if asked else 0.0,
        "response_rate": (
            round(min(assistant_messages / patient_messages, 1.0), 3) if patient_messages else 0.0
        ),
        "open_escalations": open_escalations,
    }


@router.get("/api/staff/escalations")
async def list_escalations(
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
) -> list[dict]:
    rows = (
        await db.execute(
            select(Escalation, User.full_name)
            .join(User, User.id == Escalation.patient_id)
            .order_by(Escalation.created_at.desc())
            .limit(50)
        )
    ).all()
    return [_escalation_dict(escalation, patient_name) for escalation, patient_name in rows]


@router.post("/api/staff/escalations/{escalation_id}/ack")
async def acknowledge_escalation(
    escalation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
) -> dict:
    escalation = await db.get(Escalation, escalation_id)
    if escalation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Escalation not found")
    escalation.acknowledged = True
    await db.commit()
    return {"id": str(escalation.id), "acknowledged": True}


@router.get("/api/staff/appointments/today")
async def todays_appointments(
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
) -> list[dict]:
    start, end = _today_range()
    rows = (
        await db.execute(
            select(Appointment, User.full_name, Doctor.name)
            .join(User, User.id == Appointment.patient_id)
            .join(Doctor, Doctor.id == Appointment.doctor_id)
            .where(Appointment.scheduled_at >= start, Appointment.scheduled_at < end)
            .order_by(Appointment.scheduled_at)
        )
    ).all()
    return [
        _appointment_dict(appointment, patient_name, doctor_name)
        for appointment, patient_name, doctor_name in rows
    ]


@router.get("/api/staff/patients/{patient_id}/timeline")
async def patient_timeline(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
) -> dict:
    patient = await db.get(User, patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    now = datetime.now(UTC)

    appointment_rows = (
        await db.execute(
            select(Appointment, Doctor.name)
            .join(Doctor, Doctor.id == Appointment.doctor_id)
            .where(Appointment.patient_id == patient_id)
            .order_by(Appointment.scheduled_at.desc())
            .limit(20)
        )
    ).all()

    checkins = (
        (
            await db.execute(
                select(FollowUpCheckin)
                .join(FollowUpPlan, FollowUpPlan.id == FollowUpCheckin.plan_id)
                .where(FollowUpPlan.patient_id == patient_id)
                .order_by(FollowUpCheckin.asked_at.desc().nulls_last())
                .limit(30)
            )
        )
        .scalars()
        .all()
    )

    medication_logs = (
        (
            await db.execute(
                select(MedicationLog)
                .join(MedicationSchedule, MedicationSchedule.id == MedicationLog.schedule_id)
                .where(MedicationSchedule.patient_id == patient_id)
            )
        )
        .scalars()
        .all()
    )
    one_hour_ago = now - timedelta(hours=1)
    taken = sum(1 for log in medication_logs if log.taken_at is not None)
    missed = sum(
        1
        for log in medication_logs
        if log.taken_at is None and log.reminded_at is not None and log.reminded_at < one_hour_ago
    )
    pending = sum(
        1
        for log in medication_logs
        if log.taken_at is None and log.reminded_at is not None and log.reminded_at >= one_hour_ago
    )

    escalations = (
        (
            await db.execute(
                select(Escalation)
                .where(Escalation.patient_id == patient_id)
                .order_by(Escalation.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )

    messages = (
        (
            await db.execute(
                select(Message)
                .where(
                    Message.channel == MessageChannel.CHAT,
                    Message.sender_id.in_([patient_id, ASSISTANT_USER_ID]),
                )
                .order_by(Message.created_at.desc())
                .limit(15)
            )
        )
        .scalars()
        .all()
    )

    return {
        "patient": {
            "id": str(patient.id),
            "full_name": patient.full_name,
            "email": patient.email,
        },
        "appointments": [
            _appointment_dict(appointment, patient.full_name, doctor_name)
            for appointment, doctor_name in appointment_rows
        ],
        "checkins": [
            {
                "day_number": checkin.day_number,
                "pain_level": checkin.pain_level,
                "symptoms": checkin.symptoms,
                "responded_at": (
                    checkin.responded_at.isoformat() if checkin.responded_at else None
                ),
            }
            for checkin in checkins
        ],
        "medication_adherence": {"taken": taken, "missed": missed, "pending": pending},
        "escalations": [
            _escalation_dict(escalation, patient.full_name) for escalation in escalations
        ],
        "recent_messages": [
            {
                "body": message.body,
                "created_at": message.created_at.isoformat(),
                "from_assistant": message.sender_id == ASSISTANT_USER_ID,
            }
            for message in reversed(messages)
        ],
    }


@router.get("/api/staff/summaries/missed")
async def missed_conversation_summaries(
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
) -> list[dict]:
    return await staff_ai.summarize_missed(db)


@router.post("/api/staff/patients/{patient_id}/visit-note-draft")
async def visit_note_draft(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
) -> dict:
    patient = await db.get(User, patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    return {"draft": await staff_ai.draft_visit_note(db, patient)}


def _no_show_suggestion(count: int) -> str:
    if count >= 3:
        return "Flag for a personal call from staff to rebook and confirm contact details"
    if count == 2:
        return "Send re-engagement offer with a discounted consultation"
    return "Send a friendly reminder with a one-tap rebooking link"


@router.get("/api/staff/no-shows")
async def no_shows(
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
) -> list[dict]:
    cutoff = datetime.now(UTC) - timedelta(days=30)
    rows = (
        await db.execute(
            select(
                Appointment.patient_id,
                User.full_name,
                func.count().label("no_show_count"),
                func.max(Appointment.scheduled_at).label("last_no_show"),
            )
            .join(User, User.id == Appointment.patient_id)
            .where(
                Appointment.status == AppointmentStatus.NO_SHOW,
                Appointment.scheduled_at >= cutoff,
            )
            .group_by(Appointment.patient_id, User.full_name)
            .order_by(func.count().desc())
        )
    ).all()
    return [
        {
            "patient_id": str(patient_id),
            "patient_name": patient_name,
            "count": count,
            "last_no_show": last_no_show.isoformat(),
            "suggestion": _no_show_suggestion(count),
        }
        for patient_id, patient_name, count, last_no_show in rows
    ]
