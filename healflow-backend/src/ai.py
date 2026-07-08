"""AI assistant reply generation.

Uses the Anthropic Messages API when ANTHROPIC_API_KEY is configured;
otherwise falls back to a deterministic built-in responder so the chat
remains functional in environments without an API key.
"""

import logging
import uuid

import httpx

from src.config import get_settings

logger = logging.getLogger("healflow.ai")

settings = get_settings()

# Fixed identity for the assistant user, created by migration 0002.
ASSISTANT_USER_ID = uuid.UUID("00000000-0000-4000-8000-00000000a1a1")
ASSISTANT_EMAIL = "assistant@healflow.internal"

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

SYSTEM_PROMPT = (
    "You are the HealFlow AI care assistant for a dental/medical clinic's "
    "patient communication platform. Be warm, concise, and helpful. "
    "You can help patients with general questions, appointment requests, "
    "and clinic information. You must NOT give medical diagnoses or "
    "prescribe treatment — for clinical questions, advise the patient that "
    "a member of the care team will follow up. Keep replies under 120 words."
)

FALLBACK_REPLY = (
    "Thanks for your message! I'm the HealFlow assistant. "
    "A member of our care team will review this and follow up shortly. "
    "If this is a medical emergency, please call your local emergency number."
)


def _fallback_reply(latest_message: str) -> str:
    text = latest_message.lower()
    if any(w in text for w in ("appointment", "book", "schedule", "reschedule", "cancel")):
        return (
            "I can help with appointments! Our care team will confirm your "
            "request shortly. Please share your preferred date and time if you "
            "haven't already."
        )
    if any(w in text for w in ("hours", "open", "location", "address", "phone")):
        return (
            "Our clinic details are available on your patient portal home page. "
            "A team member will follow up with specifics shortly."
        )
    if any(w in text for w in ("pain", "hurt", "bleed", "swelling", "emergency")):
        return (
            "I'm sorry you're experiencing this. I can't give medical advice, "
            "but I've flagged your message for the care team to respond as soon "
            "as possible. If this is an emergency, please call your local "
            "emergency number right away."
        )
    return FALLBACK_REPLY


async def generate_reply(history: list[dict[str, str]]) -> str:
    """Generate an assistant reply for the conversation history.

    `history` is a list of {"role": "user"|"assistant", "content": str},
    oldest first, ending with the message to answer.
    """
    if not settings.anthropic_api_key:
        latest = history[-1]["content"] if history else ""
        return _fallback_reply(latest)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": settings.anthropic_model,
                    "max_tokens": settings.anthropic_max_tokens,
                    "system": SYSTEM_PROMPT,
                    "messages": history,
                },
            )
            response.raise_for_status()
            data = response.json()
            parts = [
                block["text"]
                for block in data.get("content", [])
                if block.get("type") == "text"
            ]
            reply = "".join(parts).strip()
            if reply:
                return reply
            logger.warning("Anthropic API returned no text content; using fallback")
    except Exception:
        logger.warning("Anthropic API call failed; using fallback reply", exc_info=True)

    latest = history[-1]["content"] if history else ""
    return _fallback_reply(latest)
