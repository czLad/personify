"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  api,
  isLoggedIn,
  clearToken,
  getUserEmail,
  getUploadedDocs,
} from "@/lib/api";

const BANNER_GRADIENT = "linear-gradient(135deg, #6D65FC 0%, #4DA3FF 100%)";

type DocView = { name: string; uploadedAt: string | null };

function fmtDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

// Small file-type glyph, reused for every document row. Inline SVG keeps the
// page dependency-free, matching the pattern used on the login page.
function DocIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--accent)"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <path d="M9 13h6M9 17h6" />
    </svg>
  );
}

function DocRow({ name, sub, tag }: { name: string; sub?: string | null; tag: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "12px 14px",
        border: "1px solid var(--border)",
        borderRadius: 10,
        background: "var(--bg)",
      }}
    >
      <span
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: 36,
          height: 36,
          borderRadius: 8,
          background: "rgba(109, 101, 252, 0.10)",
          flexShrink: 0,
        }}
      >
        <DocIcon />
      </span>
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontWeight: 500,
            fontSize: 14,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={name}
        >
          {name}
        </div>
        {sub && (
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>{sub}</div>
        )}
      </div>
      <span
        style={{
          marginLeft: "auto",
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
          color: "var(--muted)",
          flexShrink: 0,
        }}
      >
        {tag}
      </span>
    </div>
  );
}

function EmptyLine({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ fontSize: 13.5, color: "var(--muted)", padding: "2px 2px 2px 0" }}>
      {children}
    </p>
  );
}

const SECTION_LABEL: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--muted)",
  marginBottom: 10,
};

