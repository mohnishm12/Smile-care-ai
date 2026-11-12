async def test_register_and_login(client, unique_email):
    register_resp = await client.post(
        "/api/auth/register",
        json={"email": unique_email, "password": "supersecret1", "full_name": "Test User"},
    )
    assert register_resp.status_code == 201
    assert register_resp.json()["email"] == unique_email

    login_resp = await client.post(
        "/api/auth/login", json={"email": unique_email, "password": "supersecret1"}
    )
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    assert tokens["token_type"] == "bearer"
    assert "access_token" in tokens

    me_resp = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == unique_email


async def test_login_wrong_password(client, unique_email):
    await client.post(
        "/api/auth/register",
        json={"email": unique_email, "password": "supersecret1", "full_name": "Test User"},
    )
    resp = await client.post(
        "/api/auth/login", json={"email": unique_email, "password": "wrong-password"}
    )
    assert resp.status_code == 401


async def test_register_duplicate_email(client, unique_email):
    payload = {"email": unique_email, "password": "supersecret1", "full_name": "Test User"}
    first = await client.post("/api/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/api/auth/register", json=payload)
    assert second.status_code == 409


async def test_me_requires_auth(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
