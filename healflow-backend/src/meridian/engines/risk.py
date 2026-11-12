"""L5 — Risk Engine.

Declarative rules over the stream + recovery read model → per-hazard Risk
levels with rule ids and evidence. THE only urgency source (no duplicates).
"""

import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.meridian.projector import Projector
from src.meridian.store import Event, read_stream

RULES_VERSION = "risk-rules/1.0"

HANDLED = frozenset(
    {
        "CheckinAnswered",
        "CheckinAsked",
        "ObservationRecorded",
        "EscalationRaised",
        "EscalationAcknowledged",
        "MessageReceived",
        "MessageAnswered",
    }
)

LEVELS = ("none", "watch", "high", "critical")


def _worse(a: str, b: str) -> str:
    return a if LEVELS.index(a) >= LEVELS.index(b) else b


def evaluate(events: list[Event]) -> list[dict]:
    """Pure rule evaluation: stream → [{hazard, level, basis}].

    Each basis entry: {rule, evidence: [event_id, ...]}.
    """
    pains: list[tuple[int, int, str]] = []
    asked: dict[int, str] = {}
    answered: set[int] = set()
    open_escalations: list[tuple[str, str]] = []  # (severity, event_id)
    acked: set[str] = set()
    unanswered_msgs: list[str] = []
    symptoms: list[tuple[str, str]] = []

    for event in events:
        if event.type == "CheckinAnswered":
            day = int(event.payload["day"])
            answered.add(day)
            if event.payload.get("pain") is not None:
                pains.append((day, int(event.payload["pain"]), str(event.event_id)))
            for symptom, present in (event.payload.get("symptoms") or {}).items():
                if present:
                    symptoms.append((symptom, str(event.event_id)))
        elif event.type == "CheckinAsked":
            asked[int(event.payload["day"])] = str(event.event_id)
        elif event.type == "ObservationRecorded":
            if event.payload.get("kind") in ("fever", "bleeding", "swelling"):
                symptoms.append((event.payload["kind"], str(event.event_id)))
        elif event.type == "EscalationRaised":
            open_escalations.append(
                (event.payload.get("severity", "high"), str(event.event_id))
            )
        elif event.type == "EscalationAcknowledged":
            acked.add(str(event.payload.get("escalation_event_id")))
        elif event.type == "MessageReceived":
            unanswered_msgs.append(str(event.event_id))
        elif event.type == "MessageAnswered":
            if unanswered_msgs:
                unanswered_msgs.pop(0)

    risks: dict[str, dict] = {}

    def raise_to(hazard: str, level: str, rule: str, evidence: list[str]) -> None:
        current = risks.setdefault(hazard, {"level": "none", "basis": []})
        current["level"] = _worse(current["level"], level)
        current["basis"].append({"rule": rule, "evidence": evidence})

    pains.sort(key=lambda p: p[0])
    for (_d1, p1, e1), (_d2, p2, e2) in zip(pains, pains[1:], strict=False):
        if p2 - p1 >= 2:
            raise_to("deterioration", "high", "pain_slope_ge_2", [e1, e2])
        elif p2 > p1:
            raise_to("deterioration", "watch", "pain_rising", [e1, e2])
    if pains and pains[-1][1] >= 8:
        raise_to("deterioration", "high", "pain_ge_8", [pains[-1][2]])

    for symptom, event_id in symptoms:
        level = "high" if symptom in ("fever", "bleeding") else "watch"
        raise_to("red_flag_symptom", level, f"symptom_{symptom}", [event_id])

    unresolved = [e for sev, e in open_escalations if e not in acked]
    critical_unresolved = [
        e for sev, e in open_escalations if e not in acked and sev == "critical"
    ]
    if critical_unresolved:
        raise_to("unacknowledged_escalation", "critical",
                 "critical_escalation_unacked", critical_unresolved)
    elif unresolved:
        raise_to("unacknowledged_escalation", "high",
                 "escalation_unacked", unresolved)

    missed_checkins = [eid for day, eid in asked.items() if day not in answered]
    if len(missed_checkins) >= 2:
        raise_to("disengagement", "watch", "checkins_unanswered_ge_2", missed_checkins)
    if unanswered_msgs:
        raise_to("awaiting_reply", "watch", "patient_message_unanswered",
                 unanswered_msgs)

    return [
        {"hazard": hazard, "level": data["level"], "basis": data["basis"]}
        for hazard, data in sorted(risks.items())
        if data["level"] != "none"
    ]


class RiskProjector(Projector):
    name = "risk"
    handles = HANDLED
    owned_tables = ("rm_risk",)

    def apply(self, conn: Connection, event: Event) -> None:
        conn.execute(
            text("DELETE FROM healflow.rm_risk WHERE stream_id = :sid"),
            {"sid": event.stream_id},
        )
        for risk in evaluate(read_stream(conn, event.stream_id)):
            conn.execute(
                text(
                    "INSERT INTO healflow.rm_risk "
                    "(stream_id, hazard, tenant_id, level, basis, rules_version) "
                    "VALUES (:sid, :hazard, :tid, :level, CAST(:basis AS jsonb), :ver)"
                ),
                {
                    "sid": event.stream_id,
                    "hazard": risk["hazard"],
                    "tid": event.tenant_id,
                    "level": risk["level"],
                    "basis": json.dumps(risk["basis"]),
                    "ver": RULES_VERSION,
                },
            )