export default function SettingsPage() {
  const router = useRouter();

  const [ready, setReady] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [email, setEmail] = useState<string | null>(null);
  const [resumes, setResumes] = useState<DocView[]>([]);
  const [essays, setEssays] = useState<DocView[]>([]);
  const [others, setOthers] = useState<DocView[]>([]);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [hoverLogout, setHoverLogout] = useState(false);

  useEffect(() => {
    const li = isLoggedIn();
    setLoggedIn(li);
    if (!li) {
      setReady(true);
      return;
    }

    let cancelled = false;

    (async () => {
      // Backend is the source of truth. The local manifest (written by the
      // dashboard on upload) is only a fallback for when the call can't be
      // made — backend down, Supabase not configured, or an expired session.
      const [meRes, docsRes] = await Promise.allSettled([
        api.getMe(),
        api.listDocuments(),
      ]);
      if (cancelled) return;

      if (meRes.status === "fulfilled") {
        setEmail(meRes.value.email ?? getUserEmail());
      } else {
        setEmail(getUserEmail());
      }

      if (docsRes.status === "fulfilled") {
        const docs = docsRes.value;
        const toView = (d: { filename: string; uploaded_at: string | null }) => ({
          name: d.filename,
          uploadedAt: d.uploaded_at,
        });
        setResumes(docs.filter((d) => d.doc_type === "resume").map(toView));
        setEssays(docs.filter((d) => d.doc_type === "essay").map(toView));
        setOthers(
          docs
            .filter((d) => d.doc_type !== "resume" && d.doc_type !== "essay")
            .map(toView)
        );
        const stamps = docs
          .map((d) => d.uploaded_at)
          .filter((s): s is string => !!s)
          .sort();
        setUpdatedAt(stamps.length ? stamps[stamps.length - 1] : null);
      } else {
        const m = getUploadedDocs();
        setResumes(m?.resume ? [{ name: m.resume, uploadedAt: m.uploadedAt }] : []);
        setEssays((m?.essays ?? []).map((n) => ({ name: n, uploadedAt: m?.uploadedAt ?? null })));
        setOthers([]);
        setUpdatedAt(m?.uploadedAt ?? null);
      }

      setReady(true);
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  function handleLogout() {
    clearToken();
    setLoggedIn(false);
    router.push("/login");
  }

  const monogram = (email?.trim()?.[0] ?? "U").toUpperCase();
  const hasAnyDoc = resumes.length > 0 || essays.length > 0 || others.length > 0;
  const lastUploaded = fmtDate(updatedAt);

  if (!ready) {
    return (
      <>
        <h1>Account</h1>
        <p className="subtitle">Your profile and uploaded documents.</p>
        <div className="card" style={{ height: 96, opacity: 0.5 }} />
        <div className="card" style={{ height: 160, opacity: 0.5 }} />
      </>
    );
  }

  if (!loggedIn) {
    return (
      <>
        <h1>Account</h1>
        <p className="subtitle">Your profile and uploaded documents.</p>
        <div className="card">
          <h2>You&apos;re signed out</h2>
          <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 16 }}>
            Sign in to sync your documents and history across devices.
          </p>
          <div style={{ display: "flex", gap: 10 }}>
            <button className="btn" onClick={() => router.push("/login")}>
              Sign in
            </button>
            <Link
              href="/signup"
              className="btn"
              style={{ background: "transparent", color: "var(--accent)", border: "1px solid var(--border)" }}
            >
              Create account
            </Link>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <h1>Account</h1>
      <p className="subtitle">Your profile and uploaded documents.</p>

      {/* Profile */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: "50%",
              background: BANNER_GRADIENT,
              color: "white",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 22,
              fontWeight: 600,
              flexShrink: 0,
              userSelect: "none",
            }}
            aria-hidden="true"
          >
            {monogram}
          </div>

          <div style={{ minWidth: 0 }}>
            <div
              style={{
                fontSize: 16,
                fontWeight: 600,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={email ?? undefined}
            >
              {email ?? "Signed in"}
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                marginTop: 4,
                fontSize: 13,
                color: "var(--muted)",
              }}
            >
              <span
                style={{ width: 7, height: 7, borderRadius: "50%", background: "#1e8449", display: "inline-block" }}
                aria-hidden="true"
              />
              Signed in
            </div>
          </div>
        </div>

      </div>

      {/* Documents */}
      <div className="card">
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: 12,
            marginBottom: 4,
          }}
        >
          <h2>Your documents</h2>
          {lastUploaded && (
            <span style={{ fontSize: 12, color: "var(--muted)", flexShrink: 0 }}>
              Updated {lastUploaded}
            </span>
          )}
        </div>
        <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 20 }}>
          The resume and personal statements Personify uses to write your responses.
        </p>

        {!hasAnyDoc ? (
          <div
            style={{
              border: "1px dashed var(--border)",
              borderRadius: 10,
              padding: "28px 20px",
              textAlign: "center",
            }}
          >
            <p style={{ fontSize: 14, color: "var(--muted)", marginBottom: 12 }}>
              You haven&apos;t uploaded any documents yet.
            </p>
            <Link className="btn" href="/#upload">
              Upload documents
            </Link>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div>
              <div style={SECTION_LABEL}>Resume</div>
              {resumes.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {resumes.map((d, i) => (
                    <DocRow key={`r-${d.name}-${i}`} name={d.name} sub={fmtDate(d.uploadedAt)} tag="Resume" />
                  ))}
                </div>
              ) : (
                <EmptyLine>No resume uploaded.</EmptyLine>
              )}
            </div>

            <div>
              <div style={SECTION_LABEL}>
                Personal statements
                {essays.length > 0 && (
                  <span style={{ fontWeight: 500, color: "var(--muted)" }}> · {essays.length}</span>
                )}
              </div>
              {essays.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {essays.map((d, i) => (
                    <DocRow key={`e-${d.name}-${i}`} name={d.name} sub={fmtDate(d.uploadedAt)} tag="Essay" />
                  ))}
                </div>
              ) : (
                <EmptyLine>No personal statements uploaded.</EmptyLine>
              )}
            </div>

            {others.length > 0 && (
              <div>
                <div style={SECTION_LABEL}>Other documents</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {others.map((d, i) => (
                    <DocRow key={`o-${d.name}-${i}`} name={d.name} sub={fmtDate(d.uploadedAt)} tag="Document" />
                  ))}
                </div>
              </div>
            )}

            <Link href="/#upload" style={{ fontSize: 13, fontWeight: 500, color: "var(--accent)" }}>
              Manage documents →
            </Link>
          </div>
        )}
      </div>

      {/* Sign out */}
      <div className="card">
        <h2>Sign out</h2>
        <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 16 }}>
          You&apos;ll need to sign in again to access your documents and history.
        </p>
        <button
          onClick={handleLogout}
          onMouseEnter={() => setHoverLogout(true)}
          onMouseLeave={() => setHoverLogout(false)}
          style={{
            display: "inline-block",
            padding: "10px 18px",
            borderRadius: 8,
            border: "1px solid #c0392b",
            background: hoverLogout ? "#c0392b" : "transparent",
            color: hoverLogout ? "white" : "#c0392b",
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
            transition: "background 0.15s, color 0.15s",
          }}
        >
          Log out
        </button>
      </div>
    </>
  );
}