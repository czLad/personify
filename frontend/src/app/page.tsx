"use client";

import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";

const INITIAL_CHECKLIST = [
  { label: "Create your account", done: true },
  { label: "Upload your documents", done: false },
  { label: "Install the Chrome extension", done: false },
  { label: "Personify your first personal statement", done: false },
];

export default function HomePage() {
  const [checklist, setChecklist] = useState(INITIAL_CHECKLIST);
  const [resumeStatus, setResumeStatus] = useState<{ msg: string; kind?: "ok" | "err" }>({ msg: "" });
  const [essayStatus, setEssayStatus] = useState<{ msg: string; kind?: "ok" | "err" }>({ msg: "" });
  const [resumeBusy, setResumeBusy] = useState(false);
  const [essayBusy, setEssayBusy] = useState(false);
  const [resumeFile, setResumeFile] = useState<string | null>(null);
  const [resumeDragging, setResumeDragging] = useState(false);
  const [essayDragging, setEssayDragging] = useState(false);
  const resumeInputRef = useRef<HTMLInputElement>(null);
  const essayInputRef = useRef<HTMLInputElement>(null);
  
  useEffect(() => {
    const installed = localStorage.getItem("personify_extension_installed") === "true";
    if (installed) {
      setChecklist((prev) =>
        prev.map((item) =>
          item.label === "Install the Chrome extension" ? { ...item, done: true } : item
        )
      );
    }
  }, []);

  function toggle(index: number) {
    setChecklist((prev) =>
      prev.map((item, i) => (i === index ? { ...item, done: !item.done } : item))
    );
  }

  async function handleResumeUpload(file: File) {
    setResumeBusy(true);
    setResumeStatus({ msg: "Uploading…" });
    try {
      await api.upload(file);
      setResumeFile(file.name);
      setResumeStatus({ msg: `✓ ${file.name} uploaded successfully`, kind: "ok" });
      setChecklist((prev) =>
        prev.map((item) =>
          item.label === "Upload your documents" ? { ...item, done: true } : item
        )
      );
    } catch (err) {
      setResumeStatus({ msg: `Upload failed: ${(err as Error).message}`, kind: "err" });
    } finally {
      setResumeBusy(false);
    }
  }

  async function handleEssayUpload(file: File) {
    setEssayBusy(true);
    setEssayStatus({ msg: "Uploading…" });
    try {
      await api.upload(file);
      setEssayStatus({ msg: `✓ ${file.name} uploaded successfully`, kind: "ok" });
    } catch (err) {
      setEssayStatus({ msg: `Upload failed: ${(err as Error).message}`, kind: "err" });
    } finally {
      setEssayBusy(false);
    }
  }

  return (
    <>
        {/* Welcome banner */}

    <div style={{
      background: "linear-gradient(135deg, #6D65FC 0%, #4DA3FF 100%)",
      borderRadius: 16,
      padding: "36px 40px 48px",
      marginBottom: 24,
      color: "white",
    }}>
      <h1 style={{
        fontSize: 32,
        fontWeight: 700,
        color: "white",
        marginBottom: 8,
      }}>
        Welcome,  Daphne 👋
      </h1>
      <p style={{ fontSize: 15, opacity: 0.75 }}>
        Let&apos;s get you set up so Personify can start writing your personal statements.
      </p>
    </div>
      <h1>Personify Dashboard</h1>
      <p className="subtitle">Agentic AI for job application personal statements.</p>

      {/* Getting started checklist */}
      <div className="card">
        <h2>Get started</h2>
        <p style={{ marginBottom: 16, color: "var(--muted)", fontSize: 14 }}>
          Upload your documents, install the Chrome extension, and click &quot;Personify&quot; on any job application.
        </p>
        <div style={{ marginBottom: 2 }}>
          {checklist.map((item, index) => (
            <div
              key={item.label}
              onClick={() => toggle(index)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "9px 0",
                borderBottom: "1px solid var(--border)",
                fontSize: 14,
                cursor: "pointer",
                userSelect: "none",
              }}
            >
              <span style={{
                width: 20,
                height: 20,
                borderRadius: "50%",
                border: item.done ? "none" : "2px solid #ccc",
                background: item.done ? "var(--accent)" : "transparent",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                color: "white",
                fontSize: 12,
                fontWeight: 700,
              }}>
                {item.done ? "✓" : ""}
              </span>
              <span style={{ color: item.done ? "var(--fg)" : "var(--muted)" }}>
                {item.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Resume upload */}
      <div className="card" id="upload">
        <h2>Resume</h2>
        <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 16 }}>
          Upload your resume to help Personify understand your experience.
        </p>

        {resumeFile && (
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "10px 12px",
            background: "var(--bg)",
            borderRadius: 8,
            marginBottom: 12,
            fontSize: 13,
          }}>
            <span style={{ color: "#1e8449" }}>✓</span>
            <span style={{ fontWeight: 500 }}>{resumeFile}</span>
            <button
              onClick={() => { setResumeFile(null); setResumeStatus({ msg: "" }); }}
              style={{ marginLeft: "auto", background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 13 }}
            >
              Replace
            </button>
          </div>
        )}

        <div
          onDragOver={(e) => { e.preventDefault(); setResumeDragging(true); }}
          onDragLeave={() => setResumeDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setResumeDragging(false);
            const file = e.dataTransfer.files?.[0];
            if (file) handleResumeUpload(file);
          }}
          onClick={() => resumeInputRef.current?.click()}
          style={{
            border: `2px dashed ${resumeDragging ? "var(--accent)" : "var(--border)"}`,
            borderRadius: 10,
            padding: "28px 20px",
            textAlign: "center",
            cursor: "pointer",
            background: resumeDragging ? "#f0f4ff" : "var(--bg)",
            transition: "all 0.15s",
          }}
        >
          <div style={{ fontSize: 24, marginBottom: 6 }}>↑</div>
          <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 4 }}>
            Drag and drop or click to upload
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)" }}>PDF, DOCX, or TXT</div>
          <input
            ref={resumeInputRef}
            type="file"
            accept=".pdf,.txt,.docx"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleResumeUpload(file);
            }}
          />
        </div>

        {resumeStatus.msg && (
          <p className={`status ${resumeStatus.kind ?? ""}`} style={{ marginTop: 10 }}>
            {resumeStatus.msg}
          </p>
        )}
        {resumeBusy && (
          <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 8 }}>Uploading…</div>
        )}
      </div>

      {/* Essays upload */}
      <div className="card">
        <h2>Personal Statements <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 400, marginLeft: 6 }}>Optional</span></h2>
        <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 16 }}>
          Upload college essays or past personal statements to give Personify more context about your voice.
        </p>

        <div
          onDragOver={(e) => { e.preventDefault(); setEssayDragging(true); }}
          onDragLeave={() => setEssayDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setEssayDragging(false);
            const file = e.dataTransfer.files?.[0];
            if (file) handleEssayUpload(file);
          }}
          onClick={() => essayInputRef.current?.click()}
          style={{
            border: `2px dashed ${essayDragging ? "var(--accent)" : "var(--border)"}`,
            borderRadius: 10,
            padding: "28px 20px",
            textAlign: "center",
            cursor: "pointer",
            background: essayDragging ? "#f0f4ff" : "var(--bg)",
            transition: "all 0.15s",
          }}
        >
          <div style={{ fontSize: 24, marginBottom: 6 }}>↑</div>
          <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 4 }}>
            Drag and drop or click to upload
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)" }}>PDF, DOCX, or TXT</div>
          <input
            ref={essayInputRef}
            type="file"
            accept=".pdf,.txt,.docx"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleEssayUpload(file);
            }}
          />
        </div>

        {essayStatus.msg && (
          <p className={`status ${essayStatus.kind ?? ""}`} style={{ marginTop: 10 }}>
            {essayStatus.msg}
          </p>
        )}
        {essayBusy && (
          <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 8 }}>Uploading…</div>
        )}
      </div>
    </>
  );
}
