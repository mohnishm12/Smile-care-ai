"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  CheckinEntry,
  PatientTimeline,
  StaffAppointment,
  getPatientTimeline,
  listTodaysAppointments,
} from "@/lib/api";
import StaffNav from "../StaffNav";

// Inline SVG line chart: day_number (x) vs pain_level (y, 0-10 scale).
function PainTrendChart({ checkins }: { checkins: CheckinEntry[] }) {
  const points = [...checkins].sort((a, b) => a.day_number - b.day_number);
  if (points.length === 0) {
    return <p className="muted">No check-in data yet.</p>;
  }

  const width = 340;
  const height = 170;
  const pad = { top: 12, right: 12, bottom: 26, left: 28 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const maxPain = 10;
  const minDay = points[0].day_number;
  const maxDay = points[points.length - 1].day_number;
  const daySpan = Math.max(maxDay - minDay, 1);

  const x = (day: number) => pad.left + ((day - minDay) / daySpan) * plotW;
  const y = (pain: number) =>
    pad.top + (1 - Math.min(Math.max(pain, 0), maxPain) / maxPain) * plotH;

  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.day_number)},${y(p.pain_level)}`)
    .join(" ");

  return (
    <svg
      className="pain-chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Pain level by recovery day"
    >
      {[0, 5, 10].map((lvl) => (
        <g key={lvl}>
          <line
            x1={pad.left}
            y1={y(lvl)}
            x2={width - pad.right}
            y2={y(lvl)}
            stroke="var(--border)"
            strokeWidth="1"
          />
          <text
            x={pad.left - 6}
            y={y(lvl) + 3}
            textAnchor="end"
            fontSize="9"
            fill="var(--text-muted)"
          >
            {lvl}
          </text>
        </g>
      ))}
      {points.length > 1 && (
        <path d={path} fill="none" stroke="var(--primary)" strokeWidth="2" />
      )}
      {points.map((p) => (
        <circle
          key={p.day_number}
          cx={x(p.day_number)}
          cy={y(p.pain_level)}
          r="3"
          fill="var(--primary)"
        />
      ))}
      {points.map((p) => (
        <text
          key={`d${p.day_number}`}
          x={x(p.day_number)}
          y={height - 8}
          textAnchor="middle"
          fontSize="9"
          fill="var(--text-muted)"
        >
          D{p.day_number}
        </text>
      ))}
    </svg>
  );
}

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

export default function DoctorDashboard() {
  const router = useRouter();
  const [appointments, setAppointments] = useState<StaffAppointment[] | null>(
    null,
  );
  const [listError, setListError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<PatientTimeline | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  const handleAuthError = useCallback(
    (err: unknown): boolean => {
      if (err instanceof ApiError && err.status === 401) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        router.replace("/login");
        return true;
      }
      return false;
    },
    [router],
  );

  useEffect(() => {
    if (!localStorage.getItem("access_token")) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        setAppointments(await listTodaysAppointments());
      } catch (err) {
        if (handleAuthError(err)) return;
        setAppointments([]);
        setListError("Failed to load today's appointments.");
      }
    })();
  }, [router, handleAuthError]);

  async function openPatient(appt: StaffAppointment) {
    // Prefer the explicit patient id when the backend provides it; fall back
    // to the appointment id otherwise.
    const patientId = appt.patient_id ?? appt.id;
    setSelectedId(patientId);
    setTimeline(null);
    setTimelineError(null);
    setTimelineLoading(true);
    try {
      setTimeline(await getPatientTimeline(patientId));
    } catch (err) {
      if (handleAuthError(err)) return;
      setTimelineError("Failed to load patient timeline.");
    } finally {
      setTimelineLoading(false);
    }
  }

  return (
    <main className="container-wide">
      <StaffNav />
      <h1>Doctor dashboard</h1>

      <div className="dash-grid">
        <section>
          <h2 className="section-title">Today&apos;s patients</h2>
          {appointments === null && !listError && (
            <p className="muted">Loading patients…</p>
          )}
          {listError && <p className="error">{listError}</p>}
          {appointments !== null &&
            appointments.length === 0 &&
            !listError && (
              <p className="muted">No patients scheduled for today.</p>
            )}
          <div className="patient-list">
            {(appointments ?? []).map((a) => {
              const pid = a.patient_id ?? a.id;
              return (
                <button
                  key={a.id}
                  type="button"
                  className={`patient-item${pid === selectedId ? " selected" : ""}`}
                  onClick={() => openPatient(a)}
                >
                  <strong>{a.patient_name}</strong>
                  <span className="muted">
                    {" · "}
                    {new Date(a.scheduled_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                    {" · "}
                    {a.status}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="card">
          {!selectedId && (
            <p className="muted">Select a patient to view their timeline.</p>
          )}
          {timelineLoading && <p className="muted">Loading timeline…</p>}
          {timelineError && <p className="error">{timelineError}</p>}

          {timeline && (
            <>
              <h2 className="section-title">
                {timeline.patient.full_name}{" "}
                <span className="muted">({timeline.patient.email})</span>
              </h2>

              <div className="timeline-section">
                <h3 className="section-title">Pain trend</h3>
                <PainTrendChart checkins={timeline.checkins} />
              </div>

              <div className="timeline-section">
                <h3 className="section-title">Medication adherence</h3>
                <AdherenceBar
                  taken={timeline.medication_adherence.taken}
                  missed={timeline.medication_adherence.missed}
                  pending={timeline.medication_adherence.pending}
                />
              </div>

              <div className="timeline-section">
                <h3 className="section-title">Escalations</h3>
                {timeline.escalations.length === 0 && (
                  <p className="muted">No escalations 🎉</p>
                )}
                {timeline.escalations.length > 0 && (
                  <div className="esc-list">
                    {timeline.escalations.map((e) => (
                      <div key={e.id} className={`esc-item ${e.severity}`}>
                        <div className="esc-head">
                          <span className={`badge ${e.severity}`}>
                            {e.severity}
                          </span>
                          <span className="muted">
                            {new Date(e.created_at).toLocaleString()}
                          </span>
                          {e.acknowledged && (
                            <span className="badge ack">Acknowledged</span>
                          )}
                        </div>
                        <div>{e.reason}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="timeline-section">
                <h3 className="section-title">Recent conversation</h3>
                {timeline.recent_messages.length === 0 && (
                  <p className="muted">No recent messages.</p>
                )}
                {timeline.recent_messages.map((m, i) => (
                  <div key={`${m.created_at}-${i}`} className="msg-excerpt">
                    <span className="who">
                      {m.from_assistant ? "HealFlow Assistant" : "Patient"}
                    </span>
                    {m.body}
                    <time className="muted" style={{ display: "block" }}>
                      {new Date(m.created_at).toLocaleString()}
                    </time>
                  </div>
                ))}
              </div>

              <div className="timeline-section">
                <h3 className="section-title">Appointment history</h3>
                {timeline.appointments.length === 0 && (
                  <p className="muted">No past appointments.</p>
                )}
                {timeline.appointments.length > 0 && (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Doctor</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {timeline.appointments.map((a) => (
                        <tr key={a.id}>
                          <td>{new Date(a.scheduled_at).toLocaleString()}</td>
                          <td>{a.doctor_name}</td>
                          <td>{a.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
