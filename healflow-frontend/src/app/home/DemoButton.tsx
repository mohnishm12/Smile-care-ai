"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, seedDemo } from "@/lib/api";

interface DemoButtonProps {
  variant?: "primary" | "ghost";
  label?: string;
  size?: "md" | "lg";
}

/**
 * Provisions a demo clinic and drops the visitor straight into the live app.
 * On success we persist both tokens and route to "/", where the real
 * Morning Brief renders against the freshly seeded patients.
 */
export default function DemoButton({
  variant = "primary",
  label = "Try the demo clinic",
  size = "md",
}: DemoButtonProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function launch() {
    setBusy(true);
    setError(null);
    try {
      const res = await seedDemo();
      localStorage.setItem("access_token", res.access_token);
      localStorage.setItem("refresh_token", res.refresh_token);
      // Navigate to the live app home (the real Morning Brief). Keep the
      // button in its "Preparing…" state — the route change unmounts us.
      router.push("/");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn't reach the clinic. Please try again.",
      );
      setBusy(false);
    }
  }

  return (
    <span className="mrd-cta">
      <button
        type="button"
        onClick={launch}
        disabled={busy}
        aria-live="polite"
        className={`mrd-btn mrd-btn-${variant} mrd-btn-${size}`}
      >
        {busy ? (
          <>
            <span className="mrd-spinner" aria-hidden="true" />
            Preparing your clinic…
          </>
        ) : (
          label
        )}
      </button>
      {error && (
        <span className="mrd-cta-error" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}
