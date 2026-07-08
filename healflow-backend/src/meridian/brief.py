"""L9 — Morning Brief assembly.

The Brief owns ZERO clinical logic (implementation directive). It:
  1. reads rm_risk and rm_recovery (never write models, never the raw stream),
  2. asks the Recommendation Engine for Recommendations,
  3. asks the Ranking Engine for order,
  4. persists the ranked Decisions to rm_decisions and returns them.

`as_of` is explicit — same stream + same as_of ⇒ byte-identical brief.
"""

import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.meridian.engines.ranking import rank
from src.meridian.engines.recommend import build
from src.meridian.engines.recovery import RecoveryProjector
from src.meridian.engines.risk import RiskProjector
from src.meridian.engines.trust import TrustProjector
from src.meridian.projector import Registry


def default_registry() -> Registry:
    registry = Registry()
    registry.register(RecoveryProjector())
    registry.register(RiskProjector())
    registry.register(TrustProjector())
    return registry


def generate_brief(conn: Connection, *, tenant_id: str, as_of: datetime) -> list[dict]:
    risk_rows = conn.execute(
        text(
            "SELECT stream_id, hazard, level, basis FROM healflow.rm_risk "
            "WHERE tenant_id = :tid ORDER BY stream_id, hazard"
        ),
        {"tid": tenant_id},
    ).fetchall()
    risks = [
        {"stream_id": r.stream_id, "hazard": r.hazard, "level": r.level, "basis": r.basis}
        for r in risk_rows
    ]

    recovery_rows = conn.execute(
        text(
            "SELECT stream_id, episode, score, components, evidence "
            "FROM healflow.rm_recovery WHERE tenant_id = :tid"
        ),
        {"tid": tenant_id},
    ).fetchall()
    recovery_by_stream = {
        r.stream_id: {
            "episode": r.episode,
            "score": r.score,
            "components": r.components,
            "evidence": r.evidence,
        }
        for r in recovery_rows
    }

    recommendations = build(
        conn,
        tenant_id=tenant_id,
        risks=risks,
        recovery_by_stream=recovery_by_stream,
        as_of=as_of,
    )
    decisions = rank(recommendations, as_of)

    conn.execute(
        text("DELETE FROM healflow.rm_decisions WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )
    for decision in decisions:
        conn.execute(
            text(
                "INSERT INTO healflow.rm_decisions "
                "(decision_id, tenant_id, as_of, rank, priority, body) "
                "VALUES (:did, :tid, :as_of, :rank, :priority, CAST(:body AS jsonb))"
            ),
            {
                "did": decision["decision_id"],
                "tid": tenant_id,
                "as_of": as_of,
                "rank": decision["rank"],
                "priority": decision["priority"],
                "body": json.dumps(decision, sort_keys=True),
            },
        )
    return decisions
