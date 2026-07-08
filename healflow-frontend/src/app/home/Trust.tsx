"use client";

import { useReveal } from "./lib";

const TIERS = [
  {
    key: "acts",
    name: "Acts",
    line: "Books, reschedules and sends reminders on its own — no one signs off.",
    zone: "green",
  },
  {
    key: "drafts",
    name: "Drafts",
    line: "Prepares a reply for anything sensitive and waits for your one-tap approval.",
    zone: "amber",
  },
  {
    key: "alerts",
    name: "Alerts",
    line: "Escalates emergencies to a human instantly, and steps back.",
    zone: "red",
  },
];

export default function Trust() {
  const { ref, shown } = useReveal<HTMLDivElement>(0.35);

  return (
    <section className="mrd-section mrd-section-alt" id="trust">
      <div className="mrd-section-head">
        <p className="mrd-eyebrow">Earned autonomy</p>
        <h2 className="mrd-h2">Autonomy earned in production, never assumed.</h2>
        <p className="mrd-lede">
          A Beta-Bernoulli trust engine watches how each action performs on real
          patients. Prove it works, and it moves up a tier. Nothing is granted on
          faith.
        </p>
      </div>

      <div className="mrd-tiers" ref={ref}>
        {TIERS.map((t, i) => (
          <article
            key={t.key}
            className={`mrd-tier mrd-reveal ${shown ? "in" : ""}`}
            style={{ transitionDelay: `${i * 0.12}s` }}
          >
            <div className={`mrd-tier-badge ${t.zone}`}>
              <span className="mrd-tier-dot" aria-hidden="true" />
              {t.name}
            </div>
            <p className="mrd-tier-line">{t.line}</p>
            <div className="mrd-tier-meter" aria-hidden="true">
              <span className={`mrd-tier-fill ${t.zone}`} />
            </div>
          </article>
        ))}
      </div>

      <p className="mrd-trust-foot">
        Confidence grows from a lower bound on evidence — not a vibe. The clinic
        stays in control the whole way up.
      </p>
    </section>
  );
}
