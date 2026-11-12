"use client";

import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion, useReveal } from "./lib";

type Sender = "patient" | "ai";

interface Msg {
  from: Sender;
  text: string;
  slots?: string[];
  emergency?: boolean;
}

// Two threads: a routine booking, then an emergency that fires a red alert.
const SCENES: Msg[][] = [
  [
    { from: "patient", text: "Hi, can I see Dr. Sharma tomorrow?" },
    {
      from: "ai",
      text: "Of course — Dr. Sharma has a few openings tomorrow:",
      slots: ["9:15 AM", "10:30 AM", "4:00 PM"],
    },
    { from: "patient", text: "10:30 works." },
    {
      from: "ai",
      text: "Booked ✓ Tomorrow, 10:30 AM with Dr. Sharma. I've sent a reminder and blocked double-bookings.",
    },
  ],
  [
    { from: "patient", text: "I have heavy bleeding since my extraction" },
    {
      from: "ai",
      emergency: true,
      text: "This needs attention now. I've alerted Dr. Sharma and sent first-aid steps. If it hasn't slowed in 10 minutes, please go to the ER.",
    },
    {
      from: "ai",
      emergency: true,
      text: "🚨 Emergency flagged · Dr. Sharma notified · human taking over",
    },
  ],
];

type Step =
  | { kind: "typing"; who: Sender }
  | { kind: "msg"; msg: Msg }
  | { kind: "hold" }
  | { kind: "clear" };

// Flatten scenes into a looping timeline: typing → message → … → hold → clear.
function buildSteps(): { step: Step; ms: number }[] {
  const out: { step: Step; ms: number }[] = [];
  SCENES.forEach((scene) => {
    scene.forEach((msg) => {
      const typeMs = Math.min(1400, 500 + msg.text.length * 12);
      out.push({ step: { kind: "typing", who: msg.from }, ms: typeMs });
      out.push({ step: { kind: "msg", msg }, ms: 700 });
    });
    out.push({ step: { kind: "hold" }, ms: 2600 });
    out.push({ step: { kind: "clear" }, ms: 500 });
  });
  return out;
}

export default function ReceptionistDemo() {
  const { ref, shown } = useReveal<HTMLDivElement>(0.4);
  const [visible, setVisible] = useState<Msg[]>([]);
  const [typing, setTyping] = useState<Sender | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!shown) return;

    // Reduced motion: show the completed booking thread, no loop, no typing.
    if (prefersReducedMotion()) {
      setVisible(SCENES[0]);
      setTyping(null);
      return;
    }

    const steps = buildSteps();
    let cancelled = false;

    const run = (i: number) => {
      if (cancelled) return;
      const { step, ms } = steps[i % steps.length];
      if (step.kind === "typing") setTyping(step.who);
      else if (step.kind === "msg") {
        setTyping(null);
        setVisible((v) => [...v, step.msg]);
      } else if (step.kind === "clear") {
        setTyping(null);
        setVisible([]);
      }
      timer.current = setTimeout(() => run(i + 1), ms);
    };
    run(0);

    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [shown]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [visible, typing]);

  return (
    <section className="mrd-section mrd-section-alt" id="receptionist">
      <div className="mrd-section-head">
        <p className="mrd-eyebrow">The AI receptionist</p>
        <h2 className="mrd-h2">It answers on WhatsApp before you&rsquo;ve had coffee.</h2>
        <p className="mrd-lede">
          Booking, rescheduling, reminders — handled. And when a message signals
          danger, it stops guessing and gets a human.
        </p>
      </div>

      <div className="mrd-phone-wrap" ref={ref}>
        <div className="mrd-phone">
          <div className="mrd-phone-bar">
            <span className="mrd-phone-avatar" aria-hidden="true">M</span>
            <span className="mrd-phone-titles">
              <span className="mrd-phone-name">Meridian &middot; Smile Care</span>
              <span className="mrd-phone-status">online</span>
            </span>
            <span className="mrd-phone-wa" aria-hidden="true">WhatsApp</span>
          </div>

          <div className="mrd-phone-body" ref={scrollRef}>
            {visible.map((m, i) => (
              <div
                key={i}
                className={`mrd-msg ${m.from} ${m.emergency ? "emergency" : ""}`}
              >
                <span className="mrd-msg-text">{m.text}</span>
                {m.slots && (
                  <span className="mrd-slots">
                    {m.slots.map((s) => (
                      <span key={s} className="mrd-slot">
                        {s}
                      </span>
                    ))}
                  </span>
                )}
              </div>
            ))}
            {typing && (
              <div className={`mrd-msg ${typing} mrd-typing`} aria-label="typing">
                <span className="mrd-dot" />
                <span className="mrd-dot" />
                <span className="mrd-dot" />
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
