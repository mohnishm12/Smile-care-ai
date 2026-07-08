"""Demo mode — one tap to a live, populated clinic.

POST /api/demo/seed creates (idempotently) a demo staff login and a set of
realistic patients with conversations, follow-up check-ins, and one active
escalation, then returns tokens so the visitor lands straight in a working
Morning Brief and reception workspace. No signup, no empty states.
"""

import logging
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.appointment import Appointment, AppointmentStatus
from src.models.care import (
    Escalation,
    EscalationSeverity,
    FollowUpCheckin,
    FollowUpPlan,
    PatientProfile,
)
from src.models.clinic import Clinic, Doctor
from src.models.message import Message, MessageChannel
from src.models.user import User, UserRole
from src.security import create_access_token, create_refresh_token, hash_password

router = APIRouter(tags=["demo"])
logger = logging.getLogger("healflow.demo")

DEMO_STAFF_EMAIL = "demo-desk@meridian.clinic"
DEMO_PASSWORD = "demo-clinic"
ASSISTANT_ID = "00000000-0000-4000-8000-00000000a1a1"

# (email, name, treatment, pain_by_day, symptoms_last, escalation, unread_msg)
DEMO_PATIENTS = [
    ("rahul.demo@meridian.clinic", "Rahul Mehta", "root canal",
     [(1, 3), (2, 5), (3, 6)], {"swelling": True}, None,
     "the pain is getting worse at night, is that normal?"),
    ("priya.demo@meridian.clinic", "Priya Nair", "extraction",
     [(1, 4), (2, 3)], {}, None,
     "I forgot to take my antibiotic twice, what should I do?"),
    ("meera.demo@meridian.clinic", "Meera Iyer", "cleaning",
     [(1, 1), (2, 0)], {}, None, None),
    ("arjun.demo@meridian.clinic", "Arjun Rao", "implant",
     [(1, 5)], {}, "critical", "I have heavy bleeding that won't stop"),
]


class DemoSession(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    staff_name: str
    clinic_name: str


async def _get_or_create_user(
    db: AsyncSession, email: str, name: str, role: UserRole
) -> User:
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            hashed_password=hash_password(DEMO_PASSWORD),
            full_name=name,
            role=role,
        )
        db.add(user)
        await db.flush()
    return user


@router.post("/api/demo/seed", response_model=DemoSession)
async def seed_demo(db: AsyncSession = Depends(get_db)) -> DemoSession:
    clinic = (
        await db.execute(select(Clinic).where(Clinic.is_active).limit(1))
    ).scalar_one_or_none()
    if clinic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No clinic configured")
    doctor = (
        await db.execute(select(Doctor).where(Doctor.clinic_id == clinic.id).limit(1))
    ).scalar_one_or_none()

    staff = await _get_or_create_user(
        db, DEMO_STAFF_EMAIL, "Dr. Shah", UserRole.CLINIC_ADMIN
    )

    now = datetime.now(UTC)
    for email, name, treatment, pains, symptoms, escalation, unread in DEMO_PATIENTS:
        patient = await _get_or_create_user(db, email, name, UserRole.PATIENT)
        profile = await db.get(PatientProfile, patient.id)
        if profile is None:
            profile = PatientProfile(user_id=patient.id, clinic_id=clinic.id)
            db.add(profile)
        profile.high_priority = escalation is not None

        # Fresh follow-up plan + check-ins (idempotent: clear prior demo plans).
        existing = (
            await db.execute(
                select(FollowUpPlan).where(
                    FollowUpPlan.patient_id == patient.id,
                    FollowUpPlan.clinic_id == clinic.id,
                )
            )
        ).scalars().all()
        for plan in existing:
            for ci in (
                await db.execute(
                    select(FollowUpCheckin).where(FollowUpCheckin.plan_id == plan.id)
                )
            ).scalars().all():
                await db.delete(ci)
            await db.delete(plan)
        await db.flush()

        plan = FollowUpPlan(
            clinic_id=clinic.id,
            patient_id=patient.id,
            doctor_id=doctor.id if doctor else clinic.id,
            treatment=treatment,
            start_date=date.today() - timedelta(days=len(pains)),
            days=7,
        )
        db.add(plan)
        await db.flush()
        for day, pain in pains:
            asked = now - timedelta(days=len(pains) - day + 1)
            symp = symptoms if day == pains[-1][0] else {}
            db.add(
                FollowUpCheckin(
                    plan_id=plan.id, day_number=day, pain_level=pain,
                    symptoms=symp, asked_at=asked, responded_at=asked,
                )
            )

        if unread:
            db.add(
                Message(
                    sender_id=patient.id, conversation_user_id=patient.id,
                    channel=MessageChannel.CHAT, body=unread,
                )
            )

        if escalation:
            db.add(
                Escalation(
                    clinic_id=clinic.id, patient_id=patient.id,
                    severity=EscalationSeverity.CRITICAL
                    if escalation == "critical" else EscalationSeverity.HIGH,
                    trigger_text=unread or "red-flag symptom",
                    reason="heavy bleeding" if escalation == "critical" else "symptom",
                )
            )

        # An upcoming appointment for the recovered patient (discharge review).
        if doctor and treatment == "cleaning":
            db.add(
                Appointment(
                    clinic_id=clinic.id, doctor_id=doctor.id, patient_id=patient.id,
                    scheduled_at=now + timedelta(hours=3),
                    status=AppointmentStatus.CONFIRMED, reason="discharge review",
                )
            )

    await db.commit()

    return DemoSession(
        access_token=create_access_token(str(staff.id)),
        refresh_token=create_refresh_token(str(staff.id)),
        staff_name=staff.full_name,
        clinic_name=clinic.name,
    )
