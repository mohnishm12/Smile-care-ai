"""Meta WhatsApp Cloud API webhook.

GET  /webhooks/whatsapp — Meta verification handshake.
POST /webhooks/whatsapp — inbound messages; always ACKs 200 fast so Meta
does not retry, with per-message processing wrapped in try/except.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src import whatsapp_client
from src.ai import ASSISTANT_EMAIL, ASSISTANT_USER_ID, generate_agent_reply
from src.config import get_settings
from src.database import async_session_maker
from src.models.care import PatientProfile
from src.models.message import Message, MessageChannel
from src.models.user import User, UserRole

settings = get_settings()
logger = logging.getLogger("healflow.whatsapp")

router = APIRouter(tags=["whatsapp"])

UNREGISTERED_REPLY = (
    "Hi! We couldn't find your patient record for this number. "
    "Please register at the clinic portal first, or visit reception "
    "and we'll link your WhatsApp right away."
)
VOICE_NOTE_REPLY = (
    "Voice notes will be supported soon — please type your message for now 🙏"
)
IMAGE_SAVED_REPLY = "Image received and saved for the care team 📎"


@router.get("/webhooks/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
) -> PlainTextResponse:
    """Meta webhook verification handshake — echo the challenge on token match."""
    if (
        hub_mode == "subscribe"
        and settings.whatsapp_verify_token
        and hub_verify_token == settings.whatsapp_verify_token
    ):
        return PlainTextResponse(content=hub_challenge)
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Webhook verification failed")


@router.post("/webhooks/whatsapp")
async def receive_webhook(payload: dict[str, Any]) -> dict[str, str]:
    """Process inbound WhatsApp messages. Always 200 — Meta retries on non-200."""
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            phone_number_id = str((value.get("metadata") or {}).get("phone_number_id") or "")
            for message in value.get("messages") or []:
                try:
                    await _process_message(message, phone_number_id)
                except Exception:
                    logger.warning(
                        "WhatsApp message processing failed (id=%s)",
                        message.get("id"),
                        exc_info=True,
                    )
    return {"status": "received"}


async def transcribe_audio(media_id: str) -> str | None:
    """Pluggable speech-to-text hook.

    TODO: wire a real STT provider (e.g. Whisper) — download the media via
    whatsapp_client.get_media_url + download_media, transcribe, and return the
    text. Returning None signals "no transcriber configured" and triggers the
    voice-note fallback reply.
    """
    return None


async def _ensure_assistant_user(db: AsyncSession) -> None:
    if await db.get(User, ASSISTANT_USER_ID) is None:
        db.add(
            User(
                id=ASSISTANT_USER_ID,
                email=ASSISTANT_EMAIL,
                hashed_password="!disabled-login",
                full_name="HealFlow Assistant",
                role=UserRole.STAFF,
            )
        )
        await db.commit()


async def _handle_image(message: dict[str, Any]) -> str:
    image = message.get("image") or {}
    media_id = str(image.get("id") or "")
    mime_type = str(image.get("mime_type") or "image/jpeg")
    if settings.whatsapp_access_token and media_id:
        media_url = await whatsapp_client.get_media_url(media_id)
        if media_url:
            image_bytes = await whatsapp_client.download_media(media_url)
            if image_bytes:
                analysis = await whatsapp_client.analyze_medical_image(image_bytes, mime_type)
                if analysis:
                    return analysis
    return IMAGE_SAVED_REPLY


async def _process_message(message: dict[str, Any], phone_number_id: str) -> None:
    wa_number = str(message.get("from") or "")
    msg_type = str(message.get("type") or "")
    if not wa_number:
        return

    async with async_session_maker() as db:
        profile = (
            await db.execute(
                select(PatientProfile).where(PatientProfile.whatsapp_number == wa_number)
            )
        ).scalars().first()
        if profile is None:
            # Only attempts the send when creds are configured (client no-ops otherwise).
            await whatsapp_client.send_text(wa_number, UNREGISTERED_REPLY, phone_number_id)
            return
        patient = await db.get(User, profile.user_id)
        if patient is None:
            logger.warning("PatientProfile %s has no user account", profile.user_id)
            return

        if msg_type == "text":
            body = str((message.get("text") or {}).get("body") or "")
        elif msg_type == "audio":
            body = "[voice note received]"
        elif msg_type == "image":
            body = "[image received]"
        else:
            body = f"[{msg_type or 'unknown'} message received]"

        db.add(Message(sender_id=patient.id, channel=MessageChannel.WHATSAPP, body=body))
        await db.commit()

        if msg_type == "text":
            reply = await generate_agent_reply(db, patient, [{"role": "user", "content": body}])
        elif msg_type == "audio":
            transcript = await transcribe_audio(str((message.get("audio") or {}).get("id") or ""))
            if transcript:
                reply = await generate_agent_reply(
                    db, patient, [{"role": "user", "content": transcript}]
                )
            else:
                reply = VOICE_NOTE_REPLY
        elif msg_type == "image":
            reply = await _handle_image(message)
        else:
            reply = (
                "Sorry, I can only handle text messages right now — "
                "please type your message 🙏"
            )

        await _ensure_assistant_user(db)
        db.add(Message(sender_id=ASSISTANT_USER_ID, channel=MessageChannel.WHATSAPP, body=reply))
        await db.commit()

    await whatsapp_client.send_text(wa_number, reply, phone_number_id)
