"use client";

import { useState } from "react";
import { PatientTimeline } from "@/lib/api";

function AdherenceBar({
  taken,
  missed,
  pending,
}: {
  taken: number;
  missed: number;
  pending: number;
}) {
  const total = taken + missed + pending;
  if (total === 0) {
    return <p className="muted">No medication schedule recorded.</p>;
  }
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <>
      <div
        className="adherence-bar"
        role="img"
        aria-label={`Medication adherence: ${taken} taken, ${missed} missed, ${pending} pending`}
      >
        {taken > 0 && <span className="taken" style={{ width: pct(taken) }} />}
        {missed > 0 && (
          <span className="missed" style={{ width: pct(missed) }} />
        )}
        {pending > 0 && (
          <span className="pending" style={{ width: pct(pending) }} />
        )}
      </div>
      <div className="legend">
        <span>
          <span className="dot" style={{ background: "#16a34a" }} />
          Taken {taken}
        </span>
        <span>
          <span className="dot" style={{ background: "var(--danger)" }} />
          Missed {missed}
        </span>
        <span>
          <span className="dot" style={{ background: "#d1d5db" }} />
          Pending {pending}
        </span>
      </div>
    </>
  );
}

export default function ContextPanel({
  timeline,
  loading,
  error,
  highPriority,
  aiPaused,
  onAck,
  onTakeover,
  onResume,
}: {
  timeline: PatientTimeline | null;
  loading: boolean;
  error: string | null;
  highPriority: boolean;
  aiPaused: boolean;
  onAck: (escalationId: string) => Promise<void>;
  onTakeover: () => void;
  onResume: () => void;
}) {
  const [ackingId, setAckingId] = useState<string | null>(null);

  if (loading) {
    return (
      <aside className="context-pane">
        <p className="muted ws-pad">Loading patient context…</p>
      </aside>
    );
  }
  if (error) {
    return (
      <aside className="context-pane">
        <p className="error ws-pad">{error}</p>
      </aside>
    );
  }
  if (!timeline) {
    return (
      <aside className="context-pane">
        <p className="muted ws-pad">
          Patient context — appointments, adherence, and escalations — shows
          here once you pick a conversation.
        </p>
      </aside>
    );
  }

  const now = Date.now();
  const upcoming = timeline.appointments
    .filter((a) => new Date(a.scheduled_at).getTime() >= now)
    .sort(
      (a, b) =>
        new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime(),
    )
    .slice(0, 3);
  const recentCheckins = [...timeline.checkins]
    .sort((a, b) => b.day_number - a.day_number)
    .slice(0, 5);
  const openEscalations = timeline.escalations.filter((e) => !e.acknowledged);

  async function ack(id: string) {
    setAckingId(id);
    await onAck(id);
    setAckingId(null);
  }

  return (
    <aside className="context-pane">
      <div className="context-head">
        <strong>{timeline.patient.full_name}</strong>
        {highPriority && <span className="chip priority">High priority</span>}
      </div>
      <div className="muted context-email">{timeline.patient.email}</div>

      <div className="context-section">
        <h3 className="context-title">Upcoming appointments</h3>
        {upcoming.length === 0 && (
          <p className="muted">No upcoming appointments booked.</p>
        )}
        {upcoming.map((a) => (
          <div key={a.id} className="context-row">
            <span>
              {new Date(a.scheduled_at).toLocaleString([], {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
            <span className="muted">
              {a.doctor_name} · {a.status}
            </span>
          </div>
        ))}
      </div>

      <div className="context-section">
        <h3 className="context-title">Medication adherence</h3>
        <AdherenceBar
          taken={timeline.medication_adherence.taken}
          missed={timeline.medication_adherence.missed}
          pending={timeline.medication_adherence.pending}
        />
      </div>

      <div className="context-section">
        <h3 className="context-title">Recent check-ins</h3>
        {recentCheckins.length === 0 && (
          <p className="muted">No check-ins recorded yet.</p>
        )}
        {recentCheckins.map((c) => (
          <div key={c.day_number} className="context-row">
            <span>Day {c.day_number}</span>
            <span
              className={`pain-pill${c.pain_level >= 7 ? " severe" : c.pain_level >= 4 ? " moderate" : ""}`}
            >
              Pain {c.pain_level}/10
            </span>
          </div>
        ))}
      </div>

      <div className="context-section">
        <h3 className="context-title">Open escalations</h3>
        {openEscalations.length === 0 && (
          <p className="muted">No open escalations 🎉</p>
        )}
        {openEscalations.map((e) => (
          <div key={e.id} className={`esc-item ${e.severity}`}>
            <div className="esc-head">
              <span className={`badge ${e.severity}`}>{e.severity}</span>
              <span className="muted">
                {new Date(e.created_at).toLocaleString([], {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </div>
            <div>{e.reason}</div>
            <button
              type="button"
              className="ack-button"
              onClick={() => ack(e.id)}
              disabled={ackingId === e.id}
            >
              {ackingId === e.id ? "Acknowledging…" : "Acknowledge"}
            </button>
          </div>
        ))}
      </div>

      <div className="context-section">
        <h3 className="context-title">Quick actions</h3>
        <div className="qa-row">
          <button
            type="button"
            className="ghost-button"
            onClick={onTakeover}
            disabled={aiPaused}
          >
            Take over
          </button>
          <button
            type="button"
            className="ghost-button"
            onClick={onResume}
            disabled={!aiPaused}
          >
            Resume AI
          </button>
        </div>
      </div>
    </aside>
  );
}
