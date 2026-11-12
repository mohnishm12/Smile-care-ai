"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

// Minimal top bar: the wordmark, the date, and one discreet menu. No tabs —
// the brief is home.
export default function TopBar({ subtitle }: { subtitle?: string | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function signOut() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    router.push("/login");
  }

  return (
    <header className="brief-topbar">
      <div className="brief-brand">
        <span className="brief-mark">Meridian</span>
        {subtitle && <span className="brief-subtitle">{subtitle}</span>}
      </div>

      <div className="brief-menu-wrap" ref={menuRef}>
        <button
          type="button"
          className="brief-menu-trigger"
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label="Menu"
          onClick={() => setOpen((v) => !v)}
        >
          <span aria-hidden="true">•••</span>
        </button>
        {open && (
          <div className="brief-menu" role="menu">
            <Link
              href="/reception"
              role="menuitem"
              className="brief-menu-item"
              onClick={() => setOpen(false)}
            >
              Workspace
            </Link>
            <Link
              href="/dashboard/reception"
              role="menuitem"
              className="brief-menu-item"
              onClick={() => setOpen(false)}
            >
              Analytics
            </Link>
            <Link
              href="/dashboard/doctor"
              role="menuitem"
              className="brief-menu-item"
              onClick={() => setOpen(false)}
            >
              Doctor view
            </Link>
            <button
              type="button"
              role="menuitem"
              className="brief-menu-item danger"
              onClick={signOut}
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
