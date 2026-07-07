"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  getMe,
  listMessages,
  MessageResponse,
  sendMessage,
  UserResponse,
  WS_BASE,
} from "@/lib/api";

export default function ChatPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    router.push("/login");
  }, [router]);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.replace("/login");
      return;
    }

    (async () => {
      try {
        setUser(await getMe());
        setMessages(await listMessages());
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        setError("Failed to load messages");
      }
    })();

    // Live updates over WebSocket; falls back silently if unavailable.
    const wsOrigin =
      WS_BASE !== ""
        ? WS_BASE
        : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
    const ws = new WebSocket(`${wsOrigin}/ws/chat?token=${encodeURIComponent(token)}`);
    ws.onmessage = (event) => {
      try {
        const incoming: MessageResponse = JSON.parse(event.data);
        setMessages((prev) =>
          prev.some((m) => m.id === incoming.id) ? prev : [...prev, incoming],
        );
      } catch {
        // ignore malformed frames
      }
    };
    wsRef.current = ws;

    return () => ws.close();
  }, [router, logout]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function onSend(e: FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await sendMessage(draft.trim());
      setMessages((prev) =>
        prev.some((m) => m.id === created.id) ? prev : [...prev, created],
      );
      setDraft("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError("Failed to send message");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="container">
      <div className="card">
        <div className="topbar">
          <h1>HealFlow Chat</h1>
          <div>
            {user && <span className="muted">{user.email} · </span>}
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault();
                logout();
              }}
            >
              Sign out
            </a>
          </div>
        </div>

        {error && <p className="error">{error}</p>}

        <div className="messages">
          {messages.length === 0 && <p className="muted">No messages yet — say hello.</p>}
          {messages.map((m) => (
            <div key={m.id} className="message">
              {m.body}
              <time>{new Date(m.created_at).toLocaleString()}</time>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        <form onSubmit={onSend} className="row">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Type a message…"
            aria-label="Message"
          />
          <button type="submit" disabled={busy || !draft.trim()}>
            Send
          </button>
        </form>
      </div>
    </main>
  );
}
