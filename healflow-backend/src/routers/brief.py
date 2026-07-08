"""Morning Brief API — the product surface.

Returns ranked Decisions for the clinic: who needs a human, in what order,
with evidence, the recommended action, its trust tier, and the cost of
ignoring it. Actions execute through the existing agent tools + reception
handlers (single implementation), then the brief is refreshed.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database import get_db
from src.deps import get_current_user
from src.meridian.bridge import refresh_brief, tenant_for_clinic
from src.models.care import Escalation
from src.models.clinic import Clinic
from src.models.user import User
from src.routers.messages import STAFF_ROLES

settings = get_settings()
router = APIRouter(tags=["brief"])
logger = logging.getLogger("healflow.brief")


class BriefResponse(BaseModel):
    greeting: str
    attention_count: int
    decisions: list[dict]
    generated_at: datetime


async def _staff(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in STAFF_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Staff access required")
    return current_user


async def _active_clinic(db: AsyncSession) -> Clinic:
    clinic = (
        await db.execute(select(Clinic).where(Clinic.is_active).limit(1))
    ).scalar_one_or_none()
    if clinic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No clinic configured")
    return clinic


def _greeting(name: str, now: datetime) -> str:
    hour = now.hour
    part = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
    first = name.split()[0] if name else "there"
    return f"Good {part}, {first}."


def _generate_sync(tenant_id: str, clinic_id: str) -> list[dict]:
    """Kernel replay is synchronous SQLAlchemy — run it on a sync engine."""
    engine = create_engine(settings.database_sync_url)
    try:
        with engine.begin() as conn:
            return refresh_brief(conn, tenant_id, clinic_id)
    finally:
        engine.dispose()


@router.get("/api/brief", response_model=BriefResponse)
async def get_brief(
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(_staff),
) -> BriefResponse:
    clinic = await _active_clinic(db)
    tenant_id = tenant_for_clinic(clinic.id)
    import anyio

    decisions = await anyio.to_thread.run_sync(
        _generate_sync, tenant_id, str(clinic.id)
    )
    now = datetime.now(UTC)
    return BriefResponse(
        greeting=_greeting(staff.full_name, now),
        attention_count=len(decisions),
        decisions=decisions,
        generated_at=now,
    )


class ActOnDecision(BaseModel):
    decision_id: str
    action: str


@router.post("/api/brief/act")
async def act_on_decision(
    payload: ActOnDecision,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(_staff),
) -> dict:
    """Execute a decision's recommended action. Records the human approval;
    the specific effect runs through existing handlers.

    decision_id is `{stream_id}|{hazard}`; stream is patient-{uid}-{tenant}.
    """
    stream_id = payload.decision_id.split("|", 1)[0]
    # stream_id = "patient-{uuid}-clinic-{uuid}" — the patient uuid is the
    # 36 chars between the "patient-" prefix and "-clinic-".
    try:
        middle = stream_id.split("patient-", 1)[1].split("-clinic-", 1)[0]
        patient_uuid = uuid.UUID(middle)
    except (ValueError, IndexError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad decision id") from exc

    action = payload.action
    result: dict = {"executed": action}

    if action == "acknowledge_escalation":
        esc = (
            await db.execute(
                select(Escalation)
                .where(
                    Escalation.patient_id == patient_uuid,
                    Escalation.acknowledged.is_(False),
                )
                .order_by(Escalation.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if esc:
            esc.acknowledged = True
            await db.commit()
            result["acknowledged"] = str(esc.id)
    else:
        # book_review_appointment, draft_symptom_outreach, send_reengagement,
        # draft_reply — these open work for the human; log the approval.
        logger.info(
            "Decision %s action %s approved by %s for patient %s",
            payload.decision_id, action, staff.email, patient_uuid,
        )
        result["logged"] = True

    return result
