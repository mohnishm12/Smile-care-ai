"use client";

import { ConversationSummary } from "@/lib/api";

export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffSec = Math.round((Date.now() - then) / 1000);
  if (diffSec < 60) return "now";
  const mins = Math.floor(diffSec / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return new Date(iso).toLocaleDateString([], {
    month: "short",
    day: "numeric",
  });
}

function previewPrefix(kind: ConversationSummary["last_sender_kind"]): string {
  if (kind === "assistant") return "AI: ";
  if (kind === "staff") return "You: ";
  return "";
}

export default function ConversationList({
  conversations,
  selectedId,
  onSelect,
}: {
  conversations: ConversationSummary[] | null;
  selectedId: string | null;
  onSelect: (patientId: string) => void;
}) {
  if (conversations === null) {
    return <p className="muted ws-pad">Loading conversations…</p>;
  }
  if (conversations.length === 0) {
    return (
      <p className="muted ws-pad">
        No conversations yet — patients appear here when they message the
        clinic.
      </p>
    );
  }

  return (
    <div className="conv-list" role="listbox" aria-label="Conversations">
      {conversations.map((c) => {
        const selected = c.patient_id === selectedId;
        return (
          <button
            key={c.patient_id}
            type="button"
            role="option"
            aria-selected={selected}
            className={`conv-item${selected ? " selected" : ""}`}
            onClick={() => onSelect(c.patient_id)}
          >
            <div className="conv-top">
              <span className="conv-name">
                {c.high_priority && (
                  <span
                    className="priority-dot"
                    title="High priority patient"
                  />
                )}
                {c.patient_name}
              </span>
              <span className="conv-time">
                {relativeTime(c.last_message_at)}
              </span>
            </div>
            <div className="conv-preview">
              {previewPrefix(c.last_sender_kind)}
              {c.last_message}
            </div>
            <div className="conv-meta">
              <span className={`chip ${c.ai_paused ? "human" : "ai"}`}>
                {c.ai_paused ? "Human" : "AI"}
              </span>
              {c.open_escalations > 0 && (
                <span
                  className="chip escalation"
                  title={`${c.open_escalations} open escalation${c.open_escalations > 1 ? "s" : ""}`}
                >
                  🚨 {c.open_escalations}
                </span>
              )}
              {c.unread_count > 0 && (
                <span className="unread-badge">{c.unread_count}</span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}
