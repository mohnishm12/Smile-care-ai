"""HealFlow AI receptionist agent.

Pipeline per patient message:
1. Emergency pre-filter (runs BEFORE any model call; never skipped)
2. With ANTHROPIC_API_KEY: Claude agent loop with clinic tools
3. Without a key: deterministic intent router driving the same tools

Both paths share the tool layer in src/agent_tools.py, so booking,
availability, medications, queue, and FAQ work with or without an API key.
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_tools import TOOL_HANDLERS, TOOL_SCHEMAS
from src.config import get_settings
from src.models import (
    Clinic,
    Escalation,
    EscalationSeverity,
    MedicationSchedule,
    PatientProfile,
    User,
)

logger = logging.getLogger("healflow.ai")
settings = get_settings()

ASSISTANT_USER_ID = uuid.UUID("00000000-0000-4000-8000-00000000a1a1")
ASSISTANT_EMAIL = "assistant@healflow.internal"

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MAX_TOOL_ROUNDS = 6

SYSTEM_PROMPT = """You are the HealFlow AI care assistant — the virtual receptionist \
and recovery companion for {clinic_name}.

You help patients with: appointments (check availability, book, cancel, reschedule), \
clinic information (hours, location, parking, fees), their prescribed medications, \
recovery check-ins (pain levels, symptoms), live queue status, and clinic-approved \
health FAQs.

Rules:
- Use the tools for anything factual — never invent slots, fees, or medication names.
- Before booking, confirm doctor + date + time with the patient.
- You must NOT diagnose conditions or prescribe treatment. For clinical questions \
beyond the clinic-approved knowledge base, say a care team member will follow up.
- Reply in the patient's language ({language_hint}). Supported: English, Hindi, \
Kannada, Tamil, Telugu, Malayalam.
- Be warm and concise — WhatsApp-style short messages, under 100 words.
- If a patient reports worrying symptoms (fever, bleeding, severe pain 8+), \
acknowledge, log what you can, and tell them the care team has been alerted.

