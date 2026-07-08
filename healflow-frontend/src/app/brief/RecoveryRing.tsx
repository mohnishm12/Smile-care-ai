"use client";

import { useEffect, useState } from "react";
import { recoveryBand } from "./humanize";

// A small inline arc that sweeps from empty to the recovery score on mount.
// Colour follows the band (<50 red, <70 amber, else teal). Honours reduced
// motion by rendering the final arc immediately.
export default function RecoveryRing({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, score));
  const band = recoveryBand(clamped);

  const size = 40;
  const stroke = 4;
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;

  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setProgress(clamped);
      return;
    }
    // Next frame so the transition has an empty→full delta to animate.
    const id = requestAnimationFrame(() => setProgress(clamped));
    return () => cancelAnimationFrame(id);
  }, [clamped]);

  const offset = circumference * (1 - progress / 100);

  return (
    <div
      className={`recovery-ring band-${band.tone}`}
      role="img"
      aria-label={`Recovery score ${clamped} out of 100 — ${band.word}`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          className="ring-track"
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={stroke}
          fill="none"
        />
        <circle
          className="ring-arc"
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className="ring-value" aria-hidden="true">
        {clamped}
      </span>
    </div>
  );
}
