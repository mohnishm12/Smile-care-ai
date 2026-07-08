import uuid

from sqlalchemy import create_engine, text

from src.config import get_settings

settings = get_settings()


async def _register_and_login(client, email: str, role: str | None = None) -> str:
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "Test User"},
    )
    if role:
        engine = create_engine(settings.database_sync_url)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE healflow.users SET role = :r WHERE email = :e"),
                {"r": role, "e": email},
            )
        engine.dispose()
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": "supersecret1"}
    )
    return resp.json()["access_token"]


async def test_patient_cannot_read_other_conversations(client, unique_email):
    """THE privacy law: a patient sees only their own thread."""
    email_a = unique_email
    email_b = f"other-{uuid.uuid4().hex[:8]}@example.com"
    token_a = await _register_and_login(client, email_a)
    token_b = await _register_and_login(client, email_b)
    secret = f"secret-{uuid.uuid4().hex[:8]}"

    await client.post(
        "/api/messages",
        json={"channel": "chat", "body": secret},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    resp = await client.get(
        "/api/messages", headers={"Authorization": f"Bearer {token_b}"}
    )
    bodies = [m["body"] for m in resp.json()]
    assert all(secret not in b for b in bodies), "patient B can read patient A's messages"


async def test_reception_endpoints_require_staff(client, unique_email):
    token = await _register_and_login(client, unique_email)
    resp = await client.get(
        "/api/reception/conversations", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403


async def test_takeover_pauses_ai_and_staff_reply_flows(client, unique_email):
    patient_email = unique_email
    staff_email = f"staff-{uuid.uuid4().hex[:8]}@example.com"
    patient_token = await _register_and_login(client, patient_email)
    staff_token = await _register_and_login(client, staff_email, role="staff")
    patient_headers = {"Authorization": f"Bearer {patient_token}"}
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    # Patient opens a conversation.
    first = await client.post(
        "/api/messages",
        json={"channel": "chat", "body": "hello, question about parking"},
        headers=patient_headers,
    )
    patient_id = first.json()["sender_id"]

    # Staff sees the conversation in the index.
    resp = await client.get("/api/reception/conversations", headers=staff_headers)
    assert resp.status_code == 200
    conversations = resp.json()
    ours = [c for c in conversations if c["patient_id"] == patient_id]
    assert ours and ours[0]["ai_paused"] is False

    # Takeover pauses the runtime.
    resp = await client.post(
        f"/api/reception/conversations/{patient_id}/takeover", headers=staff_headers
    )
    assert resp.json() == {"ai_paused": True}

    # Staff sends as clinic; message lands in the patient's thread.
    resp = await client.post(
        f"/api/reception/conversations/{patient_id}/send",
        json={"body": "Hi, this is the front desk — basement parking is open."},
        headers=staff_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["conversation_user_id"] == patient_id

    resp = await client.get("/api/messages", headers=patient_headers)
    bodies = [m["body"] for m in resp.json()]
    assert any("front desk" in b for b in bodies)

    # While paused, a patient message gets NO assistant auto-reply.
    import asyncio

    before = len((await client.get("/api/messages", headers=patient_headers)).json())
    await client.post(
        "/api/messages",
        json={"channel": "chat", "body": "thanks! one more thing"},
        headers=patient_headers,
    )
    await asyncio.sleep(1.5)
    after_msgs = (await client.get("/api/messages", headers=patient_headers)).json()
    assistant_replies_after = [
        m
        for m in after_msgs[before:]
        if m["sender_id"] == "00000000-0000-4000-8000-00000000a1a1"
    ]
    assert not assistant_replies_after, "runtime replied while paused"

    # Resume re-enables the runtime.
    resp = await client.post(
        f"/api/reception/conversations/{patient_id}/resume", headers=staff_headers
    )
    assert resp.json() == {"ai_paused": False}


async def test_suggest_returns_draft_without_sending(client, unique_email):
    patient_email = unique_email
    staff_email = f"staff-{uuid.uuid4().hex[:8]}@example.com"
    patient_token = await _register_and_login(client, patient_email)
    staff_token = await _register_and_login(client, staff_email, role="staff")

    first = await client.post(
        "/api/messages",
        json={"channel": "chat", "body": "what are the clinic hours?"},
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    patient_id = first.json()["sender_id"]

    count_before = len(
        (
            await client.get(
                "/api/messages",
                headers={"Authorization": f"Bearer {patient_token}"},
            )
        ).json()
    )

    resp = await client.post(
        f"/api/reception/conversations/{patient_id}/suggest",
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["suggestion"]) > 0

    # Suggest must not append to the thread (patient-visible count may grow by
    # the auto-reply to their own message, but never by the suggestion itself —
    # allow at most one assistant auto-reply).
    import asyncio

    await asyncio.sleep(1.0)
    count_after = len(
        (
            await client.get(
                "/api/messages",
                headers={"Authorization": f"Bearer {patient_token}"},
            )
        ).json()
    )
    assert count_after - count_before <= 1
