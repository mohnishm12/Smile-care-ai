"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, login, register } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "register") {
        await register(email, password, fullName);
      }
      const tokens = await login(email, password);
      localStorage.setItem("access_token", tokens.access_token);
      localStorage.setItem("refresh_token", tokens.refresh_token);
      router.push("/chat");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="container">
      <div className="card">
        <h1>{mode === "login" ? "Sign in to HealFlow" : "Create your account"}</h1>
        <form onSubmit={onSubmit}>
          {mode === "register" && (
            <>
              <label htmlFor="fullName">Full name</label>
              <input
                id="fullName"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                minLength={1}
              />
            </>
          )}
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Register"}
          </button>
        </form>
        <p className="muted" style={{ marginTop: "1rem" }}>
          {mode === "login" ? (
            <>
              No account?{" "}
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  setMode("register");
                  setError(null);
                }}
              >
                Register
              </a>
            </>
          ) : (
            <>
              Already registered?{" "}
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  setMode("login");
                  setError(null);
                }}
              >
                Sign in
              </a>
            </>
          )}
        </p>
        <p className="muted" style={{ marginTop: "1.25rem" }}>
          <strong>Meridian</strong> — the clinic operating system.{" "}
          <a href="/home">See what it does</a>
        </p>
      </div>
    </main>
  );
}
