"""Outbound notification primitives used by scheduled Celery tasks.

All delivery currently lands in the in-app chat (Message rows). The WhatsApp
Business adapter will plug into ``send_system_message`` later without the
tasks needing to change.
"""

import logging
import uuid

from sqlalchemy.orm import Session

from src.models import Message
from src.models.message import MessageChannel

logger = logging.getLogger("healflow.notify")

# Fixed assistant identity (same value as src.ai.ASSISTANT_USER_ID, kept local
# so Celery workers don't import the async AI stack).
ASSISTANT_USER_ID = uuid.UUID("00000000-0000-4000-8000-00000000a1a1")


def send_system_message(db: Session, patient_id: uuid.UUID, body: str) -> Message:
    """Insert a system chat message authored by the assistant user.

    ``patient_id`` selects the recipient; the Message row itself has no
    recipient column (conversations are per-patient), but the id is needed
    to route the outbound delivery.

    TODO: hook the WhatsApp adapter here — look up the patient's
    ``PatientProfile.whatsapp_number`` via ``patient_id`` and send through the
    WhatsApp Business API in addition to the chat row.
    """
    message = Message(
        sender_id=ASSISTANT_USER_ID,
        conversation_user_id=patient_id,
        channel=MessageChannel.CHAT,
        body=body,
    )
    db.add(message)
    logger.info("system message queued for patient %s", patient_id)
    return message


def notify_clinic(db: Session, clinic_id: uuid.UUID, text: str) -> None:
    """Notify clinic staff about a patient issue.

    TODO: replace logging with a real staff notification channel
    (dashboard alert / staff WhatsApp group / email digest).
    """
    logger.warning("clinic %s notification: %s", clinic_id, text)
