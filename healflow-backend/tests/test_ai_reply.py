import asyncio
import datetime as dt
import uuid

from sqlalchemy import create_engine, text

from src.config import get_settings

settings = get_settings()

ASSISTANT_ID = "00000000-0000-4000-8000-00000000a1a1"
CLINIC_ID = "00000000-0000-4000-8000-00000000c111"
DR_SHARMA_ID = "00000000-0000-4000-8000-00000000d111"


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
                VALUES (:id, 'SmileCare Test Clinic', '12 MG Road', 'Basement parking',
                        '+91-80-1234', '09:00', '18:00', 500, 'INR', '', '+91-80-9999',
                        '', '', true)
                ON CONFLICT (user_id) DO NOTHING
                """.replace("ON CONFLICT (user_id)", "ON CONFLICT (id)")
            ),
            {"id": CLINIC_ID},
        )
        conn.execute(
            text(
                """
                INSERT INTO healflow.doctors
                    (id, clinic_id, name, specialty, work_start, work_end, slot_minutes, is_active)
                VALUES (:id, :clinic_id, 'Dr. Sharma', 'Dental Surgery', '09:00', '17:00', 30, true)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"id": DR_SHARMA_ID, "clinic_id": CLINIC_ID},
        )
    engine.dispose()


async def _register_and_login(client, email: str) -> str:
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "Test User"},
    )
    resp = await client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    return resp.json()["access_token"]


async def _wait_for_reply(client, headers, after_message_id: str) -> dict | None:
    for _ in range(20):
        await asyncio.sleep(0.25)
        resp = await client.get("/api/messages", headers=headers)
        messages = resp.json()
        idx = next(i for i, m in enumerate(messages) if m["id"] == after_message_id)
        later = [m for m in messages[idx + 1 :] if m["sender_id"] == ASSISTANT_ID]
        if later:
            return later[-1]
    return None


async def test_assistant_lists_availability(client, unique_email):
    _seed_clinic()
    token = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/messages",
        json={"channel": "chat", "body": "Can I see Dr. Sharma tomorrow?"},
        headers=headers,
    )
    assert resp.status_code == 201

    reply = await _wait_for_reply(client, headers, resp.json()["id"])
    assert reply is not None, "assistant reply never arrived"
    # Fallback router lists available slots for Dr. Sharma.
    assert "Sharma" in reply["body"]
    assert "slot" in reply["body"].lower()


async def test_assistant_books_via_chat(client, unique_email):
    _seed_clinic()
    token = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {token}"}

    tomorrow = (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).date().isoformat()
    resp = await client.post(
        "/api/messages",
        json={"channel": "chat", "body": f"book Dr. Sharma {tomorrow} 11:00"},
        headers=headers,
    )
    reply = await _wait_for_reply(client, headers, resp.json()["id"])
    assert reply is not None
    assert "Booked" in reply["body"] or "taken" in reply["body"]


async def test_emergency_escalation(client, unique_email):
    _seed_clinic()
    token = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/messages",
        json={"channel": "chat", "body": "I have severe chest pain and can't breathe"},
        headers=headers,
    )
    reply = await _wait_for_reply(client, headers, resp.json()["id"])
    assert reply is not None
    assert "emergency" in reply["body"].lower()

    # Escalation row must exist for this patient.
    engine = create_engine(settings.database_sync_url)
    with engine.begin() as conn:
        count = conn.execute(
            text(
                """
                SELECT count(*) FROM healflow.escalations e
                JOIN healflow.users u ON u.id = e.patient_id
                WHERE u.email = :email
                """
            ),
            {"email": unique_email},
        ).scalar_one()
    engine.dispose()
    assert count >= 1


async def test_clinic_info(client, unique_email):
    _seed_clinic()
    token = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/messages",
        json={"channel": "chat", "body": "what are the clinic hours and parking?"},
        headers=headers,
    )
    reply = await _wait_for_reply(client, headers, resp.json()["id"])
    assert reply is not None
    assert "09:00" in reply["body"]
    assert "parking" in reply["body"].lower() or "Basement" in reply["body"]


async def test_double_booking_rejected(client, unique_email):
    _seed_clinic()
    token1 = await _register_and_login(client, unique_email)
    email2 = f"second-{uuid.uuid4().hex[:8]}@example.com"
    token2 = await _register_and_login(client, email2)

    tomorrow = (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).date().isoformat()
    body = f"book Dr. Sharma {tomorrow} 15:00"

    resp1 = await client.post(
        "/api/messages", json={"channel": "chat", "body": body},
        headers={"Authorization": f"Bearer {token1}"},
    )
    reply1 = await _wait_for_reply(
        client, {"Authorization": f"Bearer {token1}"}, resp1.json()["id"]
    )
    assert reply1 is not None and "Booked" in reply1["body"]

    resp2 = await client.post(
        "/api/messages", json={"channel": "chat", "body": body},
        headers={"Authorization": f"Bearer {token2}"},
    )
    reply2 = await _wait_for_reply(
        client, {"Authorization": f"Bearer {token2}"}, resp2.json()["id"]
    )
    assert reply2 is not None
    assert "Booked" not in reply2["body"] or "taken" in reply2["body"].lower()
