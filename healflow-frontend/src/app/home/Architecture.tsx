"use client";

import { useReveal } from "./lib";

const EVENTS = [
  "message.received",
  "appointment.booked",
  "photo.reviewed",
  "emergency.flagged",
  "followup.resolved",
];

export default function Architecture() {
  const { ref, shown } = useReveal<HTMLDivElement>(0.4);

  return (
    <section className="mrd-section" id="architecture">
      <div className="mrd-section-head">
        <p className="mrd-eyebrow">Under the hood</p>
        <h2 className="mrd-h2">
          One append-only clinical event stream.
        </h2>
        <p className="mrd-lede">
          Every action is explainable, every decision replayable. Nothing is
          overwritten — the record is the source of truth, and the audit trail
          is the product.
        </p>
      </div>

      <div className={`mrd-stream ${shown ? "in" : ""}`} ref={ref}>
        <div className="mrd-stream-line" aria-hidden="true">
          <span className="mrd-stream-pulse" />
        </div>
        <ul className="mrd-stream-events">
          {EVENTS.map((e, i) => (
            <li
              key={e}
              className={`mrd-stream-event mrd-reveal ${shown ? "in" : ""}`}
              style={{ transitionDelay: `${i * 0.1}s` }}
            >
              <span className="mrd-stream-node" aria-hidden="true" />
              <code>{e}</code>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
