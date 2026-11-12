"""Unit tests for the scheduled care-flow Celery tasks.

Tasks are invoked in-process (no worker/broker needed) — a Celery task called
as a plain function executes synchronously. Data is committed through a direct
sync session; the tasks open their own session via ``get_sync_db``.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models import (
    Appointment,
    AppointmentStatus,
    Clinic,
    Doctor,
    MedicationLog,
    MedicationSchedule,
    Message,
    Prescription,
    User,
)
from src.models.user import UserRole
from src.notify import ASSISTANT_USER_ID
from src.tasks import mark_no_shows, send_medication_reminders

settings = get_settings()


@pytest.fixture
def db():
    engine = create_engine(settings.database_sync_url)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _ensure_assistant_user(db: Session) -> None:
    """System messages are authored by the fixed assistant user; seed it if absent."""
    if db.get(User, ASSISTANT_USER_ID) is None:
        db.add(
            User(
                id=ASSISTANT_USER_ID,
                email="assistant@healflow.internal",
                hashed_password="!disabled-login",
                full_name="HealFlow Assistant",
                role=UserRole.STAFF,
            )
        )
        db.flush()


def _make_patient(db: Session) -> User:
    patient = User(
        email=f"flow-{uuid.uuid4().hex[:10]}@example.com",
        hashed_password="x",
        full_name="Flow Patient",
        role=UserRole.PATIENT,
    )
    db.add(patient)
    db.flush()
    return patient


def _make_clinic_and_doctor(db: Session) -> tuple[Clinic, Doctor]:
    clinic = Clinic(name=f"Flow Clinic {uuid.uuid4().hex[:6]}")
    db.add(clinic)
    db.flush()
    doctor = Doctor(clinic_id=clinic.id, name="Dr. Flow")
    db.add(doctor)
    db.flush()
    return clinic, doctor


def test_send_medication_reminders_creates_log_and_message(db):
    _ensure_assistant_user(db)
    patient = _make_patient(db)
    clinic, doctor = _make_clinic_and_doctor(db)
    prescription = Prescription(
        clinic_id=clinic.id, doctor_id=doctor.id, patient_id=patient.id
    )
    db.add(prescription)
    db.flush()

    now = datetime.now(UTC)
    due = now - timedelta(minutes=5)  # inside the 10-minute reminder window
    medication_name = f"Amoxicillin-{uuid.uuid4().hex[:6]}"
    schedule = MedicationSchedule(
        prescription_id=prescription.id,
        patient_id=patient.id,
        medication_name=medication_name,
        dosage="500mg",
        times_of_day=[due.strftime("%H:%M")],
        start_date=(due - timedelta(days=1)).date(),
        end_date=(due + timedelta(days=1)).date(),
        is_active=True,
    )
    db.add(schedule)
    db.commit()

    send_medication_reminders()
    # Second run must be idempotent — no duplicate log for the same due time.
    send_medication_reminders()

    log = db.execute(
        select(MedicationLog).where(MedicationLog.schedule_id == schedule.id)
    ).scalar_one()
    assert log.reminded_at is not None
    assert log.taken_at is None
    assert log.nagged_at is None

    message = (
        db.execute(
            select(Message).where(
                Message.sender_id == ASSISTANT_USER_ID,
                Message.body.contains(medication_name),
            )
        )
        .scalars()
        .first()
    )
    assert message is not None
    assert "500mg" in message.body
    assert "done" in message.body


def test_mark_no_shows_flips_old_booked_appointment(db):
    patient = _make_patient(db)
    clinic, doctor = _make_clinic_and_doctor(db)
    now = datetime.now(UTC)
    stale = Appointment(
        clinic_id=clinic.id,
        doctor_id=doctor.id,
        patient_id=patient.id,
        scheduled_at=now - timedelta(hours=3),
        status=AppointmentStatus.BOOKED,
    )
    upcoming = Appointment(
        clinic_id=clinic.id,
        doctor_id=doctor.id,
        patient_id=patient.id,
        scheduled_at=now + timedelta(hours=1),
        status=AppointmentStatus.BOOKED,
    )
    db.add_all([stale, upcoming])
    db.commit()

    mark_no_shows()

    db.expire_all()
    flipped = db.get(Appointment, stale.id)
    untouched = db.get(Appointment, upcoming.id)
    assert flipped is not None and flipped.status == AppointmentStatus.NO_SHOW
    assert untouched is not None and untouched.status == AppointmentStatus.BOOKED
