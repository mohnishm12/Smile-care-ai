import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class AppointmentStatus(str, Enum):
    BOOKED = "booked"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        # One active booking per doctor per slot — double bookings are rejected
        # at the database level, not just in application logic.
        Index(
            "uq_appointments_doctor_slot_active",
            "doctor_id",
            "scheduled_at",
            unique=True,
            postgresql_where="status IN ('booked', 'confirmed', 'checked_in')",
        ),
        {"schema": "healflow"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.clinics.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.doctors.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.users.id"), nullable=False, index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(
            AppointmentStatus,
            name="appointment_status",
            schema="healflow",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        default=AppointmentStatus.BOOKED,
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reminder_24h_sent: Mapped[bool] = mapped_column(default=False, nullable=False)
    reminder_2h_sent: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class QueueEntry(Base):
    """Live walk-in / arrival queue per clinic."""

    __tablename__ = "queue_entries"
    __table_args__ = {"schema": "healflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.clinics.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.users.id"), nullable=False
    )
    # waiting | in_consult | done
    status: Mapped[str] = mapped_column(String(16), default="waiting", nullable=False)
    # Average consult minutes used for wait estimates.
    expected_minutes: Mapped[int] = mapped_column(default=15, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
