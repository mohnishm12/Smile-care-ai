"""Meta WhatsApp Cloud API client + medical image analysis.

Every outbound call is a no-op (with a logged warning) when the relevant
credential is missing, so local dev without Meta/Anthropic keys never crashes.
"""

import base64
import logging

import httpx

from src.config import get_settings

logger = logging.getLogger("healflow.whatsapp")
settings = get_settings()

GRAPH_API_BASE = "https://graph.facebook.com"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

IMAGE_ANALYSIS_PROMPT = (
    "You are a clinical intake assistant at a medical clinic. A patient sent "
    "this image over WhatsApp. It may be a prescription, lab report, dental "
    "photo, wound photo, or other medical document.\n\n"
    "Extract structured information:\n"
    "1. Image type (prescription / lab report / dental / wound / other)\n"
    "2. Any legible text: medication names, dosages, values, dates, doctor names\n"
    "3. Visible findings, described neutrally\n\n"
    "Rules: NEVER diagnose, NEVER suggest treatment, NEVER alarm the patient. "
    "List findings factually. Keep it under 120 words, WhatsApp-friendly. "
    "ALWAYS end with: 'This has been flagged for clinician review — a care "
    "team member will follow up.'"
)


async def send_text(to: str, body: str, phone_number_id: str) -> bool:
    """Send a WhatsApp text message via the Cloud API. Returns True on success."""
    if not settings.whatsapp_access_token:
        logger.warning("WhatsApp access token not configured; skipping send to %s", to)
        return False
    if not phone_number_id:
        logger.warning("No phone_number_id for outbound WhatsApp message to %s", to)
        return False
    url = f"{GRAPH_API_BASE}/{settings.whatsapp_api_version}/{phone_number_id}/messages"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"body": body},
            },
        )
        response.raise_for_status()
    return True


async def get_media_url(media_id: str) -> str | None:
    """Resolve a WhatsApp media id to its short-lived download URL."""
    if not settings.whatsapp_access_token:
        logger.warning("WhatsApp access token not configured; cannot resolve media %s", media_id)
        return None
    url = f"{GRAPH_API_BASE}/{settings.whatsapp_api_version}/{media_id}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            url, headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"}
        )
        response.raise_for_status()
        media_url = response.json().get("url")
    return media_url if isinstance(media_url, str) else None


async def download_media(url: str) -> bytes | None:
    """Download media bytes from a URL returned by get_media_url."""
    if not settings.whatsapp_access_token:
        logger.warning("WhatsApp access token not configured; cannot download media")
        return None
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            url, headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"}
        )
        response.raise_for_status()
        return response.content


async def analyze_medical_image(image_bytes: bytes, mime_type: str) -> str | None:
    """Extract structured info from a medical image via Claude vision.

    Returns None when no Anthropic key is configured or analysis fails, so the
    caller can fall back to a plain acknowledgement.
    """
    if not settings.anthropic_api_key:
        logger.warning("Anthropic API key not configured; skipping image analysis")
        return None
    payload = {
        "model": settings.anthropic_model,
        "max_tokens": max(settings.anthropic_max_tokens, 512),
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type or "image/jpeg",
                            "data": base64.standard_b64encode(image_bytes).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": IMAGE_ANALYSIS_PROMPT},
                ],
            }
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        logger.warning("Medical image analysis failed", exc_info=True)
        return None
    text = "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    ).strip()
    if not text:
        return None
    if "flagged for clinician review" not in text.lower():
        text += "\n\n⚠ This has been flagged for clinician review."
    return text
