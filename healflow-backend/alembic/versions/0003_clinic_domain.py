"""clinic domain — clinics, doctors, appointments, care, queue, knowledge

Revision ID: 0003
Revises: 0002
Create Date: 2026-01-01 00:00:02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_CLINIC_ID = "00000000-0000-4000-8000-00000000c111"
DR_SHARMA_ID = "00000000-0000-4000-8000-00000000d111"
DR_PATEL_ID = "00000000-0000-4000-8000-00000000d222"


def upgrade() -> None:
    postgresql.ENUM(
        "booked", "confirmed", "checked_in", "completed", "cancelled", "no_show",
        name="appointment_status", schema="healflow",
    ).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM(
        "high", "critical", name="escalation_severity", schema="healflow",
    ).create(op.get_bind(), checkfirst=True)

    appointment_status = postgresql.ENUM(
        "booked", "confirmed", "checked_in", "completed", "cancelled", "no_show",
        name="appointment_status", schema="healflow", create_type=False,
    )
    escalation_severity = postgresql.ENUM(
        "high", "critical", name="escalation_severity", schema="healflow", create_type=False,
    )

    op.create_table(
        "clinics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text(), nullable=False, server_default=""),
        sa.Column("location_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("parking_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("phone", sa.String(32), nullable=False, server_default=""),
        sa.Column("open_time", sa.Time(), nullable=False, server_default="09:00"),
        sa.Column("close_time", sa.Time(), nullable=False, server_default="18:00"),
        sa.Column("consultation_fee", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="INR"),
        sa.Column("google_review_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("emergency_phone", sa.String(32), nullable=False, server_default=""),
        sa.Column("whatsapp_phone_number_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="healflow",
    )

    op.create_table(
        "doctors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.clinics.id"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.users.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("specialty", sa.String(255), nullable=False, server_default=""),
        sa.Column("work_start", sa.Time(), nullable=False, server_default="09:00"),
        sa.Column("work_end", sa.Time(), nullable=False, server_default="17:00"),
        sa.Column("slot_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="healflow",
    )

    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.clinics.id"), nullable=False, index=True),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.doctors.id"), nullable=False, index=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.users.id"), nullable=False, index=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", appointment_status, nullable=False, server_default="booked"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("reminder_24h_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reminder_2h_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="healflow",
    )
    op.create_index(
        "uq_appointments_doctor_slot_active",
        "appointments",
        ["doctor_id", "scheduled_at"],
        unique=True,
        schema="healflow",
        postgresql_where=sa.text("status IN ('booked', 'confirmed', 'checked_in')"),
    )

    op.create_table(
        "queue_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.clinics.id"), nullable=False, index=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.users.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="waiting"),
        sa.Column("expected_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="healflow",
    )

    op.create_table(
        "prescriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.clinics.id"), nullable=False, index=True),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.doctors.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.users.id"), nullable=False, index=True),
        sa.Column("diagnosis", sa.Text(), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="healflow",
    )

    op.create_table(
        "medication_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prescription_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.prescriptions.id"), nullable=False, index=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.users.id"), nullable=False, index=True),
        sa.Column("medication_name", sa.String(255), nullable=False),
        sa.Column("dosage", sa.String(128), nullable=False, server_default=""),
        sa.Column("times_of_day", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="healflow",
    )

    op.create_table(
        "medication_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.medication_schedules.id"), nullable=False, index=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nagged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_notified", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="healflow",
    )

    op.create_table(
        "followup_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.clinics.id"), nullable=False, index=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.users.id"), nullable=False, index=True),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.doctors.id"), nullable=False),
        sa.Column("treatment", sa.String(255), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("checkin_time", sa.Time(), nullable=False, server_default="10:00"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="healflow",
    )

    op.create_table(
        "followup_checkins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.followup_plans.id"), nullable=False, index=True),
        sa.Column("day_number", sa.Integer(), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pain_level", sa.Integer(), nullable=True),
        sa.Column("symptoms", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("raw_response", sa.Text(), nullable=False, server_default=""),
        schema="healflow",
    )

    op.create_table(
        "escalations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.clinics.id"), nullable=False, index=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.users.id"), nullable=False, index=True),
        sa.Column("severity", escalation_severity, nullable=False, server_default="high"),
        sa.Column("trigger_text", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="healflow",
    )

    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.clinics.id"), nullable=False, index=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.users.id"), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.appointments.id"), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("ticket_opened", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="healflow",
    )

    op.create_table(
        "clinic_knowledge",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.clinics.id"), nullable=False, index=True),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="healflow",
    )

    op.create_table(
        "patient_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.users.id"), primary_key=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healflow.clinics.id"), nullable=True),
        sa.Column("phone", sa.String(32), nullable=False, server_default=""),
        sa.Column("whatsapp_number", sa.String(32), nullable=False, server_default=""),
        sa.Column("preferred_language", sa.String(8), nullable=False, server_default="en"),
        sa.Column("preferred_contact_time", sa.String(32), nullable=False, server_default=""),
        sa.Column("conditions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("insurance_provider", sa.String(255), nullable=False, server_default=""),
        sa.Column("insurance_member_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("family_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("high_priority", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="healflow",
    )
    op.create_index(
        "ix_healflow_patient_profiles_whatsapp",
        "patient_profiles",
        ["whatsapp_number"],
        schema="healflow",
    )

    # ---- Seed: default clinic, doctors, knowledge base ----
    op.execute(
        f"""
        INSERT INTO healflow.clinics
            (id, name, address, parking_instructions, phone, consultation_fee,
             google_review_url, emergency_phone)
        VALUES (
            '{DEFAULT_CLINIC_ID}',
            'SmileCare Dental Clinic',
            '12 MG Road, Bengaluru 560001',
            'Basement parking available; enter from the rear gate on Church Street.',
            '+91-80-4000-1234',
            500,
            'https://g.page/r/smilecare-review',
            '+91-80-4000-9999'
        )
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO healflow.doctors (id, clinic_id, name, specialty, work_start, work_end, slot_minutes)
        VALUES
            ('{DR_SHARMA_ID}', '{DEFAULT_CLINIC_ID}', 'Dr. Sharma', 'Dental Surgery', '09:00', '17:00', 30),
            ('{DR_PATEL_ID}',  '{DEFAULT_CLINIC_ID}', 'Dr. Patel',  'Orthodontics',   '10:00', '18:00', 30)
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO healflow.clinic_knowledge (id, clinic_id, topic, content) VALUES
        (gen_random_uuid(), '{DEFAULT_CLINIC_ID}', 'root canal aftercare',
         'After a root canal: eat soft foods for 24-48 hours (yogurt, soup, mashed vegetables), avoid chewing on the treated side, avoid very hot or hard foods. Mild soreness is normal for 2-3 days; take prescribed painkillers with food.'),
        (gen_random_uuid(), '{DEFAULT_CLINIC_ID}', 'exercise after dental procedure',
         'Avoid strenuous exercise for 24 hours after extractions or surgery to prevent bleeding. Light walking is fine. Resume normal activity when comfortable unless your doctor said otherwise.'),
        (gen_random_uuid(), '{DEFAULT_CLINIC_ID}', 'medicines with food',
         'Amoxicillin can be taken with or without food; taking it with food reduces stomach upset. Paracetamol can be taken with or without food. Ibuprofen should always be taken after food.'),
        (gen_random_uuid(), '{DEFAULT_CLINIC_ID}', 'physiotherapy',
         'Physiotherapy uses guided exercise, manual therapy, and equipment to restore movement and reduce pain. Our partner physiotherapy centre offers sessions Mon-Sat; reception can book a referral.'),
        (gen_random_uuid(), '{DEFAULT_CLINIC_ID}', 'dental cleaning schedule',
         'We recommend a professional dental cleaning every 6 months. It takes about 30-45 minutes.')
        """
    )


def downgrade() -> None:
    for table in (
        "patient_profiles", "clinic_knowledge", "feedback", "escalations",
        "followup_checkins", "followup_plans", "medication_logs",
        "medication_schedules", "prescriptions", "queue_entries",
        "appointments", "doctors", "clinics",
    ):
        op.drop_table(table, schema="healflow")
    postgresql.ENUM(name="appointment_status", schema="healflow").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="escalation_severity", schema="healflow").drop(op.get_bind(), checkfirst=True)
