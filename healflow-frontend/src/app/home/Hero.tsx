"use client";

import DemoButton from "./DemoButton";

// The ambient "6am shift" — the AI working before anyone arrives. Each line
// fades in on a staggered, looping cadence to read as a living activity feed.
const FEED = [
  { time: "05:58", text: "Rescheduled 3 patients around Dr. Sharma's delayed flight" },
  { time: "06:03", text: "Reviewed a recovery photo from Rahul — flagged for review" },
  { time: "06:11", text: "Reordered insulin before the cabinet ran low" },
  { time: "06:19", text: "Answered 14 overnight messages, booked 2 appointments" },
  { time: "06:24", text: "Escalated one patient with worsening pain to a human" },
];

export default function Hero() {
  return (
    <section className="mrd-hero" id="top">
      <div className="mrd-hero-glow" aria-hidden="true" />
      <div className="mrd-hero-grid">
        <div className="mrd-hero-copy">
          <p className="mrd-eyebrow">The clinic operating system</p>
          <h1 className="mrd-hero-title">
            The clinic&rsquo;s best employee
            <br />
            <span className="mrd-grad">never clocks in.</span>
          </h1>
          <p className="mrd-hero-sub">
            Meridian is an AI receptionist and recovery companion that handles
            90% of patient interactions — and shows your staff only the
            decisions that need a human.
          </p>
          <div className="mrd-hero-actions">
            <DemoButton label="Try the demo clinic" size="lg" />
            <a href="#brief" className="mrd-btn mrd-btn-ghost mrd-btn-lg">
              See how it works
            </a>
          </div>
        </div>

        <aside className="mrd-feed" aria-label="The AI at 6am">
          <div className="mrd-feed-head">
            <span className="mrd-live-dot" aria-hidden="true" />
            While the clinic slept &middot; 6:00 AM
          </div>
          <ul className="mrd-feed-list">
            {FEED.map((item, i) => (
              <li
                key={item.time}
                className="mrd-feed-item"
                style={{ animationDelay: `${i * 1.15}s` }}
              >
                <span className="mrd-feed-time">{item.time}</span>
                <span className="mrd-feed-text">{item.text}</span>
              </li>
            ))}
          </ul>
        </aside>
      </div>

      <a href="#brief" className="mrd-scroll-cue" aria-hidden="true">
        <span className="mrd-scroll-track">
          <span className="mrd-scroll-thumb" />
        </span>
        Scroll
      </a>
    </section>
  );
}
