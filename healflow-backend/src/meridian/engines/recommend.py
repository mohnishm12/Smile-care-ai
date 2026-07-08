"""L7 — Recommendation Engine.

Pure: read-model rows (recovery, risk) × trust tiers → Recommendations.
Every Recommendation carries evidence, rules, model id, confidence, tier,
recommended action, and ignore-consequence — the nine Brief questions
(implementation directive) are answerable from this object alone.

Kernel v1 is rules-only: model_id = "rules/1.0"; confidence is rule-assigned.
An LLM participant later ADDs recommendations through the same shape — it
never replaces this path.
"""

from datetime import datetime

from sqlalchemy.engine import Connection

from src.meridian.engines.trust import tier_for

MODEL_ID = "rules/1.0"

# hazard → (action_class, action, ignore_consequence, confidence)
PLAYBOOK: dict[str, dict] = {
    "deterioration": {
        "action_class": "scheduling.book",
        "action": "book_review_appointment",
        "summary": "Recovery deteriorating — bring the patient in for review",
        "if_ignored": "Symptoms may worsen unmonitored; risk of complication and emergency visit",
        "confidence": 0.9,
    },
    "red_flag_symptom": {
        "action_class": "comms.clinical_reply",
        "action": "draft_symptom_outreach",
        "summary": "Red-flag symptom reported — clinician outreach needed",
        "if_ignored": "Potentially serious symptom goes unassessed",
        "confidence": 0.85,
    },
    "unacknowledged_escalation": {
        "action_class": "ops.acknowledge_escalation",
        "action": "acknowledge_escalation",
        "summary": "Escalation awaiting acknowledgement",
        "if_ignored": "SLA breach; patient in a flagged state with no human owner",
        "confidence": 1.0,
    },
    "disengagement": {
        "action_class": "comms.routine_reply",
        "action": "send_reengagement_checkin",
        "summary": "Patient stopped answering check-ins — re-engage",
        "if_ignored": "Recovery becomes unmonitored; silent deterioration possible",
        "confidence": 0.75,
    },
    "awaiting_reply": {
        "action_class": "comms.routine_reply",
        "action": "draft_reply",
        "summary": "Patient message awaiting a reply",
        "if_ignored": "Patient left waiting; trust and responsiveness degrade",
        "confidence": 0.8,
    },
}


def build(
    conn: Connection,
    *,
    tenant_id: str,
    risks: list[dict],
    recovery_by_stream: dict[str, dict],
    as_of: datetime,
) -> list[dict]:
    """risks: rows from rm_risk (stream_id, hazard, level, basis).
    recovery_by_stream: stream_id → rm_recovery row dict (or absent)."""
    recommendations: list[dict] = []
    for risk in risks:
        play = PLAYBOOK.get(risk["hazard"])
        if play is None:
            continue
        trust = tier_for(conn, tenant_id, play["action_class"], as_of)
        recovery = recovery_by_stream.get(risk["stream_id"])
        evidence = sorted(
            {eid for basis in risk["basis"] for eid in basis["evidence"]}
        )
        recommendations.append(
            {
                # deterministic identity: one recommendation per stream × hazard
                "decision_id": f"{risk['stream_id']}|{risk['hazard']}",
                "stream_id": risk["stream_id"],
                "hazard": risk["hazard"],
                "level": risk["level"],
                "summary": play["summary"],
                "why": [basis["rule"] for basis in risk["basis"]],
                "evidence": evidence,
                "rules_fired": [basis["rule"] for basis in risk["basis"]],
                "model_id": MODEL_ID,
                "confidence": play["confidence"],
                "trust": {
                    "action_class": play["action_class"],
                    "tier": trust["effective"],
                    "lb": trust["lb"],
                    "n": trust["n"],
                },
                "recommended_action": {
                    "action": play["action"],
                    "action_class": play["action_class"],
                    "tier": trust["effective"],
                },
                "if_ignored": play["if_ignored"],
                "recovery_score": recovery["score"] if recovery else None,
                "recovery_components": recovery["components"] if recovery else [],
            }
        )
    return recommendations
