"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  ASSISTANT_SENDER_ID,
  ConversationSummary,
  MessageResponse,
  PatientTimeline,
  WS_BASE,
  ackEscalation,
  getPatientTimeline,
  listConversations,
  listPatientMessages,
  markConversationRead,
  resumeConversation,
  sendClinicReply,
  suggestReply,
  takeoverConversation,
} from "@/lib/api";
import StaffNav from "../dashboard/StaffNav";
import ConversationList from "./ConversationList";
import Thread from "./Thread";
import ContextPanel from "./ContextPanel";

const POLL_INTERVAL_MS = 15_000;

// Backend order: open escalations first, then most recent message. Applied
// again client-side so live WebSocket bumps keep the same ranking.
function sortConversations(list: ConversationSummary[]): ConversationSummary[] {
  return [...list].sort((a, b) => {
    if (b.open_escalations !== a.open_escalations) {
      return b.open_escalations - a.open_escalations;
    }
    return (
      new Date(b.last_message_at).getTime() -
      new Date(a.last_message_at).getTime()
    );
  });
}

function senderKind(
  m: MessageResponse,
  patientId: string,
): ConversationSummary["last_sender_kind"] {
  if (m.sender_id === patientId) return "patient";
  if (m.sender_id === ASSISTANT_SENDER_ID) return "assistant";
  return "staff";
}

