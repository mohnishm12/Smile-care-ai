"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AnalyticsOverview,
  ApiError,
  Escalation,
  StaffAppointment,
  getAnalyticsOverview,
  listEscalations,
  listTodaysAppointments,
} from "@/lib/api";
import StaffNav from "../StaffNav";

function formatRevenue(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${currency} ${amount}`;
  }
}

function formatPercent(value: number): string {
  // Rates may arrive as a fraction (0.82) or a percentage (82).
  const pct = value <= 1 ? value * 100 : value;
  return `${Math.round(pct)}%`;
}

export default function ReceptionDashboard() {
  const router = useRouter();
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [escalations, setEscalations] = useState<Escalation[] | null>(null);
  const [appointments, setAppointments] = useState<StaffAppointment[] | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
      const problems: string[] = [];
      const [ov, esc, appts] = await Promise.allSettled([
        getAnalyticsOverview(),
        listEscalations(),
        listTodaysAppointments(),
      ]);

      // A 403 means the signed-in account lacks a staff role — say so
      // plainly instead of a generic load failure.
      const forbidden = [ov, esc, appts].some(
        (r) =>
          r.status === "rejected" &&
          r.reason instanceof ApiError &&
          r.reason.status === 403,
      );
      if (forbidden) {
        setError(
          "This account doesn't have staff access. Sign in with a staff, " +
            "doctor, or clinic admin account to view the dashboard.",
        );
        setLoading(false);
        return;
      }

      if (ov.status === "fulfilled") setOverview(ov.value);
      else if (handleAuthError(ov.reason)) return;
      else problems.push("analytics overview");

      if (esc.status === "fulfilled") setEscalations(esc.value);
      else if (handleAuthError(esc.reason)) return;
      else problems.push("escalations");

      if (appts.status === "fulfilled") setAppointments(appts.value);
      else if (handleAuthError(appts.reason)) return;
      else problems.push("today's appointments");

      if (problems.length > 0) {
        setError(`Failed to load: ${problems.join(", ")}.`);
      }
      setLoading(false);
    })();
  }, [router, handleAuthError]);

  return (
    <main className="container-wide">
      <StaffNav />
      <h1>Reception dashboard</h1>

      {loading && <p className="muted">Loading dashboard…</p>}
      {error && <p className="error">{error}</p>}

      {overview && (
        <div className="stat-grid">
          <div className="stat-card">
            <div className="stat-value">{overview.todays_appointments}</div>
            <div className="stat-label">Today&apos;s appointments</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{overview.missed_appointments}</div>
            <div className="stat-label">Missed appointments</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">
              {formatRevenue(overview.revenue, overview.currency)}
            </div>
            <div className="stat-label">Revenue</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{overview.open_escalations}</div>
            <div className="stat-label">Open escalations</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">
              {overview.avg_rating !== null
                ? overview.avg_rating.toFixed(1)
                : "—"}
            </div>
            <div className="stat-label">Avg rating</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">
              {formatPercent(overview.followup_completion_rate)}
            </div>
            <div className="stat-label">Follow-up completion</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">
              {formatPercent(overview.response_rate)}
            </div>
            <div className="stat-label">Response rate</div>
          </div>
        </div>
      )}

      <section className="timeline-section">
        <h2 className="section-title">Escalations</h2>
        {escalations !== null && escalations.length === 0 && (
          <p className="muted">No escalations 🎉</p>
        )}
        {escalations !== null && escalations.length > 0 && (
          <div className="esc-list">
            {escalations.map((e) => (
              <div key={e.id} className={`esc-item ${e.severity}`}>
                <div className="esc-head">
                  <span className={`badge ${e.severity}`}>{e.severity}</span>
                  <strong>{e.patient_name}</strong>
                  <span className="muted">
                    {new Date(e.created_at).toLocaleString()}
                  </span>
                  {e.acknowledged && (
                    <span className="badge ack">Acknowledged</span>
                  )}
                </div>
                <div>{e.reason}</div>
                {e.trigger_text && (
                  <div className="muted">&ldquo;{e.trigger_text}&rdquo;</div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="timeline-section">
        <h2 className="section-title">Today&apos;s appointments</h2>
        {appointments !== null && appointments.length === 0 && (
          <p className="muted">No appointments scheduled for today.</p>
        )}
        {appointments !== null && appointments.length > 0 && (
          <div className="card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Patient</th>
                  <th>Doctor</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {appointments.map((a) => (
                  <tr key={a.id}>
                    <td>
                      {new Date(a.scheduled_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td>{a.patient_name}</td>
                    <td>{a.doctor_name}</td>
                    <td>{a.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
