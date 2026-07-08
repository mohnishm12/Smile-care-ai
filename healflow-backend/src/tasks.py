import hashlib
import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select

from src.celery_app import celery_app
from src.database_sync import get_sync_db
from src.models import (
    Appointment,
    AppointmentStatus,
    Doctor,
    Feedback,
    FollowUpCheckin,
    FollowUpPlan,
    MedicationLog,
    MedicationSchedule,
    Prescription,
)
from src.models.message import Message
from src.notify import notify_clinic, send_system_message

logger = logging.getLogger("healflow.tasks")

EMBEDDING_DIM = 384

# NOTE (timezone, MVP): everything is stored and compared in UTC.
# MedicationSchedule.times_of_day and FollowUpPlan.checkin_time are treated as
# UTC wall-clock times until per-clinic timezones are added.

DAY1_CHECKIN_QUESTION = "How are you feeling today? On a scale of 0-10, how is your pain?"
LATER_CHECKIN_QUESTION = "Any swelling or unusual symptoms today? How is your pain 0-10?"


def _placeholder_embedding(text: str) -> list[float]:
    """Deterministic pseudo-embedding derived from text hash.

    Placeholder for a real sentence-transformers/OpenAI embedding call —
    keeps the pgvector column populated and the similarity-search path
    exercisable end-to-end without bundling a model in the MVP.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    repeated = (digest * (EMBEDDING_DIM // len(digest) + 1))[:EMBEDDING_DIM]
    return [(b - 128) / 128.0 for b in repeated]


@celery_app.task(name="src.tasks.embed_message", bind=True, max_retries=3)
def embed_message(self, message_id: str) -> str:
    with get_sync_db() as db:
        message = db.get(Message, uuid.UUID(message_id))
        if message is None:
            return f"message {message_id} not found"
        message.embedding = _placeholder_embedding(message.body)
        db.commit()
    return f"embedded message {message_id}"


@celery_app.task(name="src.tasks.cleanup_expired_sessions")
def cleanup_expired_sessions() -> str:
    # Placeholder for session/refresh-token blacklist cleanup once that
    # store is added (e.g. Redis-backed revocation list).
    return f"cleanup ran at {datetime.now(UTC).isoformat()}"


def _as_date(value: datetime | date) -> date:
    """Coerce a Date-column value (typed datetime, returned as date) to date."""
    if isinstance(value, datetime):
        return value.date()
    return value


def _due_at_in_window(hhmm: str, now: datetime, window_start: datetime) -> datetime | None:
    """Return the tz-aware due datetime if this dose time falls in [window_start, now]."""
    try:
        hour, minute = (int(part) for part in hhmm.split(":", 1))
        dose_time = time(hour, minute)
    except (TypeError, ValueError, AttributeError):
        logger.warning("invalid times_of_day entry %r", hhmm)
        return None
    # Check today and yesterday so the window keeps working across midnight UTC.
    for day in (now.date(), now.date() - timedelta(days=1)):
        candidate = datetime.combine(day, dose_time, tzinfo=UTC)
        if window_start <= candidate <= now:
            return candidate
    return None


@celery_app.task(name="src.tasks.send_appointment_reminders")
def send_appointment_reminders() -> str:
    """Remind patients about upcoming appointments (24h and 2h ahead)."""
    now = datetime.now(UTC)
    sent = 0
    with get_sync_db() as db:
        appointments = (
            db.execute(
                select(Appointment).where(
                    Appointment.status.in_(
                        [AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED]
                    ),
                    Appointment.scheduled_at > now,
                    Appointment.scheduled_at <= now + timedelta(hours=24),
                )
            )
            .scalars()
            .all()
        )
        for appt in appointments:
            needs_24h = not appt.reminder_24h_sent
            needs_2h = (
                not appt.reminder_2h_sent
                and appt.scheduled_at <= now + timedelta(hours=2)
            )
            if not (needs_24h or needs_2h):
                continue
            doctor = db.get(Doctor, appt.doctor_id)
            doctor_name = doctor.name if doctor else "your doctor"
            when = appt.scheduled_at.strftime("%d %b %Y at %H:%M UTC")
            body = f"Reminder: appointment with {doctor_name} on {when}"
            if needs_24h:
                send_system_message(db, appt.patient_id, body)
                appt.reminder_24h_sent = True
                sent += 1
            if needs_2h:
                send_system_message(db, appt.patient_id, body)
                appt.reminder_2h_sent = True
                sent += 1
        db.commit()
    return f"sent {sent} appointment reminders"


@celery_app.task(name="src.tasks.send_medication_reminders")
def send_medication_reminders() -> str:
    """Create dose logs and remind patients for doses due in the last 10 minutes."""
    now = datetime.now(UTC)
    window_start = now - timedelta(minutes=10)
    today = now.date()
    created = 0
    with get_sync_db() as db:
        schedules = (
            db.execute(
                select(MedicationSchedule).where(
                    MedicationSchedule.is_active.is_(True),
                    MedicationSchedule.start_date <= today,
                    MedicationSchedule.end_date >= today,
                )
            )
            .scalars()
            .all()
        )
        for schedule in schedules:
            for hhmm in schedule.times_of_day:
                due_at = _due_at_in_window(hhmm, now, window_start)
                if due_at is None:
                    continue
                existing = db.execute(
                    select(MedicationLog.id).where(
                        MedicationLog.schedule_id == schedule.id,
                        MedicationLog.due_at == due_at,
                    )
                ).first()
                if existing is not None:
                    continue
                db.add(MedicationLog(schedule_id=schedule.id, due_at=due_at, reminded_at=now))
                send_system_message(
                    db,
                    schedule.patient_id,
                    f"Time to take your {schedule.medication_name} {schedule.dosage} 💊 "
                    "Reply 'done' when taken.",
                )
                created += 1
        db.commit()
    return f"sent {created} medication reminders"


@celery_app.task(name="src.tasks.nag_medication")
def nag_medication() -> str:
    """Nag patients about untaken doses; escalate to the clinic after a second miss."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=30)
    nagged = 0
    escalated = 0
    with get_sync_db() as db:
        pending = db.execute(
            select(MedicationLog, MedicationSchedule)
            .join(MedicationSchedule, MedicationLog.schedule_id == MedicationSchedule.id)
            .where(
                MedicationLog.reminded_at <= cutoff,
                MedicationLog.taken_at.is_(None),
                MedicationLog.nagged_at.is_(None),
            )
        ).all()
        for log, schedule in pending:
            send_system_message(
                db,
                schedule.patient_id,
                f"Gentle reminder: {schedule.medication_name} still pending",
            )
            log.nagged_at = now
            nagged += 1

        overdue = db.execute(
            select(MedicationLog, MedicationSchedule, Prescription)
            .join(MedicationSchedule, MedicationLog.schedule_id == MedicationSchedule.id)
            .join(Prescription, MedicationSchedule.prescription_id == Prescription.id)
            .where(
                MedicationLog.nagged_at <= cutoff,
                MedicationLog.taken_at.is_(None),
                MedicationLog.clinic_notified.is_(False),
            )
        ).all()
        for log, schedule, prescription in overdue:
            notify_clinic(
                db,
                prescription.clinic_id,
                f"Patient {schedule.patient_id} has not taken {schedule.medication_name} "
                f"(due {log.due_at.isoformat()}) after two reminders.",
            )
            log.clinic_notified = True
            escalated += 1
        db.commit()
    return f"nagged {nagged}, escalated {escalated}"


