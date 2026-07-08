"""L8 — Decision Ranking Engine (architecture §6.3).

Pure function: recommendations × as_of → ordered decision list. Transparent
weighted scoring; every rank carries its arithmetic ("why ranked here").
THE only ranking implementation.
"""

from datetime import datetime

RANKING_VERSION = "ranking/1.0"

SEVERITY_BASE = {"critical": 1000.0, "high": 400.0, "watch": 120.0, "none": 0.0}

# Hard law: unacknowledged critical escalations always rank first.
ABSOLUTE_FIRST = ("unacknowledged_escalation", "critical")


def _patient_risk_bonus(recovery_score: int | None) -> float:
    if recovery_score is None:
        return 0.0
    return max(0.0, (70 - recovery_score) * 2.0)


def rank(recommendations: list[dict], as_of: datetime) -> list[dict]:
    ranked: list[dict] = []
    for rec in recommendations:
        base = SEVERITY_BASE.get(rec["level"], 0.0)
        risk_bonus = _patient_risk_bonus(rec.get("recovery_score"))
        absolute = (rec["hazard"], rec["level"]) == ABSOLUTE_FIRST
        priority = (10**9 if absolute else 0) + base + risk_bonus
        ranked.append(
            {
                **rec,
                "priority": round(priority, 4),
                "ranking": {
                    "version": RANKING_VERSION,
                    "severity_base": base,
                    "patient_risk_bonus": risk_bonus,
                    "absolute_first": absolute,
                    "as_of": as_of.isoformat(),
                },
            }
        )
    # Deterministic total order: priority desc, then stable key.
    ranked.sort(key=lambda r: (-r["priority"], r["decision_id"]))
    for position, rec in enumerate(ranked, start=1):
        rec["rank"] = position
    return ranked
