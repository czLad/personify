const BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export type HistoryItem = {
  company_name: string;
  question: string;
  generated_response: string;
  created_at: string;
};

export type AuthResponse = {
  user_id: string;
  access_token: string;
};

export type OAuthResponse = {
  url: string;
};

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function getUserId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("user_id");
}

export function setToken(token: string, userId: string) {
  localStorage.setItem("token", token);
  localStorage.setItem("user_id", userId);
}

export function clearToken() {
  localStorage.removeItem("token");
  localStorage.removeItem("user_id");
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  const userId = getUserId();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (userId) headers["X-User-Id"] = userId;
  return headers;
}

export const api = {
  health: () => jsonFetch<{ status: string; service: string }>("/health"),

  history: () => jsonFetch<{ status: string; items: HistoryItem[] }>("/history", {
    headers: authHeaders(),
  }),

  upload: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE_URL}/upload`, {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  },

  signup: (email: string, password: string) =>
    jsonFetch<AuthResponse>("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    jsonFetch<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  loginWithGoogle: () =>
    jsonFetch<OAuthResponse>("/auth/login/google", { method: "POST" }),
};
