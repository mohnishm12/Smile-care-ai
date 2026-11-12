async def _register_and_login(client, email: str) -> str:
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "Test User"},
    )
    resp = await client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    return resp.json()["access_token"]


async def test_create_and_list_messages(client, unique_email):
    token = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/messages", json={"channel": "chat", "body": "hello"}, headers=headers
    )
    assert create_resp.status_code == 201
    message = create_resp.json()
    assert message["body"] == "hello"

    list_resp = await client.get("/api/messages", headers=headers)
    assert list_resp.status_code == 200
    bodies = [m["body"] for m in list_resp.json()]
    assert "hello" in bodies


async def test_create_message_requires_auth(client):
    resp = await client.post("/api/messages", json={"channel": "chat", "body": "hi"})
    assert resp.status_code == 401
