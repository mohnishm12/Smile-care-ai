"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Brief from "./brief/Brief";

// Home is the Morning Brief. No token → sign in. With a token we render the
// brief; it redirects patients (403) to /chat and expired sessions (401) to
// /login on its own.
export default function Home() {
  const router = useRouter();
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.replace("/login");
      setAuthed(false);
      return;
    }
    setAuthed(true);
  }, [router]);

  if (!authed) {
    return (
      <main className="brief-shell">
        <div className="brief-column">
          <p className="brief-loading">Loading Meridian…</p>
        </div>
      </main>
    );
  }

  return <Brief />;
}
