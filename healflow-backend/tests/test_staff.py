import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.config import get_settings
from src.main import app
from src.models import Clinic, Escalation, User
from src.models.user import UserRole
from src.routers import staff

settings = get_settings()

# The orchestrator wires staff.router into src.main; include it here too so
# these tests are self-sufficient if that wiring lands later.
if not any(getattr(route, "path", None) == "/api/analytics/overview" for route in app.routes):
    app.include_router(staff.router)

OVERVIEW_KEYS = {
    "todays_appointments",
    "missed_appointments",
    "revenue",
    "currency",
    "avg_rating",
    "followup_completion_rate",
    "response_rate",
    "open_escalations",
}


async def _register_and_login(client, email: str) -> str:
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "Staff Tester"},
    )
    resp = await client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    return resp.json()["access_token"]


def _set_role(email: str, role: UserRole) -> uuid.UUID:
    """Flip a user's role directly in the DB via a sync session."""
    engine = create_engine(settings.database_sync_url)
    try:
        with Session(engine) as session:
            user = session.execute(select(User).where(User.email == email)).scalar_one()
            user.role = role
            session.commit()
            return user.id
    finally:
        engine.dispose()


def _create_escalation(patient_id: uuid.UUID) -> uuid.UUID:
    engine = create_engine(settings.database_sync_url)
    try:
        with Session(engine) as session:
            clinic = Clinic(name="Ack Test Clinic")
            session.add(clinic)
            session.flush()
            escalation = Escalation(
                clinic_id=clinic.id,
                patient_id=patient_id,
                trigger_text="severe bleeding after extraction",
                reason="red-flag keyword",
            )
            session.add(escalation)
            session.commit()
            return escalation.id
    finally:
        engine.dispose()


async def test_analytics_overview_forbidden_for_patient(client, unique_email):
    token = await _register_and_login(client, unique_email)
    resp = await client.get("/api/analytics/overview", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


async def test_analytics_overview_shape_for_staff(client, unique_email):
    token = await _register_and_login(client, unique_email)
    _set_role(unique_email, UserRole.STAFF)

    resp = await client.get("/api/analytics/overview", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert OVERVIEW_KEYS <= set(data)
    assert isinstance(data["todays_appointments"], int)
    assert isinstance(data["open_escalations"], int)
    assert isinstance(data["followup_completion_rate"], int | float)
    assert isinstance(data["response_rate"], int | float)
    assert isinstance(data["currency"], str)


async def test_escalation_ack_roundtrip(client, unique_email):
    token = await _register_and_login(client, unique_email)
    user_id = _set_role(unique_email, UserRole.STAFF)
    escalation_id = _create_escalation(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    list_resp = await client.get("/api/staff/escalations", headers=headers)
    assert list_resp.status_code == 200
    row = next(e for e in list_resp.json() if e["id"] == str(escalation_id))
    assert row["acknowledged"] is False
    assert row["severity"] == "high"
    assert row["patient_name"] == "Staff Tester"

    ack_resp = await client.post(f"/api/staff/escalations/{escalation_id}/ack", headers=headers)
    assert ack_resp.status_code == 200
    assert ack_resp.json()["acknowledged"] is True

    again = await client.get("/api/staff/escalations", headers=headers)
    row = next(e for e in again.json() if e["id"] == str(escalation_id))
    assert row["acknowledged"] is True
