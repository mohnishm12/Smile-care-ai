"""L4 — Recovery Engine (v1: linear, explainable — architecture §3.5).

Implemented as a projector: the score is a pure fold over the patient stream,
so replay reproduces it exactly. Every component carries its evidence event
ids. THE only recovery implementation (constitution: no duplicates).
"""

import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.meridian.projector import Projector
from src.meridian.store import Event, read_stream

ENGINE_VERSION = "recovery/1.0"

HANDLED = frozenset(
    {
        "FollowUpPlanStarted",
        "CheckinAsked",
        "CheckinAnswered",
        "DoseReminded",
        "DoseTaken",
        "DoseMissed",
        "ObservationRecorded",
    }
)

# Penalty weights (protocol pack v1 — generic outpatient)
W_PAIN_LEVEL = 3        # per pain point above expected
W_PAIN_SLOPE = 6        # per point of rise between consecutive checkins
W_MISSED_DOSE = 4
W_UNANSWERED = 5        # asked but never answered
W_SYMPTOM = {"fever": 15, "bleeding": 15, "swelling": 8}
EXPECTED_PAIN_BY_DAY = {1: 5, 2: 4, 3: 3, 4: 2, 5: 2, 6: 1, 7: 1}


def compute(events: list[Event]) -> dict | None:
    """Pure fold: patient-stream events → {score, components, evidence}.

    Deterministic: no clock, no randomness, no IO.
    """
    plan_evidence: list[str] = []
    episode = ""
    checkins: list[tuple[int, int, str]] = []  # (day, pain, event_id)
    asked: dict[int, str] = {}
    answered_days: set[int] = set()
    missed: list[str] = []
    symptoms: list[tuple[str, str]] = []  # (symptom, event_id)

    for event in events:
        if event.type == "FollowUpPlanStarted":
            episode = event.payload.get("treatment", "")
            plan_evidence = [str(event.event_id)]
            checkins, asked, answered_days, missed, symptoms = [], {}, set(), [], []
        elif event.type == "CheckinAsked":
            asked[int(event.payload["day"])] = str(event.event_id)
        elif event.type == "CheckinAnswered":
            day = int(event.payload["day"])
            answered_days.add(day)
            if "pain" in event.payload and event.payload["pain"] is not None:
                checkins.append((day, int(event.payload["pain"]), str(event.event_id)))
            for symptom, present in (event.payload.get("symptoms") or {}).items():
                if present:
                    symptoms.append((symptom, str(event.event_id)))
        elif event.type == "DoseMissed":
            missed.append(str(event.event_id))
        elif event.type == "ObservationRecorded":
            kind = event.payload.get("kind")
            if kind in W_SYMPTOM:
                symptoms.append((str(kind), str(event.event_id)))

    if not plan_evidence:
        return None

    components: list[dict] = []
    evidence: list[str] = list(plan_evidence)

    checkins.sort(key=lambda c: c[0])
    for day, pain, event_id in checkins:
        expected = EXPECTED_PAIN_BY_DAY.get(day, 1)
        if pain > expected:
            delta = -W_PAIN_LEVEL * (pain - expected)
            components.append(
                {"kind": "pain_above_expected", "day": day, "delta": delta,
                 "evidence": [event_id]}
            )
            evidence.append(event_id)
    for (d1, p1, e1), (d2, p2, e2) in zip(checkins, checkins[1:], strict=False):
        if p2 > p1:
            delta = -W_PAIN_SLOPE * (p2 - p1)
            components.append(
                {"kind": "pain_rising", "from_day": d1, "to_day": d2,
                 "delta": delta, "evidence": [e1, e2]}
            )
            evidence.extend([e1, e2])

    unanswered = [eid for day, eid in asked.items() if day not in answered_days]
    if unanswered:
        components.append(
            {"kind": "checkins_unanswered", "count": len(unanswered),
             "delta": -W_UNANSWERED * len(unanswered), "evidence": unanswered}
        )
        evidence.extend(unanswered)

    if missed:
        components.append(
            {"kind": "doses_missed", "count": len(missed),
             "delta": -W_MISSED_DOSE * len(missed), "evidence": missed}
        )
        evidence.extend(missed)

    for symptom, event_id in symptoms:
        components.append(
            {"kind": f"symptom_{symptom}", "delta": -W_SYMPTOM[symptom],
             "evidence": [event_id]}
        )
        evidence.append(event_id)

    score = max(0, min(100, 100 + sum(c["delta"] for c in components)))
    return {
        "episode": episode,
        "score": score,
        "components": components,
        "evidence": sorted(set(evidence)),
    }


class RecoveryProjector(Projector):
    name = "recovery"
    handles = HANDLED
    owned_tables = ("rm_recovery",)

    def apply(self, conn: Connection, event: Event) -> None:
        result = compute(read_stream(conn, event.stream_id))
        if result is None:
            return
        conn.execute(
            text(
                "INSERT INTO healflow.rm_recovery "
                "(stream_id, tenant_id, episode, score, components, evidence,"
                " engine_version, computed_from_seq) "
                "VALUES (:sid, :tid, :ep, :score, CAST(:components AS jsonb),"
                " CAST(:evidence AS jsonb), :ver, :seq) "
                "ON CONFLICT (stream_id) DO UPDATE SET "
                "episode=:ep, score=:score, components=CAST(:components AS jsonb),"
                " evidence=CAST(:evidence AS jsonb), engine_version=:ver,"
                " computed_from_seq=:seq"
            ),
            {
                "sid": event.stream_id,
                "tid": event.tenant_id,
                "ep": result["episode"],
                "score": result["score"],
                "components": json.dumps(result["components"]),
                "evidence": json.dumps(result["evidence"]),
                "ver": ENGINE_VERSION,
                "seq": event.seq,
            },
        )
