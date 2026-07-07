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
  channel: string;
  body: string;
  created_at: string;
}

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

export function listMessages() {
  return request<MessageResponse[]>("/api/messages");
}

export function sendMessage(body: string) {
  return request<MessageResponse>("/api/messages", {
    method: "POST",
    body: JSON.stringify({ channel: "chat", body }),
  });
}

export { ApiError };
