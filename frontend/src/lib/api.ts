const BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export type DownloadItem = {
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

export type DocumentItem = {
  id: string;
  filename: string;
  content_type: string | null;
  doc_type: string | null; // "resume" | "essay" | null
  uploaded_at: string | null;
};

export type MeResponse = {
  user_id: string;
  email: string | null;
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

export function getUserEmail(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("user_email");
}

// email is optional so existing callers don't break; when provided (login),
// it's persisted so the Account page can show a real identifier instead of
// just the raw user UUID.
export function setToken(token: string, userId: string, email?: string) {
  localStorage.setItem("token", token);
  localStorage.setItem("user_id", userId);
  if (email) localStorage.setItem("user_email", email);
}

export function clearToken() {
  localStorage.removeItem("token");
  localStorage.removeItem("user_id");
  localStorage.removeItem("user_email");
  localStorage.removeItem("uploaded_docs");
}

// ── Uploaded-documents manifest ─────────────────────────────────────────────
// The backend has no endpoint to list a user's stored documents, so the
// dashboard records what it just uploaded here (the one place that knows each
// file's role + name). Every successful upload overwrites this, mirroring the
// wipe-and-rebuild model, so it always reflects the current stored set. The
// Account page reads it to show "what you've uploaded."
export type UploadedDocs = {
  resume: string | null;
  essays: string[];
  uploadedAt: string; // ISO timestamp
};

export function setUploadedDocs(docs: UploadedDocs) {
  if (typeof window === "undefined") return;
  localStorage.setItem("uploaded_docs", JSON.stringify(docs));
}

export function getUploadedDocs(): UploadedDocs | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("uploaded_docs");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UploadedDocs;
  } catch {
    return null;
  }
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

  download: () => jsonFetch<{ status: string; items: DownloadItem[] }>("/download", {
    headers: authHeaders(),
  }),

  upload: async (file: File, docType?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    // Lets the backend record whether this is a "resume" or "essay" so the
    // Account page can group them. Optional — omitted uploads store null.
    if (docType) fd.append("doc_type", docType);
    const res = await fetch(`${BASE_URL}/upload`, {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `${res.status} ${res.statusText}`);
    }
    return res.json();
  },

  // Authenticated user's stored documents, newest first. Powers the Account
  // page. Requires a valid Supabase session (Bearer token) — throws 401 if the
  // token is missing/expired, in which case the caller can fall back.
  listDocuments: () =>
    jsonFetch<DocumentItem[]>("/documents", { headers: authHeaders() }),

  // Basic profile for the signed-in user (id + email), verified server-side.
  getMe: () => jsonFetch<MeResponse>("/auth/me", { headers: authHeaders() }),

  // Wipe the user's entire stored corpus (in-memory + Supabase). The
  // dashboard calls this once before re-uploading resume + essays so the
  // stored set always matches what's currently attached (wipe-and-rebuild).
  resetCorpus: async () => {
    const res = await fetch(`${BASE_URL}/upload`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `${res.status} ${res.statusText}`);
    }
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