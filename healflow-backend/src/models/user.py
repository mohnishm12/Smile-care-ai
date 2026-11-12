import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class UserRole(str, Enum):
    ADMIN = "admin"
    CLINIC_ADMIN = "clinic_admin"
    DOCTOR = "doctor"
    STAFF = "staff"
    PATIENT = "patient"


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "healflow"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="user_role",
            schema="healflow",
            # Store enum VALUES ("patient"), not Python member names ("PATIENT"),
            # matching the type created by the alembic migration.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        default=UserRole.PATIENT,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