@celery_app.task(name="src.tasks.send_followup_checkins")
def send_followup_checkins() -> str:
    """Ask the daily recovery check-in question for active follow-up plans."""
    now = datetime.now(UTC)
    today = now.date()
    asked = 0
    with get_sync_db() as db:
        plans = (
            db.execute(
                select(FollowUpPlan).where(
                    FollowUpPlan.is_active.is_(True),
                    FollowUpPlan.start_date <= today,
                )
            )
            .scalars()
            .all()
        )
        for plan in plans:
            day_number = (today - _as_date(plan.start_date)).days + 1
            if day_number > plan.days:
                continue
            # checkin_time is a UTC wall-clock time for the MVP.
            if now.time() < plan.checkin_time:
                continue
            existing = db.execute(
                select(FollowUpCheckin.id).where(
                    FollowUpCheckin.plan_id == plan.id,
                    FollowUpCheckin.day_number == day_number,
                )
            ).first()
            if existing is not None:
                continue
            db.add(FollowUpCheckin(plan_id=plan.id, day_number=day_number, asked_at=now))
            question = DAY1_CHECKIN_QUESTION if day_number == 1 else LATER_CHECKIN_QUESTION
            send_system_message(db, plan.patient_id, question)
            asked += 1
        db.commit()
    return f"asked {asked} follow-up check-ins"


@celery_app.task(name="src.tasks.request_feedback")
def request_feedback() -> str:
    """Ask for a visit rating after completed appointments without feedback yet.

    Re-sends on each run until a Feedback row exists for the appointment or the
    24h window since completion lapses (per MVP spec).
    """
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=24)
    requested = 0
    with get_sync_db() as db:
        has_feedback = (
            select(Feedback.id).where(Feedback.appointment_id == Appointment.id).exists()
        )
        appointments = (
            db.execute(
                select(Appointment).where(
                    Appointment.status == AppointmentStatus.COMPLETED,
                    Appointment.updated_at >= cutoff,
                    ~has_feedback,
                )
            )
            .scalars()
            .all()
        )
        for appt in appointments:
            send_system_message(
                db, appt.patient_id, "How was your visit today? Reply with a rating 1-5 ⭐"
            )
            requested += 1
        db.commit()
    return f"requested feedback for {requested} appointments"


@celery_app.task(name="src.tasks.mark_no_shows")
def mark_no_shows() -> str:
    """Flip booked/confirmed appointments more than 2h past their slot to no_show."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=2)
    marked = 0
    with get_sync_db() as db:
        appointments = (
            db.execute(
                select(Appointment).where(
                    Appointment.status.in_(
                        [AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED]
                    ),
                    Appointment.scheduled_at < cutoff,
                )
            )
            .scalars()
            .all()
        )
        for appt in appointments:
            appt.status = AppointmentStatus.NO_SHOW
            marked += 1
        db.commit()
    return f"marked {marked} no-shows"
