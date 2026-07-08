"use client";

import { useId, useState } from "react";
import type { BriefDecision } from "@/lib/api";
import RecoveryRing from "./RecoveryRing";
import {
  actionLabel,
  cardHeading,
  componentLine,
  humanizeRule,
  situationLine,
  tierChip,
  whyLine,
} from "./humanize";

interface Props {
  decision: BriefDecision;
  index: number;
  exiting: boolean;
  acting: boolean;
  error: string | null;
  onAct: (decision: BriefDecision) => void;
}

export default function DecisionCard({
  decision,
  index,
  exiting,
  acting,
  error,
  onAct,
}: Props) {
  const [open, setOpen] = useState(false);
  const detailsId = useId();

  const heading = cardHeading(decision);
  const situation = situationLine(decision);
  const why = whyLine(decision.why);
  const chip = tierChip(decision.recommended_action.tier);
  const label = actionLabel(decision.recommended_action.action);
  const score = decision.recovery_score;

  return (
    <article
      className={`brief-card level-${decision.level}${exiting ? " exiting" : ""}`}
      style={{ "--i": index } as React.CSSProperties}
      aria-busy={acting || undefined}
    >
      <div className="brief-card-main">
        <span
          className={`sev-dot sev-${decision.level}`}
          aria-hidden="true"
        />

        <div className="brief-card-body">
          <div className="brief-card-head">
            <h2 className="brief-name">{heading}</h2>
            {score !== null && <RecoveryRing score={score} />}
          </div>

          {situation && <p className="brief-situation">{situation}</p>}
          {why && <p className="brief-why">{why}</p>}

          <div className="brief-actions">
            <button
              type="button"
              className="brief-primary"
              onClick={() => onAct(decision)}
              disabled={acting || exiting}
            >
              {acting ? "Working…" : label}
            </button>
            <span className={`tier-chip tier-${chip.tone}`}>{chip.label}</span>
            <button
              type="button"
              className="brief-why-toggle"
              aria-expanded={open}
              aria-controls={detailsId}
              onClick={() => setOpen((v) => !v)}
            >
              {open ? "Hide" : "Why?"}
            </button>
          </div>

          {error && (
            <p className="brief-card-error" role="alert">
              {error}
            </p>
          )}
        </div>
      </div>

      {open && (
        <div className="brief-details" id={detailsId}>
          {decision.rules_fired.length > 0 && (
            <div className="brief-detail-block">
              <h3>What triggered this</h3>
              <ul>
                {decision.rules_fired.map((rule, i) => (
                  <li key={`${rule}-${i}`}>{humanizeRule(rule)}</li>
                ))}
              </ul>
            </div>
          )}

          {decision.recovery_components.length > 0 && (
            <div className="brief-detail-block">
              <h3>Recovery signals</h3>
              <ul>
                {decision.recovery_components.map((c, i) => (
                  <li key={`${c.kind}-${i}`}>{componentLine(c)}</li>
                ))}
              </ul>
            </div>
          )}

          {decision.if_ignored && (
            <p className="brief-if-ignored">
              If ignored: {decision.if_ignored}
            </p>
          )}
        </div>
      )}
    </article>
  );
}