export default function ReceptionWorkspace() {
  const router = useRouter();

  const [conversations, setConversations] = useState<
    ConversationSummary[] | null
  >(null);
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageResponse[] | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);
  const [threadError, setThreadError] = useState<string | null>(null);

  const [timeline, setTimeline] = useState<PatientTimeline | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  // Refs mirror state the WebSocket handler needs without re-connecting.
  const selectedIdRef = useRef<string | null>(null);
  selectedIdRef.current = selectedId;

  const handleAuthError = useCallback(
    (err: unknown): boolean => {
      if (err instanceof ApiError && err.status === 401) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        router.replace("/login");
        return true;
      }
      return false;
    },
    [router],
  );

  const refreshConversations = useCallback(async () => {
    try {
      const list = await listConversations();
      setConversations(sortConversations(list));
      setListError(null);
    } catch (err) {
      if (handleAuthError(err)) return;
      if (err instanceof ApiError && err.status === 403) {
        setFatalError(
          "This account doesn't have staff access. Sign in with a staff, " +
            "doctor, or clinic admin account to use the workspace.",
        );
        return;
      }
      // Keep any stale list on screen; only surface the error when we have
      // nothing at all to show.
      setListError("Couldn't refresh conversations. Retrying shortly…");
    }
  }, [handleAuthError]);

  // Applies a live message to the conversation list: bump preview, move the
  // row into place, and count unread when we aren't looking at the thread.
  const bumpConversation = useCallback(
    (m: MessageResponse, patientId: string) => {
      setConversations((prev) => {
        if (prev === null) return prev;
        const existing = prev.find((c) => c.patient_id === patientId);
        if (!existing) {
          // Unknown patient (first-ever message) — pull the full list.
          void refreshConversations();
          return prev;
        }
        const kind = senderKind(m, patientId);
        const viewing = selectedIdRef.current === patientId;
        const updated: ConversationSummary = {
          ...existing,
          last_message: m.body.slice(0, 160),
          last_message_at: m.created_at,
          last_sender_kind: kind,
          unread_count:
            kind === "patient" && !viewing
              ? existing.unread_count + 1
              : existing.unread_count,
          ai_paused: kind === "staff" ? true : existing.ai_paused,
        };
        return sortConversations(
          prev.map((c) => (c.patient_id === patientId ? updated : c)),
        );
      });
    },
    [refreshConversations],
  );

  // Initial load, 15s polling, and the shared staff WebSocket.
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.replace("/login");
      return;
    }

    void refreshConversations();
    const interval = setInterval(
      () => void refreshConversations(),
      POLL_INTERVAL_MS,
    );

    const wsOrigin =
      WS_BASE !== ""
        ? WS_BASE
        : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
    const ws = new WebSocket(
      `${wsOrigin}/ws/chat?token=${encodeURIComponent(token)}`,
    );
    ws.onmessage = (event) => {
      let incoming: MessageResponse;
      try {
        incoming = JSON.parse(event.data) as MessageResponse;
      } catch {
        return; // ignore malformed frames
      }
      if (!incoming || typeof incoming.id !== "string") return;
      // Staff/assistant messages carry conversation_user_id; patient
      // messages are identified by their sender.
      const patientId = incoming.conversation_user_id ?? incoming.sender_id;
      if (!patientId) return;

      if (selectedIdRef.current === patientId) {
        setMessages((prev) =>
          prev === null || prev.some((m) => m.id === incoming.id)
            ? prev
            : [...prev, incoming],
        );
        // We're looking right at it — keep the read watermark current.
        markConversationRead(patientId).catch(() => undefined);
      }
      bumpConversation(incoming, patientId);
    };

    return () => {
      clearInterval(interval);
      ws.close();
    };
  }, [router, refreshConversations, bumpConversation]);

  const selectConversation = useCallback(
    async (patientId: string) => {
      setSelectedId(patientId);
      setMessages(null);
      setThreadError(null);
      setThreadLoading(true);
      setTimeline(null);
      setTimelineError(null);
      setTimelineLoading(true);

      const [msgs, tl] = await Promise.allSettled([
        listPatientMessages(patientId),
        getPatientTimeline(patientId),
      ]);

      if (msgs.status === "fulfilled") {
        const ordered = [...msgs.value].sort(
          (a, b) =>
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
        );
        setMessages(ordered);
        // Opening a thread marks it read; clear the badge optimistically.
        markConversationRead(patientId).catch(() => undefined);
        setConversations((prev) =>
          prev === null
            ? prev
            : prev.map((c) =>
                c.patient_id === patientId ? { ...c, unread_count: 0 } : c,
              ),
        );
      } else if (!handleAuthError(msgs.reason)) {
        setThreadError("Failed to load this conversation.");
      }
      setThreadLoading(false);

      if (tl.status === "fulfilled") {
        setTimeline(tl.value);
      } else if (!handleAuthError(tl.reason)) {
        setTimelineError("Failed to load patient context.");
      }
      setTimelineLoading(false);
    },
    [handleAuthError],
  );

  const setAiPaused = useCallback((patientId: string, paused: boolean) => {
    setConversations((prev) =>
      prev === null
        ? prev
        : prev.map((c) =>
            c.patient_id === patientId ? { ...c, ai_paused: paused } : c,
          ),
    );
  }, []);

  const handleTakeover = useCallback(async () => {
    if (!selectedId) return;
    try {
      const res = await takeoverConversation(selectedId);
      setAiPaused(selectedId, res.ai_paused);
    } catch (err) {
      if (handleAuthError(err)) return;
      setThreadError("Couldn't take over this conversation.");
    }
  }, [selectedId, setAiPaused, handleAuthError]);

  const handleResume = useCallback(async () => {
    if (!selectedId) return;
    try {
      const res = await resumeConversation(selectedId);
      setAiPaused(selectedId, res.ai_paused);
    } catch (err) {
      if (handleAuthError(err)) return;
      setThreadError("Couldn't resume the AI for this conversation.");
    }
  }, [selectedId, setAiPaused, handleAuthError]);

  const handleSend = useCallback(
    async (body: string): Promise<boolean> => {
      if (!selectedId) return false;
      setThreadError(null);
      try {
        const created = await sendClinicReply(selectedId, body);
        setMessages((prev) =>
          prev === null || prev.some((m) => m.id === created.id)
            ? prev
            : [...prev, created],
        );
        bumpConversation(created, selectedId);
        setAiPaused(selectedId, true); // sending as clinic pauses the AI
        markConversationRead(selectedId).catch(() => undefined);
        return true;
      } catch (err) {
        if (handleAuthError(err)) return false;
        setThreadError("Failed to send — the message was not delivered.");
        return false;
      }
    },
    [selectedId, bumpConversation, setAiPaused, handleAuthError],
  );

  const handleSuggest = useCallback(async (): Promise<string | null> => {
    if (!selectedId) return null;
    setThreadError(null);
    try {
      const res = await suggestReply(selectedId);
      return res.suggestion;
    } catch (err) {
      if (handleAuthError(err)) return null;
      setThreadError("Couldn't draft a suggestion right now.");
      return null;
    }
  }, [selectedId, handleAuthError]);

  const handleAck = useCallback(
    async (escalationId: string) => {
      try {
        await ackEscalation(escalationId);
        if (selectedIdRef.current) {
          const [tl] = await Promise.allSettled([
            getPatientTimeline(selectedIdRef.current),
          ]);
          if (tl.status === "fulfilled") setTimeline(tl.value);
        }
        void refreshConversations();
      } catch (err) {
        if (handleAuthError(err)) return;
        setTimelineError("Couldn't acknowledge the escalation.");
      }
    },
    [refreshConversations, handleAuthError],
  );

  const selected =
    conversations?.find((c) => c.patient_id === selectedId) ?? null;
  const aiPaused = selected?.ai_paused ?? false;

  if (fatalError) {
    return (
      <main className="container-wide">
        <StaffNav />
        <h1>Reception workspace</h1>
        <p className="error">{fatalError}</p>
      </main>
    );
  }

  return (
    <main className="ws-shell">
      <div className="ws-header">
        <StaffNav />
      </div>
      {listError && conversations === null && (
        <p className="error ws-pad">{listError}</p>
      )}
      <div className="ws-layout">
        <section className="conv-pane">
          <div className="conv-pane-head">
            <h1 className="ws-title">Conversations</h1>
            {conversations !== null && (
              <span className="muted">{conversations.length}</span>
            )}
          </div>
          <ConversationList
            conversations={conversations}
            selectedId={selectedId}
            onSelect={(id) => void selectConversation(id)}
          />
        </section>

        <Thread
          patientId={selectedId}
          patientName={selected?.patient_name ?? timeline?.patient.full_name ?? null}
          aiPaused={aiPaused}
          messages={messages}
          loading={threadLoading}
          error={threadError}
          onSend={handleSend}
          onSuggest={handleSuggest}
          onTakeover={() => void handleTakeover()}
          onResume={() => void handleResume()}
        />

        <ContextPanel
          timeline={timeline}
          loading={timelineLoading}
          error={timelineError}
          highPriority={selected?.high_priority ?? false}
          aiPaused={aiPaused}
          onAck={handleAck}
          onTakeover={() => void handleTakeover()}
          onResume={() => void handleResume()}
        />
      </div>
    </main>
  );
}
