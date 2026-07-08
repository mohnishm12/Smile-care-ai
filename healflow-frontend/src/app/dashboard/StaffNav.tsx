"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

export default function StaffNav() {
  const router = useRouter();

  function signOut() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    router.push("/login");
  }

  return (
    <nav className="nav-row">
      <Link href="/">Home</Link>
      <Link href="/dashboard/reception">Reception</Link>
      <Link href="/dashboard/doctor">Doctor</Link>
      <span className="spacer" />
      <button type="button" className="nav-link-button" onClick={signOut}>
        Sign out
      </button>
    </nav>
  );
}
