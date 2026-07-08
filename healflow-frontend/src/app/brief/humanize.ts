// Turns the kernel's machine-readable rule ids, component kinds and action
// names into calm, human sentences for the Morning Brief. Pure functions —
// no state, safe to call during render.

import type { BriefDecision, RecoveryComponent, TrustTier } from "@/lib/api";

// recommended_action.action → the verb a clinician reads on the button.
const ACTION_LABELS: Record<string, string> = {
  acknowledge_escalation: "Acknowledge",
  book_review_appointment: "Book review",
  draft_symptom_outreach: "Draft outreach",
  send_reengagement_checkin: "Send check-in",
  draft_reply: "Reply",
};

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? titleCase(action);
}

// Trust tier → the small chip beside the action.
const TIER_CHIPS: Record<TrustTier, { label: string; tone: string }> = {
  ACT: { label: "auto", tone: "act" },
  DRAFT: { label: "review", tone: "draft" },
  ASK: { label: "confirm", tone: "ask" },
};

export function tierChip(tier: TrustTier): { label: string; tone: string } {
  return TIER_CHIPS[tier] ?? { label: tier.toLowerCase(), tone: "ask" };
}

// A handful of rule ids read badly under the generic humanizer; spell those
// out. Everything else falls through to snake_case → sentence.
const RULE_PHRASES: Record<string, string> = {
  pain_slope_ge_2: "Pain climbing steeply across nights",
  pain_rising: "Pain rising night over night",
  pain_ge_8: "Pain reported at 8 or higher",
  checkins_unanswered_ge_2: "Two or more check-ins unanswered",
  patient_message_unanswered: "A patient message is still waiting",
};

export function humanizeRule(rule: string): string {
  if (RULE_PHRASES[rule]) return RULE_PHRASES[rule];
  if (rule.startsWith("symptom_")) {
    return `Reported ${rule.slice("symptom_".length).replace(/_/g, " ")}`;
  }
  return sentence(rule.replace(/_ge_(\d+)/g, " ≥ $1"));
}

// Joins the why[] rules into one muted line under the card heading.
export function whyLine(why: string[]): string {
  const parts = why.map(humanizeRule).filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0];
  return parts.slice(0, -1).join(", ") + " · " + parts[parts.length - 1];
}

// recovery_components → readable "Why?" expansion lines with their weight.
export function componentLine(c: RecoveryComponent): string {
  const delta = typeof c.delta === "number" ? c.delta : 0;
  const weight = delta ? ` (${delta > 0 ? "+" : ""}${Math.round(delta)})` : "";
  const kind = c.kind ?? "";
  if (kind === "pain_above_expected") {
    return `Pain above expected on day ${c.day ?? "?"}${weight}`;
  }
  if (kind === "pain_rising") {
    return `Pain rose from day ${c.from_day ?? "?"} to ${c.to_day ?? "?"}${weight}`;
  }
  if (kind === "checkins_unanswered") {
    return `${c.count ?? "Several"} check-ins unanswered${weight}`;
  }
  if (kind === "doses_missed") {
    return `${c.count ?? "Several"} medication doses missed${weight}`;
  }
  if (kind.startsWith("symptom_")) {
    return `Reported ${kind.slice("symptom_".length).replace(/_/g, " ")}${weight}`;
  }
  return sentence(kind.replace(/_/g, " ")) + weight;
}

// Recovery band → colour + short word. <50 red, <70 amber, else teal.
export function recoveryBand(
  score: number,
): { tone: "low" | "mid" | "high"; word: string } {
  if (score < 50) return { tone: "low", word: "at risk" };
  if (score < 70) return { tone: "mid", word: "watch" };
  return { tone: "high", word: "on track" };
}

// The heading a clinician reads first: the patient when the backend provides
// one, else the situation summary so the row still reads as a person's item.
export function cardHeading(d: BriefDecision): string {
  const name = d.patient_name?.trim();
  return name && name.length > 0 ? name : d.summary;
}

// When we lead with a name, the summary becomes the situation line; when we
// had to lead with the summary, there's no separate situation line.
export function situationLine(d: BriefDecision): string | null {
  const name = d.patient_name?.trim();
  return name && name.length > 0 ? d.summary : null;
}

function titleCase(s: string): string {
  return s
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function sentence(s: string): string {
  const t = s.trim().replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}