Patient context:
{patient_context}"""

# ---------------------------------------------------------------------------
# Emergency detection — keyword layer, runs before any model call
# ---------------------------------------------------------------------------

EMERGENCY_PATTERNS: list[tuple[str, str, EscalationSeverity]] = [
    (r"chest\s*pain|heart\s*attack", "possible cardiac event", EscalationSeverity.CRITICAL),
    (r"can'?t\s*breathe|cannot\s*breathe|difficulty\s*breathing|short(ness)?\s*of\s*breath",
     "breathing difficulty", EscalationSeverity.CRITICAL),
    (r"stroke|face\s*droop|slurred\s*speech|one\s*side.*(numb|weak)",
     "possible stroke", EscalationSeverity.CRITICAL),
    (r"heavy\s*bleed|bleeding\s*(a lot|heavily|won'?t stop)|blood\s*everywhere",
     "heavy bleeding", EscalationSeverity.CRITICAL),
    (r"suicid|kill\s*myself|end\s*my\s*life|don'?t want to live",
     "self-harm risk", EscalationSeverity.CRITICAL),
    (r"severe\s*allerg|anaphyla|throat\s*(closing|swelling)",
     "severe allergic reaction", EscalationSeverity.CRITICAL),
    (r"high\s*fever|fever\s*(above|over)\s*10[3-9]|104\s*degree",
     "high fever", EscalationSeverity.HIGH),
    (r"\bfever\b", "fever reported", EscalationSeverity.HIGH),
    (r"\bbleed(ing)?\b", "bleeding reported", EscalationSeverity.HIGH),
]

EMERGENCY_REPLY = (
    "🚨 This sounds like it may be a medical emergency.\n\n"
    "Please CALL {emergency_phone} (clinic emergency line) or your local "
    "emergency number (112 in India) RIGHT NOW.\n\n"
    "If someone is with you, ask them to help. Your doctor and our care team "
    "have been alerted and will contact you immediately."
)

HIGH_PRIORITY_REPLY = (
    "I'm sorry you're experiencing this — I've alerted your doctor and our care "
    "team, and marked your case high priority. Someone will contact you very soon.\n\n"
    "If symptoms get worse, call {emergency_phone} or 112 immediately."
)


@dataclass
class EmergencyResult:
    detected: bool
    severity: EscalationSeverity | None = None
    reason: str = ""


def detect_emergency(text: str) -> EmergencyResult:
    lowered = text.lower()
    for pattern, reason, severity in EMERGENCY_PATTERNS:
        if re.search(pattern, lowered):
            return EmergencyResult(True, severity, reason)
    return EmergencyResult(False)


async def raise_escalation(
    db: AsyncSession, patient: User, text: str, result: EmergencyResult
) -> str:
    clinic = (
        await db.execute(select(Clinic).where(Clinic.is_active).limit(1))
    ).scalar_one_or_none()
    profile = await db.get(PatientProfile, patient.id)
    if profile is None:
        profile = PatientProfile(user_id=patient.id, clinic_id=clinic.id if clinic else None)
        db.add(profile)
    profile.high_priority = True
    db.add(
        Escalation(
            clinic_id=clinic.id if clinic else None,
            patient_id=patient.id,
            severity=result.severity or EscalationSeverity.HIGH,
            trigger_text=text[:2000],
            reason=result.reason,
        )
    )
    await db.commit()
    emergency_phone = clinic.emergency_phone if clinic and clinic.emergency_phone else "the clinic"
    template = (
        EMERGENCY_REPLY if result.severity == EscalationSeverity.CRITICAL else HIGH_PRIORITY_REPLY
    )
    return template.format(emergency_phone=emergency_phone)


# ---------------------------------------------------------------------------
# Language detection (script-based; Latin text defaults to profile/en)
# ---------------------------------------------------------------------------

SCRIPT_RANGES = {
    "hi": (0x0900, 0x097F),  # Devanagari
    "kn": (0x0C80, 0x0CFF),  # Kannada
    "ta": (0x0B80, 0x0BFF),  # Tamil
    "te": (0x0C00, 0x0C7F),  # Telugu
    "ml": (0x0D00, 0x0D7F),  # Malayalam
}

LANGUAGE_NAMES = {
    "en": "English", "hi": "Hindi", "kn": "Kannada",
    "ta": "Tamil", "te": "Telugu", "ml": "Malayalam",
}


def detect_language(text: str, default: str = "en") -> str:
    counts = dict.fromkeys(SCRIPT_RANGES, 0)
    for char in text:
        point = ord(char)
        for lang, (start, end) in SCRIPT_RANGES.items():
            if start <= point <= end:
                counts[lang] += 1
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] >= 3 else default


# ---------------------------------------------------------------------------
# Patient memory context
# ---------------------------------------------------------------------------

async def build_patient_context(db: AsyncSession, patient: User) -> str:
    lines = [f"Name: {patient.full_name}"]
    profile = await db.get(PatientProfile, patient.id)
    if profile:
        if profile.preferred_language != "en":
            lines.append(f"Preferred language: {LANGUAGE_NAMES.get(profile.preferred_language)}")
        if profile.conditions:
            lines.append(f"Known conditions: {', '.join(profile.conditions)}")
        if profile.insurance_provider:
            lines.append(f"Insurance: {profile.insurance_provider}")
        if profile.high_priority:
            lines.append("⚠ Currently marked HIGH PRIORITY")
    meds = (
        await db.execute(
            select(MedicationSchedule).where(
                MedicationSchedule.patient_id == patient.id, MedicationSchedule.is_active
            )
        )
    ).scalars().all()
    if meds:
        lines.append(
            "Active medications: " + "; ".join(f"{m.medication_name} {m.dosage}" for m in meds)
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude agent loop (tool use)
# ---------------------------------------------------------------------------

async def _call_claude(payload: dict) -> dict:
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
        return response.json()


async def _agent_loop(
    db: AsyncSession, patient: User, history: list[dict], language: str
) -> str:
    context = await build_patient_context(db, patient)
    system = SYSTEM_PROMPT.format(
        clinic_name="the clinic",
        language_hint=LANGUAGE_NAMES.get(language, "English"),
        patient_context=context,
    )
    messages: list[dict] = list(history)

    for _ in range(MAX_TOOL_ROUNDS):
        data = await _call_claude(
            {
                "model": settings.anthropic_model,
                "max_tokens": settings.anthropic_max_tokens,
                "system": system,
                "tools": TOOL_SCHEMAS,
                "messages": messages,
            }
        )
        content = data.get("content", [])
        tool_uses = [b for b in content if b.get("type") == "tool_use"]
        if not tool_uses:
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
            return text or _fallback_generic()

        messages.append({"role": "assistant", "content": content})
        results = []
        for block in tool_uses:
            handler = TOOL_HANDLERS.get(block["name"])
            if handler is None:
                output: dict = {"error": f"Unknown tool {block['name']}"}
            else:
                try:
                    output = await handler(db, patient, block.get("input", {}))
                except Exception:
                    logger.warning("Tool %s failed", block["name"], exc_info=True)
                    output = {"error": "Tool failed; apologise and offer human follow-up"}
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": json.dumps(output, default=str),
                }
            )
        messages.append({"role": "user", "content": results})

    return "I'm having trouble completing that — our care team will follow up shortly."


# ---------------------------------------------------------------------------
# Keyless fallback — deterministic intent router over the same tools
# ---------------------------------------------------------------------------

def _fallback_generic() -> str:
    return (
        "Thanks for your message! I'm the HealFlow assistant. I can help with "
        "appointments (try: 'slots for Dr. Sharma tomorrow'), clinic info "
        "('clinic hours', 'parking', 'fees'), your medications ('my medicines'), "
        "or the queue ('how long is the wait?')."
    )


async def _fallback_route(db: AsyncSession, patient: User, text: str) -> str:
    lowered = text.lower()

    doctor_match = re.search(r"dr\.?\s*([a-z]+)", lowered)
    time_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", lowered)
    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", lowered)
    day = (
        iso_match.group(1)
        if iso_match
        else "tomorrow" if "tomorrow" in lowered else "today" if "today" in lowered else None
    )

    booking_words = ("book", "appointment", "slot", "available", "see dr", "meet dr")
    if any(w in lowered for w in booking_words) or doctor_match:
        doctor_name = doctor_match.group(1) if doctor_match else ""
        if not doctor_match:
            doctors = await TOOL_HANDLERS["list_doctors"](db, patient, {})
            names = ", ".join(d["name"] for d in doctors.get("doctors", []))
            return f"Which doctor would you like to see? Available: {names}"
        if time_match and day:
            result = await TOOL_HANDLERS["book_appointment"](
                db, patient,
                {"doctor_name": doctor_name, "date": day, "time": time_match.group(0)},
            )
            if result.get("booked"):
                return (
                    f"✅ Booked! {result['doctor']} on {result['when']}. "
                    f"Consultation fee: {result['fee']}. You'll get a reminder before the visit."
                )
            return f"Couldn't book: {result.get('error', 'unknown error')}"
        availability = await TOOL_HANDLERS["get_availability"](
            db, patient, {"doctor_name": doctor_name, "date": day or "tomorrow"}
        )
        if availability.get("error"):
            return availability["error"]
        slots = availability["available_slots"]
        if not slots:
            return f"{availability['doctor']} has no open slots on {availability['date']}."
        shown = ", ".join(slots[:6])
        return (
            f"{availability['doctor']} has these slots on {availability['date']}: {shown}. "
            f"Reply like: 'book Dr. {doctor_name.title()} {availability['date']} {slots[0]}'"
        )

    if any(w in lowered for w in ("cancel", "reschedul")):
        mine = await TOOL_HANDLERS["get_my_appointments"](db, patient, {})
        if not mine["appointments"]:
            return "You have no upcoming appointments."
        first = mine["appointments"][0]
        if "cancel" in lowered and ("yes" in lowered or "confirm" in lowered):
            result = await TOOL_HANDLERS["cancel_appointment"](
                db, patient, {"appointment_id": first["appointment_id"]}
            )
            return "Cancelled ✅" if result.get("cancelled") else result.get("error", "Failed")
        listing = "; ".join(f"{a['doctor']} on {a['when']}" for a in mine["appointments"])
        return (
            f"Your upcoming appointments: {listing}. "
            "Reply 'cancel confirm' to cancel the first one, or contact reception to reschedule."
        )

    info_words = (
        "hour", "timing", "open", "close", "location",
        "address", "parking", "fee", "cost", "charge",
    )
    if any(w in lowered for w in info_words):
        info = await TOOL_HANDLERS["get_clinic_info"](db, patient, {})
        if info.get("error"):
            return info["error"]
        return (
            f"🏥 {info['name']}\n📍 {info['address']}\n🕘 Hours: {info['hours']}\n"
            f"🅿 {info['parking']}\n💳 Consultation fee: {info['consultation_fee']}\n"
            f"📞 {info['phone']}"
        )

    if any(w in lowered for w in ("medicine", "medication", "prescri", "tablet", "dose")):
        meds = await TOOL_HANDLERS["get_my_medications"](db, patient, {})
        if not meds["medications"]:
            return "I don't see any active prescriptions for you. The care team can confirm."
        listing = "\n".join(
            f"• {m['name']} {m['dosage']} at {', '.join(m['times'])} (until {m['until']})"
            for m in meds["medications"]
        )
        return f"Your current medications:\n{listing}"

    if any(w in lowered for w in ("done", "taken", "took it")):
        result = await TOOL_HANDLERS["log_medication_taken"](db, patient, {})
        if result.get("logged"):
            return "Great, logged it ✅ Keep it up!"
        return result.get("note", "Noted!")

    pain_match = re.search(r"\b([0-9]|10)\b\s*(/|out of)?\s*(10)?", lowered)
    if any(w in lowered for w in ("pain", "hurt")) and pain_match:
        result = await TOOL_HANDLERS["log_pain_level"](
            db, patient, {"level": int(pain_match.group(1)), "context": text}
        )
        if result.get("logged"):
            return (
                f"Recorded pain level {result['pain_level']}/10. "
                "The care team tracks this daily — thank you!"
            )
        return result.get("note", "Noted your pain level, thank you.")

    if any(w in lowered for w in ("wait", "queue", "how long")):
        queue = await TOOL_HANDLERS["get_queue_status"](db, patient, {})
        if queue.get("error"):
            return queue["error"]
        return (
            f"There are {queue['patients_ahead']} patients ahead of you. "
            f"Estimated wait: {queue['estimated_wait_minutes']} minutes."
        )

    knowledge = await TOOL_HANDLERS["search_clinic_knowledge"](db, patient, {"query": text})
    if knowledge.get("entries"):
        top = knowledge["entries"][0]
        return (
            f"{top['content']}\n\n"
            "(For anything specific to your case, the care team will confirm.)"
        )

    return _fallback_generic()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _merge_history(history: list[dict]) -> list[dict]:
    """Anthropic requires alternating roles — merge consecutive same-role turns."""
    merged: list[dict] = []
    for turn in history:
        if merged and merged[-1]["role"] == turn["role"]:
            merged[-1] = {
                "role": turn["role"],
                "content": f"{merged[-1]['content']}\n{turn['content']}",
            }
        else:
            merged.append(dict(turn))
    # Conversation must start with a user turn.
    while merged and merged[0]["role"] != "user":
        merged.pop(0)
    return merged


async def generate_agent_reply(
    db: AsyncSession, patient: User, history: list[dict]
) -> str:
    """Full agent pipeline. `history` = [{"role", "content"}], newest last."""
    history = _merge_history(history)
    latest = history[-1]["content"] if history else ""

    emergency = detect_emergency(latest)
    if emergency.detected:
        return await raise_escalation(db, patient, latest, emergency)

    profile = await db.get(PatientProfile, patient.id)
    default_lang = profile.preferred_language if profile else "en"
    language = detect_language(latest, default=default_lang)
    if profile and language != profile.preferred_language:
        profile.preferred_language = language
        await db.commit()

    if not settings.anthropic_api_key:
        return await _fallback_route(db, patient, latest)

    try:
        return await _agent_loop(db, patient, history, language)
    except Exception:
        logger.warning("Agent loop failed; using fallback router", exc_info=True)
        return await _fallback_route(db, patient, latest)


