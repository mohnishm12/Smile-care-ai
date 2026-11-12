"use client";

import { useCountUp, useReveal } from "./lib";

interface BriefPatient {
  name: string;
  level: "red" | "amber" | "green";
  status: string;
  note: string;
}

const PATIENTS: BriefPatient[] = [
  {
    name: "Rahul Mehta",
    level: "red",
    status: "Recovery slowing",
    note: "Pain up 2 days running after extraction. Photo looks inflamed.",
  },
  {
    name: "Priya Nair",
    level: "amber",
    status: "Missed medication",
    note: "Skipped antibiotics twice. Nudged, no reply yet.",
  },
  {
    name: "Meera Iyer",
    level: "green",
    status: "Recovered",
    note: "Day 7 check-in clear. Closing the follow-up.",
  },
];

const RADIUS = 54;
const CIRC = 2 * Math.PI * RADIUS;
const TARGET = 87;

export default function MorningBrief() {
  const { ref, shown } = useReveal<HTMLDivElement>(0.35);
  const score = useCountUp(TARGET, shown);
  const offset = shown ? CIRC * (1 - TARGET / 100) : CIRC;

  return (
    <section className="mrd-section" id="brief">
      <div className="mrd-section-head">
        <p className="mrd-eyebrow">The Morning Brief</p>
        <h2 className="mrd-h2">
          No dashboards. Just the three patients who need you.
        </h2>
        <p className="mrd-lede">
          Every morning, Meridian ranks the whole panel and surfaces only what
          can&rsquo;t wait — with the reason it decided.
        </p>
      </div>

      <div className="mrd-brief" ref={ref}>
        <div className="mrd-brief-card">
          <div className="mrd-brief-cardhead">
            <span>Who needs you today</span>
            <span className="mrd-brief-date">Tue &middot; 3 flagged</span>
          </div>
          <ul className="mrd-brief-list">
            {PATIENTS.map((p, i) => (
              <li
                key={p.name}
                className={`mrd-brief-row mrd-reveal ${shown ? "in" : ""}`}
                style={{ transitionDelay: `${0.15 + i * 0.12}s` }}
              >
                <span className={`mrd-status-dot ${p.level}`} aria-hidden="true" />
                <span className="mrd-brief-main">
                  <span className="mrd-brief-name">{p.name}</span>
                  <span className="mrd-brief-note">{p.note}</span>
                </span>
                <span className={`mrd-brief-tag ${p.level}`}>{p.status}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="mrd-ring-card">
          <div className="mrd-ring" role="img" aria-label={`Recovery score ${TARGET} of 100`}>
            <svg viewBox="0 0 128 128" width="150" height="150">
              <defs>
                <linearGradient id="mrdRing" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="#34d3ee" />
                  <stop offset="100%" stopColor="#5b8bff" />
                </linearGradient>
              </defs>
              <circle
                cx="64"
                cy="64"
                r={RADIUS}
                className="mrd-ring-track"
                fill="none"
                strokeWidth="10"
              />
              <circle
                cx="64"
                cy="64"
                r={RADIUS}
                className="mrd-ring-value"
                fill="none"
                strokeWidth="10"
                strokeLinecap="round"
                stroke="url(#mrdRing)"
                strokeDasharray={CIRC}
                strokeDashoffset={offset}
                transform="rotate(-90 64 64)"
              />
            </svg>
            <div className="mrd-ring-center">
              <span className="mrd-ring-num">{score}</span>
              <span className="mrd-ring-label">recovery</span>
            </div>
          </div>
          <p className="mrd-ring-caption">
            Meera&rsquo;s recovery score, earned from real check-ins — not a guess.
          </p>
        </div>
      </div>
    </section>
  );
}
