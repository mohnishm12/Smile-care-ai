"""Morning Brief product-surface test: demo seed → brief → act.

Exercises the full bridge: live domain rows → kernel replay → ranked
Decisions over HTTP, and that acting on a decision changes the world.
"""

import uuid

import pytest
from sqlalchemy import create_engine, text

from src.config import get_settings

settings = get_settings()

# Kernel tables aren't in the ORM metadata (they live in migration 0004);
# conftest's create_all won't make them. Bootstrap here.
KERNEL_DDL = """
CREATE TABLE IF NOT EXISTS healflow.meridian_events (
    event_id uuid PRIMARY KEY, stream_id varchar(128) NOT NULL, seq bigint NOT NULL,
    tenant_id varchar(64) NOT NULL, type varchar(96) NOT NULL, v integer NOT NULL DEFAULT 1,
    occurred_at timestamptz NOT NULL, recorded_at timestamptz NOT NULL,
    actor jsonb NOT NULL, payload jsonb NOT NULL, causation_id uuid, correlation_id uuid,
    prev_hash varchar(64) NOT NULL DEFAULT '', hash varchar(64) NOT NULL,
    CONSTRAINT uq_meridian_stream_seq UNIQUE (stream_id, seq));
CREATE INDEX IF NOT EXISTS ix_meridian_events_replay
    ON healflow.meridian_events (recorded_at, stream_id, seq);
CREATE TABLE IF NOT EXISTS healflow.meridian_checkpoints (
    projector varchar(96) PRIMARY KEY, last_event_id uuid NOT NULL, last_seq_key varchar(256) NOT NULL);
CREATE TABLE IF NOT EXISTS healflow.meridian_applied (
    projector varchar(96) NOT NULL, event_id uuid NOT NULL, PRIMARY KEY (projector, event_id));
CREATE TABLE IF NOT EXISTS healflow.rm_recovery (
    stream_id varchar(128) PRIMARY KEY, tenant_id varchar(64) NOT NULL, episode varchar(128) NOT NULL,
    score integer NOT NULL, components jsonb NOT NULL, evidence jsonb NOT NULL,
    engine_version varchar(32) NOT NULL, computed_from_seq bigint NOT NULL);
CREATE TABLE IF NOT EXISTS healflow.rm_risk (
    stream_id varchar(128) NOT NULL, hazard varchar(64) NOT NULL, tenant_id varchar(64) NOT NULL,
    level varchar(16) NOT NULL, basis jsonb NOT NULL, rules_version varchar(32) NOT NULL,
    PRIMARY KEY (stream_id, hazard));
CREATE TABLE IF NOT EXISTS healflow.rm_trust (
    tenant_id varchar(64) NOT NULL, action_class varchar(96) NOT NULL, outcomes jsonb NOT NULL,
    engine_version varchar(32) NOT NULL, PRIMARY KEY (tenant_id, action_class));
CREATE TABLE IF NOT EXISTS healflow.rm_decisions (
    decision_id varchar(160) PRIMARY KEY, tenant_id varchar(64) NOT NULL, as_of timestamptz NOT NULL,
    rank integer NOT NULL, priority numeric(18,4) NOT NULL, body jsonb NOT NULL);
"""


@pytest.fixture(autouse=True)
def _kernel_tables():
    engine = create_engine(settings.database_sync_url)
    with engine.begin() as conn:
        for stmt in KERNEL_DDL.split(";"):
            if stmt.strip():
                conn.execute(text(stmt))
    engine.dispose()


def _seed_clinic() -> None:
    engine = create_engine(settings.database_sync_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO healflow.clinics
                    (id, name, address, parking_instructions, phone, open_time, close_time,
                     consultation_fee, currency, google_review_url, emergency_phone,
                     location_url, whatsapp_phone_number_id, is_active)
                VALUES ('00000000-0000-4000-8000-00000000c111', 'Demo Clinic', '', '', '',
                        '09:00','18:00',500,'INR','','+91-1', '', '', true)
                ON CONFLICT (id) DO NOTHING
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO healflow.doctors
                    (id, clinic_id, name, specialty, work_start, work_end, slot_minutes, is_active)
                VALUES ('00000000-0000-4000-8000-00000000d111',
                        '00000000-0000-4000-8000-00000000c111', 'Dr. Sharma', 'Dental',
                        '09:00','17:00',30,true)
                ON CONFLICT (id) DO NOTHING
                """
            )
        )
    engine.dispose()


async def test_demo_seed_then_brief_then_act(client):
    _seed_clinic()

    # One tap: demo session (staff token, populated clinic).
    resp = await client.post("/api/demo/seed")
    assert resp.status_code == 200
    session = resp.json()
    assert session["access_token"]
    assert session["clinic_name"]
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    # The Morning Brief: ranked decisions from the seeded patients.
    resp = await client.get("/api/brief", headers=headers)
    assert resp.status_code == 200
    brief = resp.json()
    assert "morning" in brief["greeting"].lower() or "afternoon" in brief["greeting"].lower() \
        or "evening" in brief["greeting"].lower()
    assert brief["attention_count"] >= 1
    decisions = brief["decisions"]

    # Arjun's critical bleeding escalation must rank first.
    top = decisions[0]
    assert top["hazard"] == "unacknowledged_escalation"
    assert top["level"] == "critical"
    # Every decision carries the traceability payload.
    for d in decisions:
        assert d["summary"] and d["evidence"] and d["recommended_action"]["action"]
        assert d["trust"]["tier"] in ("ASK", "DRAFT", "ACT")
        assert d["if_ignored"]

    # Act on the top escalation → acknowledge.
    resp = await client.post(
        "/api/brief/act",
        json={"decision_id": top["decision_id"], "action": "acknowledge_escalation"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json().get("acknowledged")

    # Regenerate: the acknowledged escalation is gone from the top.
    resp = await client.get("/api/brief", headers=headers)
    new_top = resp.json()["decisions"]
    assert not new_top or new_top[0]["decision_id"] != top["decision_id"]


async def test_brief_requires_staff(client):
    email = f"pt-{uuid.uuid4().hex[:8]}@example.com"
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "Pat"},
    )
    token = (
        await client.post(
            "/api/auth/login", json={"email": email, "password": "supersecret1"}
        )
    ).json()["access_token"]
    resp = await client.get("/api/brief", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
