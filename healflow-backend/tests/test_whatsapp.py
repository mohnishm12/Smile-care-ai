"""WhatsApp webhook tests.

The router is mounted on a standalone FastAPI app here (the production app
wires it in main.py via the orchestrator), so these tests stay independent
of app-level wiring.
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.config import get_settings
from src.routers.whatsapp import router

settings = get_settings()

VERIFY_TOKEN = "test-verify-token"


@pytest.fixture
async def wa_client():
    app = FastAPI()
    app.include_router(router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def _verify_token(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verify_token", VERIFY_TOKEN)


async def test_verify_returns_challenge_for_correct_token(wa_client, _verify_token):
    resp = await wa_client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "1158201444",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "1158201444"


async def test_verify_rejects_wrong_token(wa_client, _verify_token):
    resp = await wa_client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "1158201444",
        },
    )
    assert resp.status_code == 403


async def test_verify_rejects_when_token_unconfigured(wa_client, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verify_token", "")
    resp = await wa_client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "42"},
    )
    assert resp.status_code == 403


async def test_post_unknown_number_returns_received(wa_client):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "111222333"},
                            "messages": [
                                {
                                    "id": "wamid.test1",
                                    "from": "919999000111",
                                    "type": "text",
                                    "text": {"body": "hello, anyone there?"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    resp = await wa_client.post("/webhooks/whatsapp", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}


async def test_post_empty_payload_returns_received(wa_client):
    resp = await wa_client.post("/webhooks/whatsapp", json={"object": "whatsapp_business_account"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}
