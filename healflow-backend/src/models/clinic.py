import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Clinic(Base):
    """Tenant root — every domain row hangs off a clinic for multi-clinic support."""

    __tablename__ = "clinics"
    __table_args__ = {"schema": "healflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, default="", nullable=False)
    location_url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    parking_instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    open_time: Mapped[time] = mapped_column(Time, default=time(9, 0), nullable=False)
    close_time: Mapped[time] = mapped_column(Time, default=time(18, 0), nullable=False)
    consultation_fee: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    google_review_url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    emergency_phone: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    whatsapp_phone_number_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Doctor(Base):
    __tablename__ = "doctors"
    __table_args__ = {"schema": "healflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.clinics.id"), nullable=False, index=True
    )
    # Optional link to a login account (role=doctor) for dashboard access.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healflow.users.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    specialty: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    # Working hours; slots are generated between these on slot_minutes boundaries.
    work_start: Mapped[time] = mapped_column(Time, default=time(9, 0), nullable=False)
    work_end: Mapped[time] = mapped_column(Time, default=time(17, 0), nullable=False)
    slot_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
