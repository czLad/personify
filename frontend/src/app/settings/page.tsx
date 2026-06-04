"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isLoggedIn, clearToken } from "@/lib/api";

export default function SettingsPage() {
  const router = useRouter();
  const [loggedIn, setLoggedIn] = useState(false);

  useEffect(() => {
    // TODO: replace with real auth state check when backend is wired
    setLoggedIn(isLoggedIn());
  }, []);

  function handleLogout() {
    // TODO: optionally call POST /auth/logout if backend adds it
    clearToken();
    setLoggedIn(false);
    router.push("/login");
  }

  function handleLogin() {
    router.push("/login");
  }

  return (
    <>
      <h1>Account</h1>
      {/* <p className="subtitle">Configure how Personify generates responses.</p> */}

      {/* <div className="card">
        <h2>Tone</h2>
        <p style={{ color: "var(--muted)", fontSize: 14 }}>
          Coming soon: choose Formal, Balanced, or Conversational.
        </p>
      </div>

      <div className="card">
        <h2>Length</h2>
        <p style={{ color: "var(--muted)", fontSize: 14 }}>
          Coming soon: target ~50, 100, or 150 words per response.
        </p>
      </div> */}

      {/* Account section — wires to auth */}
      <div className="card">
        <h2>Account</h2>
        <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 16 }}>
          {loggedIn
            ? "You are currently signed in."
            : "Sign in to sync your documents and history across devices."}
        </p>
        {loggedIn ? (
          <button className="btn" onClick={handleLogout} style={{ background: "#c0392b" }}>
            Log out
          </button>
        ) : (
          <div style={{ display: "flex", gap: 10 }}>
            <button className="btn" onClick={handleLogin}>
              Sign in
            </button>
            <a href="/signup" className="btn btn-outline">
              Create account
            </a>
          </div>
        )}
      </div>
    </>
  );
}
