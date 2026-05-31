"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function HomePage() {
  const [status, setStatus] = useState<{ msg: string; kind?: "ok" | "err" }>({ msg: "" });

  async function ping() {
    setStatus({ msg: "Checking backend…" });
    try {
      const data = await api.health();
      setStatus({ msg: `Backend OK — ${data.service}`, kind: "ok" });
    } catch (err) {
      setStatus({ msg: `Backend unreachable: ${(err as Error).message}`, kind: "err" });
    }
  }

  return (
    <>
      <h1>Personify Dashboard</h1>
      <p className="subtitle">Agentic AI for job application personal statements.</p>

      <div className="card">
        <h2>Get started</h2>
        <p style={{ marginBottom: 16, color: "var(--muted)", fontSize: 14 }}>
          Upload your resume on the <a href="/upload" style={{ color: "var(--accent)" }}>Upload</a> page,
          install the Chrome extension, and click "Autofill" on any job application.
        </p>
        <button className="btn" onClick={ping}>Test backend connection</button>
        {status.msg && <p className={`status ${status.kind ?? ""}`}>{status.msg}</p>}
      </div>
    </>
  );
}
