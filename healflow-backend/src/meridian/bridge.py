"""Domain → Meridian event bridge.

The kernel (store → projectors → engines → brief) is the single source of
ranking/recovery/trust logic. In the running product the live domain tables
(escalations, follow-up check-ins, messages, ledger) are the system of record,
not yet the event store. This bridge projects the current domain state for one
clinic into the kernel's event store, replays, and returns ranked Decisions.

Regeneration is a full rebuild of this tenant's kernel state — deterministic
and replay-identical (the milestone law still holds). At clinic scale this is
cheap and keeps ONE implementation of every calculation.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.meridian.brief import default_registry, generate_brief
from src.meridian.store import append

RUNTIME_ACTOR = {"kind": "runtime", "id": "meridian"}
PATIENT_ACTOR = {"kind": "patient", "id": "self"}
ASSISTANT_ID = "00000000-0000-4000-8000-00000000a1a1"


def _stream(patient_id: str, tenant_id: str) -> str:
    return f"patient-{patient_id}-{tenant_id}"


def _wipe_tenant(conn: Connection, tenant_id: str) -> None:
    for table in ("rm_decisions", "rm_trust", "rm_risk", "rm_recovery",
                  "meridian_applied", "meridian_checkpoints"):
        conn.execute(
            text(f"DELETE FROM healflow.{table} WHERE tenant_id = :t")
            if table in ("rm_decisions", "rm_trust", "rm_risk", "rm_recovery")
            else text(f"DELETE FROM healflow.{table}"),
            {"t": tenant_id},
        )
    conn.execute(
        text("DELETE FROM healflow.meridian_events WHERE tenant_id = :t"),
        {"t": tenant_id},
    )


def _emit(conn: Connection, stream: str, tenant: str, type_: str,
          payload: dict, at: datetime, actor: dict) -> None:
    append(
        conn, stream_id=stream, tenant_id=tenant, type_=type_,
        payload=payload, actor=actor, occurred_at=at, recorded_at=at,
    )


def ingest_tenant(conn: Connection, tenant_id: str, clinic_id: str) -> None:
    """Emit kernel events from the clinic's live domain rows."""
    _wipe_tenant(conn, tenant_id)

    # Follow-up plans + check-ins → recovery/deterioration signal.
    plans = conn.execute(
        text(
            "SELECT id, patient_id, treatment, start_date "
            "FROM healflow.followup_plans WHERE clinic_id = :c AND is_active"
        ),
        {"c": clinic_id},
    ).fetchall()
    for plan in plans:
        stream = _stream(str(plan.patient_id), tenant_id)
        base = datetime.combine(plan.start_date, datetime.min.time(), tzinfo=UTC)
        _emit(conn, stream, tenant_id, "FollowUpPlanStarted",
              {"treatment": plan.treatment}, base, RUNTIME_ACTOR)
        checkins = conn.execute(
            text(
                "SELECT day_number, pain_level, symptoms, asked_at, responded_at "
                "FROM healflow.followup_checkins WHERE plan_id = :p "
                "ORDER BY day_number"
            ),
            {"p": str(plan.id)},
        ).fetchall()
        for ci in checkins:
            asked_at = ci.asked_at or base
            _emit(conn, stream, tenant_id, "CheckinAsked",
                  {"day": ci.day_number}, asked_at, RUNTIME_ACTOR)
            if ci.responded_at is not None:
                _emit(
                    conn, stream, tenant_id, "CheckinAnswered",
                    {"day": ci.day_number, "pain": ci.pain_level,
                     "symptoms": ci.symptoms or {}},
                    ci.responded_at, PATIENT_ACTOR,
                )

    # Unacknowledged escalations.
    escalations = conn.execute(
        text(
            "SELECT patient_id, severity, reason, created_at, acknowledged "
            "FROM healflow.escalations WHERE clinic_id = :c ORDER BY created_at"
        ),
        {"c": clinic_id},
    ).fetchall()
    for esc in escalations:
        stream = _stream(str(esc.patient_id), tenant_id)
        raised = _find_or_make_raise(conn, stream, tenant_id, esc)
        if esc.acknowledged:
            _emit(conn, stream, tenant_id, "EscalationAcknowledged",
                  {"escalation_event_id": raised}, esc.created_at, RUNTIME_ACTOR)

    # Unanswered patient messages (awaiting reply).
    convos = conn.execute(
        text(
            """
            SELECT m.conversation_user_id AS pid, m.sender_id, m.created_at
            FROM healflow.messages m
            JOIN healflow.patient_profiles p ON p.user_id = m.conversation_user_id
            WHERE p.clinic_id = :c OR p.clinic_id IS NULL
            ORDER BY m.created_at
            """
        ),
        {"c": clinic_id},
    ).fetchall()
    for row in convos:
        if row.pid is None:
            continue
        stream = _stream(str(row.pid), tenant_id)
        if str(row.sender_id) == str(row.pid):
            _emit(conn, stream, tenant_id, "MessageReceived", {},
                  row.created_at, PATIENT_ACTOR)
        else:
            _emit(conn, stream, tenant_id, "MessageAnswered", {},
                  row.created_at, RUNTIME_ACTOR)


def _find_or_make_raise(conn: Connection, stream: str, tenant: str, esc) -> str:
    event = append(
        conn, stream_id=stream, tenant_id=tenant, type_="EscalationRaised",
        payload={"severity": esc.severity, "reason": esc.reason},
        actor=RUNTIME_ACTOR, occurred_at=esc.created_at, recorded_at=esc.created_at,
    )
    return str(event.event_id)


def refresh_brief(conn: Connection, tenant_id: str, clinic_id: str,
                  as_of: datetime | None = None) -> list[dict]:
    """Full rebuild: ingest domain → replay kernel → ranked Decisions."""
    ingest_tenant(conn, tenant_id, clinic_id)
    registry = default_registry()
    registry.replay_all(conn, tenant_id=tenant_id)
    return generate_brief(
        conn, tenant_id=tenant_id, as_of=as_of or datetime.now(UTC)
    )


def read_brief(conn: Connection, tenant_id: str) -> list[dict]:
    """Return the last generated Decisions without rebuilding."""
    rows = conn.execute(
        text(
            "SELECT body FROM healflow.rm_decisions "
            "WHERE tenant_id = :t ORDER BY rank"
        ),
        {"t": tenant_id},
    ).fetchall()
    return [r.body for r in rows]


def tenant_for_clinic(clinic_id: uuid.UUID) -> str:
    return f"clinic-{clinic_id}"
