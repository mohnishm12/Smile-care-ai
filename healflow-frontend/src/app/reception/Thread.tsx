"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ASSISTANT_SENDER_ID, MessageResponse } from "@/lib/api";

function bubbleKind(
  m: MessageResponse,
  patientId: string,
): "patient" | "assistant" | "staff" {
  if (m.sender_id === patientId) return "patient";
  if (m.sender_id === ASSISTANT_SENDER_ID) return "assistant";
  return "staff";
}

const LABELS: Record<string, string> = {
  assistant: "HealFlow Assistant",
  staff: "You / Clinic",
};

export default function Thread({
  patientId,
  patientName,
  aiPaused,
  messages,
  loading,
  error,
  onSend,
  onSuggest,
  onTakeover,
  onResume,
}: {
  patientId: string | null;
  patientName: string | null;
  aiPaused: boolean;
  messages: MessageResponse[] | null;
  loading: boolean;
  error: string | null;
  onSend: (body: string) => Promise<boolean>;
  onSuggest: () => Promise<string | null>;
  onTakeover: () => void;
  onResume: () => void;
}) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Reset the composer when switching conversations.
  useEffect(() => {
    setDraft("");
  }, [patientId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  if (!patientId) {
    return (
      <section className="thread-pane">
        <div className="ws-empty">
          <p className="muted">
            Select a conversation to read the thread, reply as the clinic, or
            hand it back to the assistant.
          </p>
        </div>
      </section>
    );
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = draft.trim();
    if (!body || sending) return;
    setSending(true);
    const ok = await onSend(body);
    if (ok) setDraft("");
    setSending(false);
  }

  async function suggest() {
    if (suggesting) return;
    setSuggesting(true);
    const suggestion = await onSuggest();
    if (suggestion !== null) setDraft(suggestion);
    setSuggesting(false);
  }

  return (
    <section className="thread-pane">
      <div className="thread-topbar">
        <div className="thread-title">
          <strong>{patientName ?? "Conversation"}</strong>
          <span className={`chip ${aiPaused ? "human" : "ai"}`}>
            {aiPaused ? "Human handling" : "AI active"}
          </span>
        </div>
        {aiPaused ? (
          <button type="button" className="ghost-button" onClick={onResume}>
            Resume AI
          </button>
        ) : (
          <button type="button" className="ghost-button" onClick={onTakeover}>
            Take over
          </button>
        )}
      </div>

      <div className="thread-messages">
        {loading && <p className="muted ws-pad">Loading thread…</p>}
        {error && <p className="error ws-pad">{error}</p>}
        {!loading && !error && messages !== null && messages.length === 0 && (
          <p className="muted ws-pad">
            No messages in this conversation yet — send the first one below.
          </p>
        )}
        {(messages ?? []).map((m) => {
          const kind = bubbleKind(m, patientId);
          return (
            <div key={m.id} className={`bubble ${kind}`}>
              {kind !== "patient" && (
                <span className="bubble-label">{LABELS[kind]}</span>
              )}
              <div className="bubble-body">{m.body}</div>
              <time className="bubble-time">
                {new Date(m.created_at).toLocaleString([], {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </time>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      <form className="composer" onSubmit={submit}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Reply to ${patientName ?? "patient"} as the clinic…`}
          aria-label="Reply as clinic"
          rows={2}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <div className="composer-actions">
          <button
            type="button"
            className="ghost-button"
            onClick={suggest}
            disabled={suggesting || sending}
          >
            {suggesting ? "Drafting…" : "✨ Suggest reply"}
          </button>
          <button type="submit" disabled={sending || !draft.trim()}>
            {sending ? "Sending…" : "Send"}
          </button>
        </div>
      </form>
    </section>
  );
}
