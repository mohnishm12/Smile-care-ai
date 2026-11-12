"""L6 — Trust Engine (architecture §7).

Fold over Ledger events → per (tenant, action_class) outcome list (read
model), and a pure scoring function outcomes × as_of → tier. Wilson lower
bound (closed form, deterministic) + exponential time decay. Ceilings are
law (constitution §7): listed classes can never exceed their ceiling.
"""

import json
import math
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.meridian.projector import Projector
from src.meridian.store import Event

ENGINE_VERSION = "trust/1.0"

HANDLED = frozenset(
    {"ActionProposed", "ActionApproved", "ActionDenied", "ActionExecuted", "ActionUndone"}
)

TIERS = ("ASK", "DRAFT", "ACT")

# Permanent ceilings — never earnable past these (constitution §7 hard law).
CEILINGS: dict[str, str] = {
    "clinical.prescription": "DRAFT",
    "clinical.diagnosis_communication": "DRAFT",
    "clinical.note_draft": "DRAFT",
    "consent.decision": "ASK",
    "records.share": "DRAFT",
}

HALF_LIFE_DAYS = 90.0
PROMOTE_DRAFT_LB = 0.90
PROMOTE_DRAFT_N = 30.0
PROMOTE_ACT_LB = 0.97
PROMOTE_ACT_N = 100.0

# outcome kind → (success_weight, failure_weight)
OUTCOME_WEIGHTS: dict[str, tuple[float, float]] = {
    "approved_unedited": (1.0, 0.0),
    "approved_edited": (0.5, 0.0),
    "executed_clean": (1.0, 0.0),
    "denied": (0.0, 1.0),
    "undone": (0.0, 2.0),
    "incident": (0.0, 10.0),
}


def _decay(outcome_at: datetime, as_of: datetime) -> float:
    age_days = max(0.0, (as_of - outcome_at).total_seconds() / 86400.0)
    return math.pow(0.5, age_days / HALF_LIFE_DAYS)


def wilson_lower_bound(successes: float, total: float, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    p = successes / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, (centre - margin) / denom)


def score(outcomes: list[dict], as_of: datetime) -> dict:
    """Pure: outcome list × as_of → {tier, lb, n, incidents}."""
    successes = 0.0
    failures = 0.0
    incidents = 0
    for outcome in outcomes:
        weight_s, weight_f = OUTCOME_WEIGHTS.get(outcome["kind"], (0.0, 0.0))
        decay = _decay(datetime.fromisoformat(outcome["at"]), as_of)
        successes += weight_s * decay
        failures += weight_f * decay
        if outcome["kind"] == "incident":
            incidents += 1

    total = successes + failures
    lb = wilson_lower_bound(successes, total)
    if incidents > 0:
        tier = "ASK"
    elif lb >= PROMOTE_ACT_LB and total >= PROMOTE_ACT_N:
        tier = "ACT"
    elif lb >= PROMOTE_DRAFT_LB and total >= PROMOTE_DRAFT_N:
        tier = "DRAFT"
    else:
        tier = "ASK"
    return {"tier": tier, "lb": round(lb, 6), "n": round(total, 3), "incidents": incidents}


def effective_tier(action_class: str, computed_tier: str, enacted_tier: str | None) -> str:
    """Ceiling ∧ human enactment: computed is the *eligible* tier; the enacted
    tier (human-approved, from AutonomyTierChanged) is what applies; ceilings
    cap both. Kernel v1: enacted defaults to computed (single-operator mode)."""
    tier = enacted_tier or computed_tier
    ceiling = CEILINGS.get(action_class, "ACT")
    return tier if TIERS.index(tier) <= TIERS.index(ceiling) else ceiling


class TrustProjector(Projector):
    name = "trust"
    handles = HANDLED
    owned_tables = ("rm_trust",)

    def apply(self, conn: Connection, event: Event) -> None:
        kind: str | None = None
        if event.type == "ActionApproved":
            kind = ("approved_edited" if event.payload.get("edited") else "approved_unedited")
        elif event.type == "ActionDenied":
            kind = "denied"
        elif event.type == "ActionUndone":
            kind = "undone"
        elif event.type == "ActionExecuted":
            if event.payload.get("incident"):
                kind = "incident"
            elif event.payload.get("clean", True) and event.payload.get("tier") == "ACT":
                kind = "executed_clean"
        if kind is None:
            return

        action_class = event.payload["action_class"]
        row = conn.execute(
            text(
                "SELECT outcomes FROM healflow.rm_trust "
                "WHERE tenant_id = :tid AND action_class = :ac"
            ),
            {"tid": event.tenant_id, "ac": action_class},
        ).first()
        outcomes = list(row[0]) if row else []
        outcomes.append(
            {
                "kind": kind,
                "at": event.occurred_at.isoformat(),
                "evidence": str(event.event_id),
            }
        )
        conn.execute(
            text(
                "INSERT INTO healflow.rm_trust (tenant_id, action_class, outcomes, engine_version) "
                "VALUES (:tid, :ac, CAST(:outcomes AS jsonb), :ver) "
                "ON CONFLICT (tenant_id, action_class) DO UPDATE "
                "SET outcomes = CAST(:outcomes AS jsonb), engine_version = :ver"
            ),
            {
                "tid": event.tenant_id,
                "ac": action_class,
                "outcomes": json.dumps(outcomes),
                "ver": ENGINE_VERSION,
            },
        )


def tier_for(conn: Connection, tenant_id: str, action_class: str, as_of: datetime) -> dict:
    """THE trust lookup (single implementation, constitution law)."""
    row = conn.execute(
        text(
            "SELECT outcomes FROM healflow.rm_trust "
            "WHERE tenant_id = :tid AND action_class = :ac"
        ),
        {"tid": tenant_id, "ac": action_class},
    ).first()
    outcomes = list(row[0]) if row else []
    result = score(outcomes, as_of)
    result["effective"] = effective_tier(action_class, result["tier"], None)
    result["action_class"] = action_class
    result["evidence"] = [o["evidence"] for o in outcomes]
    return result
