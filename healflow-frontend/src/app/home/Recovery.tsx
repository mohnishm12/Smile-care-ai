"use client";

import { useReveal } from "./lib";

// Recovery score over the first 10 days: a dip on day 3-4, then a steady climb.
const DAYS = [40, 46, 38, 44, 55, 63, 68, 74, 82, 87];

const W = 520;
const H = 220;
const PAD = 24;

function coords() {
  const max = 100;
  const stepX = (W - PAD * 2) / (DAYS.length - 1);
  return DAYS.map((v, i) => {
    const x = PAD + i * stepX;
    const y = H - PAD - (v / max) * (H - PAD * 2);
    return [x, y] as const;
  });
}

export default function Recovery() {
  const { ref, shown } = useReveal<HTMLDivElement>(0.4);
  const pts = coords();
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");
  const area = `${line} L${pts[pts.length - 1][0]} ${H - PAD} L${pts[0][0]} ${H - PAD} Z`;
  const [lastX, lastY] = pts[pts.length - 1];

  return (
    <section className="mrd-section" id="recovery">
      <div className="mrd-section-head">
        <p className="mrd-eyebrow">Recovery, watched</p>
        <h2 className="mrd-h2">
          Recovery is watched — not left to &ldquo;call us if it gets worse.&rdquo;
        </h2>
        <p className="mrd-lede">
          Meridian checks in after every treatment, tracks pain day by day, and
          turns the answers into a recovery score that trends where it matters.
        </p>
      </div>

      <div className="mrd-chart-card" ref={ref}>
        <div className="mrd-chart-legend">
          <span>Day 1</span>
          <span className="mrd-chart-metric">Recovery score</span>
          <span>Day 10</span>
        </div>
        <svg
          className={`mrd-chart ${shown ? "in" : ""}`}
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label="Recovery score climbing from 40 to 87 over ten days"
        >
          <defs>
            <linearGradient id="mrdArea" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#34d3ee" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#34d3ee" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="mrdLine" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#34d3ee" />
              <stop offset="100%" stopColor="#5b8bff" />
            </linearGradient>
          </defs>

          {[0.25, 0.5, 0.75].map((g) => (
            <line
              key={g}
              x1={PAD}
              x2={W - PAD}
              y1={H - PAD - g * (H - PAD * 2)}
              y2={H - PAD - g * (H - PAD * 2)}
              className="mrd-chart-grid"
            />
          ))}

          <path d={area} fill="url(#mrdArea)" className="mrd-chart-area" />
          <path
            d={line}
            fill="none"
            stroke="url(#mrdLine)"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="mrd-chart-line"
            pathLength={1}
          />
          <circle cx={lastX} cy={lastY} r="5" className="mrd-chart-end" />
        </svg>
      </div>
    </section>
  );
}
