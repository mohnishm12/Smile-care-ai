"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    router.replace(token ? "/chat" : "/login");
  }, [router]);

  return (
    <main className="container">
      <p className="muted">Loading HealFlow AI…</p>
    </main>
  );
}
