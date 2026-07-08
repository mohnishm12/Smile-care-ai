import uuid
from datetime import datetime, time
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, Time, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Prescription(Base):
    __tablename__ = "prescriptions"
    __table_args__ = {"schema": "healflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.clinics.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.doctors.id"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.users.id"), nullable=False, index=True
    )
    diagnosis: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MedicationSchedule(Base):
    __tablename__ = "medication_schedules"
    __table_args__ = {"schema": "healflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prescription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.prescriptions.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.users.id"), nullable=False, index=True
    )
    medication_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dosage: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # Times of day the dose is due, e.g. ["08:00", "20:00"].
    times_of_day: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    start_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MedicationLog(Base):
    """One row per due dose: sent reminder, patient response, escalation."""

    __tablename__ = "medication_logs"
    __table_args__ = {"schema": "healflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("healflow.medication_schedules.id"),
        nullable=False,
        index=True,
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    nagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clinic_notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class FollowUpPlan(Base):
    """Post-treatment recovery follow-up sequence (the WhatsApp day-1/day-2 flow)."""

    __tablename__ = "followup_plans"
    __table_args__ = {"schema": "healflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.clinics.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.users.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.doctors.id"), nullable=False
    )
    treatment: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    # Preferred daily check-in time for the patient.
    checkin_time: Mapped[time] = mapped_column(Time, default=time(10, 0), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FollowUpCheckin(Base):
    __tablename__ = "followup_checkins"
    __table_args__ = {"schema": "healflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.followup_plans.id"), nullable=False, index=True
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pain_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Structured symptom flags extracted from the reply ({"swelling": false, ...}).
    symptoms: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    raw_response: Mapped[str] = mapped_column(Text, default="", nullable=False)


class EscalationSeverity(str, Enum):
    HIGH = "high"
    CRITICAL = "critical"


class Escalation(Base):
    """Raised when emergency keywords / red-flag symptoms are detected."""

    __tablename__ = "escalations"
    __table_args__ = {"schema": "healflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.clinics.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.users.id"), nullable=False, index=True
    )
    severity: Mapped[EscalationSeverity] = mapped_column(
        SAEnum(
            EscalationSeverity,
            name="escalation_severity",
            schema="healflow",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        default=EscalationSeverity.HIGH,
        nullable=False,
    )
    trigger_text: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = {"schema": "healflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.clinics.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.users.id"), nullable=False
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.appointments.id"), nullable=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..5
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # rating >= 4 → patient gets the Google review link; else internal ticket.
    ticket_opened: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ClinicKnowledge(Base):
    """Clinic-approved FAQ/knowledge base used to ground assistant answers."""

    __tablename__ = "clinic_knowledge"
    __table_args__ = {"schema": "healflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.clinics.id"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PatientProfile(Base):
    """Smart-memory profile keyed to the user account."""

    __tablename__ = "patient_profiles"
    __table_args__ = {"schema": "healflow"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.users.id"), primary_key=True
    )
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.clinics.id"), nullable=True
    )
    phone: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    whatsapp_number: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    preferred_contact_time: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    conditions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    insurance_provider: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    insurance_member_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    family_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    high_priority: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
