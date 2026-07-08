// Client-side API helper. NEXT_PUBLIC_* vars are inlined at build time;
// fall back to same-origin (through nginx) when unset.
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL !== ""
    ? process.env.NEXT_PUBLIC_API_URL
    : "";

export const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL && process.env.NEXT_PUBLIC_WS_URL !== ""
    ? process.env.NEXT_PUBLIC_WS_URL
    : "";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

export interface MessageResponse {
  id: string;
  sender_id: string;
  conversation_user_id?: string | null;
  channel: string;
  body: string;
  created_at: string;
}

// Fixed identity seeded by backend migration 0002 — messages from this
// sender are the AI assistant.
export const ASSISTANT_SENDER_ID = "00000000-0000-4000-8000-00000000a1a1";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

export function register(email: string, password: string, fullName: string) {
  return request<UserResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, full_name: fullName }),
  });
}

export function login(email: string, password: string) {
  return request<TokenResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getMe() {
  return request<UserResponse>("/api/auth/me");
}

// ---- Staff & analytics endpoints ----

export interface AnalyticsOverview {
  todays_appointments: number;
  missed_appointments: number;
  revenue: number;
  currency: string;
  avg_rating: number | null;
  followup_completion_rate: number;
  response_rate: number;
  open_escalations: number;
}

export interface Escalation {
  id: string;
  patient_name: string;
  severity: "high" | "critical";
  reason: string;
  trigger_text: string;
  created_at: string;
  acknowledged: boolean;
}

export interface StaffAppointment {
  id: string;
  patient_name: string;
  doctor_name: string;
  scheduled_at: string;
  status: string;
  // Present when the backend exposes the linked patient; used to open the
  // patient timeline from the doctor view.
  patient_id?: string;
}

export interface CheckinEntry {
  day_number: number;
  pain_level: number;
  symptoms: Record<string, unknown>;
  responded_at: string;
}

export interface MedicationAdherence {
  taken: number;
  missed: number;
  pending: number;
}

export interface TimelineMessage {
  body: string;
  created_at: string;
  from_assistant: boolean;
}

export interface PatientSummary {
  id: string;
  full_name: string;
  email: string;
}

export interface PatientTimeline {
  patient: PatientSummary;
  appointments: StaffAppointment[];
  checkins: CheckinEntry[];
  medication_adherence: MedicationAdherence;
  escalations: Escalation[];
  recent_messages: TimelineMessage[];
}

export function getAnalyticsOverview() {
  return request<AnalyticsOverview>("/api/analytics/overview");
}

export function listEscalations() {
  return request<Escalation[]>("/api/staff/escalations");
}

export function listTodaysAppointments() {
  return request<StaffAppointment[]>("/api/staff/appointments/today");
}

export function getPatientTimeline(patientId: string) {
  return request<PatientTimeline>(
    `/api/staff/patients/${encodeURIComponent(patientId)}/timeline`,
  );
}

export function listMessages() {
  return request<MessageResponse[]>("/api/messages");
}

export function sendMessage(body: string) {
  return request<MessageResponse>("/api/messages", {
    method: "POST",
    body: JSON.stringify({ channel: "chat", body }),
  });
}

// ---- Reception workspace endpoints ----

export interface ConversationSummary {
  patient_id: string;
  patient_name: string;
  last_message: string;
  last_message_at: string;
  last_sender_kind: "patient" | "assistant" | "staff";
  unread_count: number;
  ai_paused: boolean;
  high_priority: boolean;
  open_escalations: number;
}

export function listConversations() {
  return request<ConversationSummary[]>("/api/reception/conversations");
}

export function listPatientMessages(patientId: string, limit = 200) {
  return request<MessageResponse[]>(
    `/api/messages?patient_id=${encodeURIComponent(patientId)}&limit=${limit}`,
  );
}

export function sendClinicReply(patientId: string, body: string) {
  return request<MessageResponse>(
    `/api/reception/conversations/${encodeURIComponent(patientId)}/send`,
    { method: "POST", body: JSON.stringify({ body }) },
  );
}

export function takeoverConversation(patientId: string) {
  return request<{ ai_paused: boolean }>(
    `/api/reception/conversations/${encodeURIComponent(patientId)}/takeover`,
    { method: "POST" },
  );
}

export function resumeConversation(patientId: string) {
  return request<{ ai_paused: boolean }>(
    `/api/reception/conversations/${encodeURIComponent(patientId)}/resume`,
    { method: "POST" },
  );
}

export function suggestReply(patientId: string) {
  return request<{ suggestion: string }>(
    `/api/reception/conversations/${encodeURIComponent(patientId)}/suggest`,
    { method: "POST" },
  );
}

export function markConversationRead(patientId: string) {
  return request<{ ok: boolean }>(
    `/api/reception/conversations/${encodeURIComponent(patientId)}/read`,
    { method: "POST" },
  );
}

export function ackEscalation(escalationId: string) {
  return request<{ id: string; acknowledged: boolean }>(
    `/api/staff/escalations/${encodeURIComponent(escalationId)}/ack`,
    { method: "POST" },
  );
}

export { ApiError };
