"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  BriefDecision,
  actOnDecision,
  getBrief,
} from "@/lib/api";
import TopBar from "./TopBar";
import DecisionCard from "./DecisionCard";

const EXIT_MS = 340;

// Counts the hero number up to its target on mount / when it changes.
// Honours reduced motion by snapping straight to the value.
function useCountUp(target: number): number {
  const [value, setValue] = useState(target);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || target <= 0) {
      setValue(target);
      return;
    }
    const from = 0;
    const start = performance.now();
    const duration = 600;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(from + (target - from) * eased));
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [target]);

  return value;
}

export default function Brief() {
  const router = useRouter();

  const [greeting, setGreeting] = useState<string>("");
  const [decisions, setDecisions] = useState<BriefDecision[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [exiting, setExiting] = useState<Set<string>>(new Set());
  const [actingId, setActingId] = useState<string | null>(null);
  const [cardError, setCardError] = useState<Record<string, string>>({});

  const handleAuthError = useCallback(
    (err: unknown): boolean => {
      if (err instanceof ApiError && err.status === 401) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        router.replace("/login");
        return true;
      }
      // A patient account has no staff brief — send them to their experience.
      if (err instanceof ApiError && err.status === 403) {
        router.replace("/chat");
        return true;
      }
      return false;
    },
    [router],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const brief = await getBrief();
        if (cancelled) return;
        setGreeting(brief.greeting);
        setDecisions(brief.decisions);
        setLoadError(null);
      } catch (err) {
        if (cancelled) return;
        if (handleAuthError(err)) return;
        setLoadError("Couldn't load the brief. Refresh to try again.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [handleAuthError]);

  const remaining = decisions
    ? decisions.filter((d) => !exiting.has(d.decision_id)).length
    : 0;
  const heroCount = useCountUp(remaining);

  const handleAct = useCallback(
    async (decision: BriefDecision) => {
      const id = decision.decision_id;
      setActingId(id);
      setCardError((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      // Optimistic: begin the card's exit so the number settles immediately.
      setExiting((prev) => new Set(prev).add(id));
      try {
        await actOnDecision(id, decision.recommended_action.action);
        setTimeout(() => {
          setDecisions((prev) =>
            prev ? prev.filter((d) => d.decision_id !== id) : prev,
          );
          setExiting((prev) => {
            const next = new Set(prev);
            next.delete(id);
            return next;
          });
        }, EXIT_MS);
      } catch (err) {
        // Roll back — the card returns to the list.
        setExiting((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
        if (!handleAuthError(err)) {
          setCardError((prev) => ({
            ...prev,
            [id]: "That didn't go through. Try again.",
          }));
        }
      } finally {
        setActingId((cur) => (cur === id ? null : cur));
      }
    },
    [handleAuthError],
  );

  if (loadError) {
    return (
      <main className="brief-shell">
        <TopBar subtitle={today()} />
        <div className="brief-column">
          <p className="brief-load-error" role="alert">
            {loadError}
          </p>
        </div>
      </main>
    );
  }

  if (decisions === null) {
    return (
      <main className="brief-shell">
        <TopBar subtitle={today()} />
        <div className="brief-column">
          <p className="brief-loading" aria-live="polite">
            Preparing your morning brief…
          </p>
        </div>
      </main>
    );
  }

  const firstName = greetingFirstName(greeting);
  const empty = remaining === 0;

  return (
    <main className="brief-shell">
      <TopBar subtitle={today()} />
      <div className="brief-column">
        <section className="brief-hero" aria-live="polite">
          <h1 className="brief-greeting">
            {greeting || "Good morning."}
          </h1>
          {empty ? (
            <p className="brief-lede calm">
              Nothing needs you right now — your clinic is running smoothly.
            </p>
          ) : (
            <p className="brief-lede">
              <span className="brief-count">{heroCount}</span>{" "}
              {heroCount === 1 ? "patient needs" : "patients need"} your
              attention. Everything else is handled.
            </p>
          )}
        </section>

        {empty ? (
          <div className="brief-empty" aria-hidden="true">
            <div className="brief-empty-mark" />
          </div>
        ) : (
          <ol className="brief-list">
            {decisions.map((d, i) => (
              <li key={d.decision_id}>
                <DecisionCard
                  decision={d}
                  index={i}
                  exiting={exiting.has(d.decision_id)}
                  acting={actingId === d.decision_id}
                  error={cardError[d.decision_id] ?? null}
                  onAct={handleAct}
                />
              </li>
            ))}
          </ol>
        )}

        <p className="brief-signoff">
          {firstName ? `That's the picture, ${firstName}.` : "That's the picture."}
        </p>
      </div>
    </main>
  );
}

function today(): string {
  return new Date().toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

// "Good morning, Dr. Shah." → "Dr. Shah"
function greetingFirstName(greeting: string): string | null {
  const m = greeting.match(/,\s*(.+?)\.?\s*$/);
  return m ? m[1] : null;
}
