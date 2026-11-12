"""Staff-facing AI helpers: missed-conversation summaries and visit-note drafts.

Uses the Claude API when an API key is configured; otherwise falls back to
deterministic rule-based output so the endpoints stay functional keyless.
"""

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai import ASSISTANT_USER_ID
from src.config import get_settings
from src.models.message import Message, MessageChannel
from src.models.user import User, UserRole

settings = get_settings()
logger = logging.getLogger("healflow.staff_ai")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

SYMPTOM_KEYWORDS = (
    "swelling",
    "bleeding",
    "fever",
    "nausea",
    "dizziness",
    "headache",
    "vomiting",
    "infection",
    "numbness",
    "rash",
)


async def _claude_complete(prompt: str, max_tokens: int = 300) -> str | None:
    """Single-turn Claude completion; returns None when keyless or on any error."""
    if not settings.anthropic_api_key:
        return None
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
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            data = response.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ).strip()
        return text or None
    except Exception:
        logger.warning("Claude call failed; using rule-based fallback", exc_info=True)
        return None


async def summarize_missed(db: AsyncSession) -> list[dict]:
    """Patients whose last chat message in the past 24h has no assistant reply.

    Messages carry no recipient/thread id, so "replied" is approximated as any
    assistant chat message created after the patient's last message.
    """
    cutoff = datetime.now(UTC) - timedelta(days=1)

    result = await db.execute(
        select(Message, User)
        .join(User, User.id == Message.sender_id)
        .where(
            Message.channel == MessageChannel.CHAT,
            Message.created_at >= cutoff,
            User.role == UserRole.PATIENT,
        )
        .order_by(Message.created_at.asc())
    )
    last_by_patient: dict[uuid.UUID, tuple[Message, User]] = {}
    for message, sender in result.all():
        last_by_patient[sender.id] = (message, sender)  # ascending order → last one wins

    if not last_by_patient:
        return []

    last_assistant_at = (
        await db.execute(
            select(Message.created_at)
            .where(
                Message.sender_id == ASSISTANT_USER_ID,
                Message.channel == MessageChannel.CHAT,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    summaries: list[dict] = []
    for message, sender in last_by_patient.values():
        if last_assistant_at is not None and last_assistant_at > message.created_at:
            continue
        summary = await _claude_complete(
            "Summarise this unanswered patient message for clinic staff in one line, "
            f"no preamble. Patient {sender.full_name} wrote: {message.body[:500]}",
            max_tokens=100,
        )
        summaries.append(
            {
                "patient_id": str(sender.id),
                "patient_name": sender.full_name,
                "last_message": message.body,
                "waiting_since": message.created_at.isoformat(),
                "summary": summary or message.body[:100],
            }
        )
    return summaries


async def draft_visit_note(db: AsyncSession, patient: User) -> str:
    """Draft a visit note from the patient's last 30 chat messages."""
    result = await db.execute(
        select(Message)
        .where(
            Message.channel == MessageChannel.CHAT,
            Message.sender_id.in_([patient.id, ASSISTANT_USER_ID]),
        )
        .order_by(Message.created_at.desc())
        .limit(30)
    )
    messages = list(reversed(result.scalars().all()))

    transcript = "\n".join(
        f"{'Assistant' if m.sender_id == ASSISTANT_USER_ID else 'Patient'}: {m.body}"
        for m in messages
    )
    if transcript:
        draft = await _claude_complete(
            "Draft a concise clinical visit note (subjective/assessment style) for "
            f"patient {patient.full_name} from this chat transcript. Mark it as an "
            f"unverified draft for staff review.\n\n{transcript[:6000]}",
            max_tokens=settings.anthropic_max_tokens,
        )
        if draft:
            return draft
    return _template_note(patient, messages)


def _template_note(patient: User, messages: list[Message]) -> str:
    patient_bodies = [m.body for m in messages if m.sender_id != ASSISTANT_USER_ID]
    text = " ".join(patient_bodies).lower()

    pain_levels = [
        match for match in re.findall(r"pain[^0-9]{0,20}(\d{1,2})", text) if int(match) <= 10
    ]
    symptoms = sorted({keyword for keyword in SYMPTOM_KEYWORDS if keyword in text})

    lines = [
        f"Visit note draft — {patient.full_name}",
        f"Generated {datetime.now(UTC).date().isoformat()} from the last "
        f"{len(messages)} chat messages ({len(patient_bodies)} from the patient).",
        f"Reported pain levels: {', '.join(pain_levels) if pain_levels else 'none reported'}.",
        f"Symptoms mentioned: {', '.join(symptoms) if symptoms else 'none detected'}.",
        "This is an automated draft — review the conversation before finalising.",
    ]
    return "\n".join(lines)
