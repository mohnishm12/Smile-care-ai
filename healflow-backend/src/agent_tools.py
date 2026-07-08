"""Tools the AI receptionist can call, plus their Anthropic tool schemas.

Every tool takes (db, patient, args) and returns a JSON-serializable dict.
Tools are clinic-scoped through the patient's profile (multi-clinic ready).
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    Appointment,
    AppointmentStatus,
    Clinic,
    ClinicKnowledge,
    Doctor,
    FollowUpCheckin,
    FollowUpPlan,
    MedicationLog,
    MedicationSchedule,
    PatientProfile,
    QueueEntry,
    User,
)

ACTIVE_STATUSES = (
    AppointmentStatus.BOOKED,
    AppointmentStatus.CONFIRMED,
    AppointmentStatus.CHECKED_IN,
)


async def _default_clinic(db: AsyncSession) -> Clinic | None:
    result = await db.execute(select(Clinic).where(Clinic.is_active).limit(1))
    return result.scalar_one_or_none()


async def _patient_clinic(db: AsyncSession, patient: User) -> Clinic | None:
    profile = await db.get(PatientProfile, patient.id)
    if profile and profile.clinic_id:
        clinic = await db.get(Clinic, profile.clinic_id)
        if clinic:
            return clinic
    return await _default_clinic(db)


async def _find_doctor(db: AsyncSession, clinic_id: uuid.UUID, name: str) -> Doctor | None:
    result = await db.execute(
        select(Doctor).where(
            Doctor.clinic_id == clinic_id,
            Doctor.is_active,
            func.lower(Doctor.name).contains(
                name.lower().replace("dr.", "").replace("dr ", "").strip()
            ),
        )
    )
    return result.scalars().first()


def _parse_day(value: str) -> date:
    today = datetime.now(UTC).date()
    lowered = value.strip().lower()
    if lowered in ("today",):
        return today
    if lowered in ("tomorrow",):
        return today + timedelta(days=1)
    return date.fromisoformat(lowered)


async def get_clinic_info(db: AsyncSession, patient: User, args: dict) -> dict:
    clinic = await _patient_clinic(db, patient)
    if clinic is None:
        return {"error": "No clinic configured"}
    return {
        "name": clinic.name,
        "address": clinic.address,
        "location_url": clinic.location_url,
        "parking": clinic.parking_instructions,
        "phone": clinic.phone,
        "hours": f"{clinic.open_time.strftime('%H:%M')}-{clinic.close_time.strftime('%H:%M')}",
        "consultation_fee": f"{clinic.consultation_fee} {clinic.currency}",
        "emergency_phone": clinic.emergency_phone,
    }


async def list_doctors(db: AsyncSession, patient: User, args: dict) -> dict:
    clinic = await _patient_clinic(db, patient)
    if clinic is None:
        return {"error": "No clinic configured"}
    result = await db.execute(
        select(Doctor).where(Doctor.clinic_id == clinic.id, Doctor.is_active)
    )
    return {
        "doctors": [
            {"name": d.name, "specialty": d.specialty,
             "hours": f"{d.work_start.strftime('%H:%M')}-{d.work_end.strftime('%H:%M')}"}
            for d in result.scalars().all()
        ]
    }


async def get_availability(db: AsyncSession, patient: User, args: dict) -> dict:
    clinic = await _patient_clinic(db, patient)
    if clinic is None:
        return {"error": "No clinic configured"}
    doctor = await _find_doctor(db, clinic.id, args["doctor_name"])
    if doctor is None:
        return {"error": f"No doctor matching '{args['doctor_name']}' found"}
    try:
        day = _parse_day(args.get("date", "tomorrow"))
    except ValueError:
        return {"error": "Could not parse date; use YYYY-MM-DD, 'today' or 'tomorrow'"}

    day_start = datetime.combine(day, time.min, tzinfo=UTC)
    day_end = datetime.combine(day, time.max, tzinfo=UTC)
    result = await db.execute(
        select(Appointment.scheduled_at).where(
            Appointment.doctor_id == doctor.id,
            Appointment.scheduled_at.between(day_start, day_end),
            Appointment.status.in_(ACTIVE_STATUSES),
        )
    )
    taken = {
        row[0].replace(tzinfo=UTC) if row[0].tzinfo is None else row[0]
        for row in result.all()
    }

    slots = []
    cursor = datetime.combine(day, doctor.work_start, tzinfo=UTC)
    end = datetime.combine(day, doctor.work_end, tzinfo=UTC)
    now = datetime.now(UTC)
    while cursor < end:
        if cursor > now and cursor not in taken:
            slots.append(cursor.strftime("%H:%M"))
        cursor += timedelta(minutes=doctor.slot_minutes)

    return {"doctor": doctor.name, "date": day.isoformat(), "available_slots": slots[:12]}


async def book_appointment(db: AsyncSession, patient: User, args: dict) -> dict:
    clinic = await _patient_clinic(db, patient)
    if clinic is None:
        return {"error": "No clinic configured"}
    doctor = await _find_doctor(db, clinic.id, args["doctor_name"])
    if doctor is None:
        return {"error": f"No doctor matching '{args['doctor_name']}' found"}
    try:
        day = _parse_day(args["date"])
        slot_time = time.fromisoformat(args["time"])
    except (ValueError, KeyError):
        return {"error": "Need date (YYYY-MM-DD/'today'/'tomorrow') and time (HH:MM)"}

    scheduled_at = datetime.combine(day, slot_time, tzinfo=UTC)
    if scheduled_at < datetime.now(UTC):
        return {"error": "That time is in the past"}

    appointment = Appointment(
        clinic_id=clinic.id,
        doctor_id=doctor.id,
        patient_id=patient.id,
        scheduled_at=scheduled_at,
        reason=args.get("reason", ""),
    )
    db.add(appointment)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return {"error": "That slot was just taken — pick another time", "conflict": True}
    await db.refresh(appointment)
    return {
        "booked": True,
        "appointment_id": str(appointment.id),
        "doctor": doctor.name,
        "when": scheduled_at.strftime("%Y-%m-%d %H:%M"),
        "fee": f"{clinic.consultation_fee} {clinic.currency}",
    }


async def get_my_appointments(db: AsyncSession, patient: User, args: dict) -> dict:
    result = await db.execute(
        select(Appointment, Doctor.name)
        .join(Doctor, Doctor.id == Appointment.doctor_id)
        .where(
            Appointment.patient_id == patient.id,
            Appointment.status.in_(ACTIVE_STATUSES),
            Appointment.scheduled_at >= datetime.now(UTC) - timedelta(hours=1),
        )
        .order_by(Appointment.scheduled_at)
    )
    return {
        "appointments": [
            {
                "appointment_id": str(a.id),
                "doctor": doctor_name,
                "when": a.scheduled_at.strftime("%Y-%m-%d %H:%M"),
                "status": a.status.value,
            }
            for a, doctor_name in result.all()
        ]
    }


async def cancel_appointment(db: AsyncSession, patient: User, args: dict) -> dict:
    appointment = await db.get(Appointment, uuid.UUID(args["appointment_id"]))
    if appointment is None or appointment.patient_id != patient.id:
        return {"error": "Appointment not found"}
    if appointment.status not in ACTIVE_STATUSES:
        return {"error": f"Appointment is already {appointment.status.value}"}
    appointment.status = AppointmentStatus.CANCELLED
    await db.commit()
    return {"cancelled": True, "appointment_id": str(appointment.id)}


async def reschedule_appointment(db: AsyncSession, patient: User, args: dict) -> dict:
    appointment = await db.get(Appointment, uuid.UUID(args["appointment_id"]))
    if appointment is None or appointment.patient_id != patient.id:
        return {"error": "Appointment not found"}
    if appointment.status not in ACTIVE_STATUSES:
        return {"error": f"Appointment is {appointment.status.value}; book a new one instead"}
    try:
        day = _parse_day(args["date"])
        slot_time = time.fromisoformat(args["time"])
    except (ValueError, KeyError):
        return {"error": "Need date (YYYY-MM-DD/'today'/'tomorrow') and time (HH:MM)"}
    new_at = datetime.combine(day, slot_time, tzinfo=UTC)
    if new_at < datetime.now(UTC):
        return {"error": "That time is in the past"}
    old = appointment.scheduled_at
    appointment.scheduled_at = new_at
    appointment.reminder_24h_sent = False
    appointment.reminder_2h_sent = False
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return {"error": "That slot is taken — pick another time", "conflict": True}
    return {
        "rescheduled": True,
        "from": old.strftime("%Y-%m-%d %H:%M"),
        "to": new_at.strftime("%Y-%m-%d %H:%M"),
    }


async def get_my_medications(db: AsyncSession, patient: User, args: dict) -> dict:
    result = await db.execute(
        select(MedicationSchedule).where(
            MedicationSchedule.patient_id == patient.id,
            MedicationSchedule.is_active,
        )
    )
    return {
        "medications": [
            {
                "name": s.medication_name,
                "dosage": s.dosage,
                "times": s.times_of_day,
                "until": s.end_date.isoformat(),
            }
            for s in result.scalars().all()
        ]
    }


async def log_medication_taken(db: AsyncSession, patient: User, args: dict) -> dict:
    result = await db.execute(
        select(MedicationLog)
        .join(MedicationSchedule, MedicationSchedule.id == MedicationLog.schedule_id)
        .where(
            MedicationSchedule.patient_id == patient.id,
            MedicationLog.taken_at.is_(None),
            MedicationLog.reminded_at.is_not(None),
        )
        .order_by(MedicationLog.due_at.desc())
        .limit(1)
    )
    log = result.scalar_one_or_none()
    if log is None:
        return {"logged": False, "note": "No pending dose reminder found; noted anyway."}
    log.taken_at = datetime.now(UTC)
    await db.commit()
    return {"logged": True}


async def log_pain_level(db: AsyncSession, patient: User, args: dict) -> dict:
    level = int(args["level"])
    if not 0 <= level <= 10:
        return {"error": "Pain level must be 0-10"}
    result = await db.execute(
        select(FollowUpCheckin)
        .join(FollowUpPlan, FollowUpPlan.id == FollowUpCheckin.plan_id)
        .where(
            FollowUpPlan.patient_id == patient.id,
            FollowUpPlan.is_active,
            FollowUpCheckin.responded_at.is_(None),
        )
        .order_by(FollowUpCheckin.day_number.desc())
        .limit(1)
    )
    checkin = result.scalar_one_or_none()
    if checkin is None:
        return {
            "logged": False,
            "note": "No active follow-up plan; pain level noted in conversation only.",
        }
    checkin.pain_level = level
    checkin.responded_at = datetime.now(UTC)
    checkin.raw_response = args.get("context", "")
    await db.commit()
    return {"logged": True, "pain_level": level}


async def get_queue_status(db: AsyncSession, patient: User, args: dict) -> dict:
    clinic = await _patient_clinic(db, patient)
    if clinic is None:
        return {"error": "No clinic configured"}
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.clinic_id == clinic.id, QueueEntry.status == "waiting"
        ).order_by(QueueEntry.joined_at)
    )
    entries = list(result.scalars().all())
    ahead = 0
    for entry in entries:
        if entry.patient_id == patient.id:
            break
        ahead += 1
    else:
        ahead = len(entries)
    estimated = sum(e.expected_minutes for e in entries[:ahead])
    return {"patients_ahead": ahead, "estimated_wait_minutes": estimated}


async def search_clinic_knowledge(db: AsyncSession, patient: User, args: dict) -> dict:
    clinic = await _patient_clinic(db, patient)
    if clinic is None:
        return {"error": "No clinic configured"}
    query = args.get("query", "").lower()
    result = await db.execute(
        select(ClinicKnowledge).where(ClinicKnowledge.clinic_id == clinic.id)
    )
    entries = result.scalars().all()
    words = {w for w in query.split() if len(w) > 3}
    scored = []
    for entry in entries:
        haystack = f"{entry.topic} {entry.content}".lower()
        score = sum(1 for w in words if w in haystack)
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return {
        "entries": [
            {"topic": e.topic, "content": e.content} for _, e in scored[:3]
        ]
    }


TOOL_HANDLERS: dict[str, Any] = {
    "get_clinic_info": get_clinic_info,
    "list_doctors": list_doctors,
    "get_availability": get_availability,
    "book_appointment": book_appointment,
    "get_my_appointments": get_my_appointments,
    "cancel_appointment": cancel_appointment,
    "reschedule_appointment": reschedule_appointment,
    "get_my_medications": get_my_medications,
    "log_medication_taken": log_medication_taken,
    "log_pain_level": log_pain_level,
    "get_queue_status": get_queue_status,
    "search_clinic_knowledge": search_clinic_knowledge,
}

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "get_clinic_info",
        "description": (
            "Clinic name, address, location link, parking, phone, opening hours, consultation fee."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_doctors",
        "description": "List the clinic's doctors with specialties and working hours.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_availability",
        "description": "Get a doctor's open appointment slots for a date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "doctor_name": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD, 'today' or 'tomorrow'"},
            },
            "required": ["doctor_name"],
        },
    },
    {
        "name": "book_appointment",
        "description": "Book an appointment. Confirm doctor, date and time with the patient first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "doctor_name": {"type": "string"},
                "date": {"type": "string"},
                "time": {"type": "string", "description": "HH:MM 24h"},
                "reason": {"type": "string"},
            },
            "required": ["doctor_name", "date", "time"],
        },
    },
    {
        "name": "get_my_appointments",
        "description": "The patient's upcoming appointments (needed before cancel/reschedule).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel one of the patient's appointments by id.",
        "input_schema": {
            "type": "object",
            "properties": {"appointment_id": {"type": "string"}},
            "required": ["appointment_id"],
        },
    },
    {
        "name": "reschedule_appointment",
        "description": "Move an existing appointment to a new date/time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string"},
                "date": {"type": "string"},
                "time": {"type": "string"},
            },
            "required": ["appointment_id", "date", "time"],
        },
    },
    {
        "name": "get_my_medications",
        "description": "The patient's current prescribed medications and dose times.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "log_medication_taken",
        "description": (
            "Record that the patient took their most recently reminded dose "
            "(they said 'done', 'taken', etc.)."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "log_pain_level",
        "description": (
            "Record the patient's reported pain level (0-10) against their "
            "active recovery follow-up."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "integer", "minimum": 0, "maximum": 10},
                "context": {"type": "string"},
            },
            "required": ["level"],
        },
    },
    {
        "name": "get_queue_status",
        "description": "Live clinic queue: how many patients are ahead and estimated wait.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_clinic_knowledge",
        "description": (
            "Search clinic-approved FAQ/knowledge (aftercare, diet, exercise, "
            "medicines with food, services)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]
