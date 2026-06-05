"use client";

import { useState, useRef } from "react";
import { api, setUploadedDocs } from "@/lib/api";
import { log } from "@/lib/log";

const INITIAL_CHECKLIST = [
  { label: "Create your account", done: true },
  { label: "Upload your documents", done: false },
  { label: "Install the Chrome extension", done: false },
  { label: "Personify your first personal statement", done: false },
];

// Same gradient as the welcome banner — reused for the primary upload CTA.
const BANNER_GRADIENT = "linear-gradient(135deg, #6D65FC 0%, #4DA3FF 100%)";

type Status = { msg: string; kind?: "ok" | "err" };

export default function HomePage() {
  const [checklist, setChecklist] = useState(INITIAL_CHECKLIST);

  // Staged files — nothing is uploaded until the user clicks "Upload documents".
  // The resume is a single slot; personal statements can be several files.
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [essayFiles, setEssayFiles] = useState<File[]>([]);

  const [resumeDragging, setResumeDragging] = useState(false);
  const [essayDragging, setEssayDragging] = useState(false);

  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>({ msg: "" });

  // True only while the currently-attached set matches what's stored on the
  // server. Drives the button label ("Uploaded" vs "Upload documents"). Reset
  // to false the moment the user stages or removes a file, since the attached
  // set no longer matches what was uploaded.
  const [uploaded, setUploaded] = useState(false);

  const resumeInputRef = useRef<HTMLInputElement>(null);
  const essayInputRef = useRef<HTMLInputElement>(null);

  function toggle(index: number) {
    setChecklist((prev) =>
      prev.map((item, i) => (i === index ? { ...item, done: !item.done } : item))
    );
  }

  // ── Staging (no network) ──────────────────────────────────────────────────
  function stageResume(file: File) {
    log.debug("[stageResume] got file:", file?.name, file?.type, file?.size);
    setResumeFile(file);
    setStatus({ msg: "" });
    setUploaded(false);
  }

  function stageEssays(files: FileList | null) {
    const arr = files ? Array.from(files) : [];
    log.debug(
      "[stageEssays] FileList length:", files?.length,
      "→ array:", arr.map((f) => f.name)
    );
    if (arr.length === 0) {
      log.warn("[stageEssays] nothing to stage — FileList was empty");
      return;
    }
    setEssayFiles((prev) => {
      const next = [...prev, ...arr];
      log.debug("[stageEssays] essayFiles now:", next.map((f) => f.name));
      return next;
    });
    setStatus({ msg: "" });
    setUploaded(false);
  }

  function removeEssay(index: number) {
    setEssayFiles((prev) => prev.filter((_, i) => i !== index));
    setUploaded(false);
  }

  // ── Upload everything (wipe-and-rebuild) ────────────────────────────────────
  // Clears the user's whole corpus once, then uploads the resume followed by
  // each personal statement. This keeps the stored set exactly matching what's
  // currently attached — no stale or duplicate chunks accumulate across
  // re-uploads. Mirrors the per-file POST /upload flow the fake job page uses,
  // with an explicit DELETE /upload up front.
  async function handleUploadAll() {
    log.debug(
      "[handleUploadAll] resume:", resumeFile?.name,
      "essays:", essayFiles.map((f) => f.name)
    );
    if (!resumeFile && essayFiles.length === 0) {
      setStatus({ msg: "Attach a resume (and optionally personal statements) first.", kind: "err" });
      return;
    }

    const ordered: { role: string; file: File }[] = [];
    if (resumeFile) ordered.push({ role: "resume", file: resumeFile });
    for (const f of essayFiles) ordered.push({ role: "essay", file: f });

    setBusy(true);
    setStatus({ msg: "Clearing previous documents…" });

    try {
      // 1. Wipe the existing corpus so this upload fully replaces it.
      await api.resetCorpus();

      // 2. Upload each staged file (sequential — keeps the status readable
      //    and the backend store consistent).
      const lines: string[] = ["Upload results:"];
      let total = 0;
      for (const { role, file } of ordered) {
        setStatus({ msg: `Uploading ${file.name}…` });
        const r = await api.upload(file, role);
        log.debug("[handleUploadAll] uploaded", role, file.name, "→", r);
        total += r.chunks_stored ?? 0;
        lines.push(
          `  ✓ [${role}] ${r.filename} — chunks=${r.chunks_stored}, stored_in=${r.stored_in}`
        );
      }
      lines.push("");
      lines.push(`Total chunks indexed: ${total}`);
      log.debug("[handleUploadAll]", lines.join(" | "));
      setUploaded(true);
      setStatus({ msg: "" });

      // Record what was just stored so the Account page can list it. This
      // mirrors the wipe-and-rebuild model: it always reflects the current set.
      setUploadedDocs({
        resume: resumeFile?.name ?? null,
        essays: essayFiles.map((f) => f.name),
        uploadedAt: new Date().toISOString(),
      });

      setChecklist((prev) =>
        prev.map((item) =>
          item.label === "Upload your documents" ? { ...item, done: true } : item
        )
      );
    } catch (err) {
      log.error("[handleUploadAll] failed:", err);
      setStatus({ msg: `Upload failed: ${(err as Error).message}`, kind: "err" });
    } finally {
      setBusy(false);
    }
  }

  const hasStaged = !!resumeFile || essayFiles.length > 0;

  return (
    <>
      {/* Welcome banner */}
      <div style={{
        background: BANNER_GRADIENT,
        borderRadius: 16,
        padding: "36px 40px 48px",
        marginBottom: 24,
        color: "white",
      }}>
        <h1 style={{ fontSize: 32, fontWeight: 700, color: "white", marginBottom: 8 }}>
          Welcome, Daphne 👋
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

      {/* Resume — attach (single slot) */}
      <div className="card" id="upload">
        <h2>Resume</h2>
        <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 16 }}>
          Attach your resume to help Personify understand your experience.
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
            <span style={{ fontWeight: 500 }}>{resumeFile.name}</span>
            <button
              onClick={() => { setResumeFile(null); setUploaded(false); }}
              style={{ marginLeft: "auto", background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 13 }}
            >
              Remove
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
            log.debug("[resume onDrop] dropped files:", e.dataTransfer.files?.length);
            if (file) stageResume(file);
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
            Drag and drop or click to attach
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)" }}>PDF, DOCX, or TXT</div>
          <input
            ref={resumeInputRef}
            type="file"
            accept=".pdf,.txt,.docx"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              log.debug("[resume input onChange] files:", e.target.files?.length);
              if (file) stageResume(file);
              e.target.value = "";
            }}
          />
        </div>
      </div>

      {/* Personal statements — attach (multiple) */}
      <div className="card">
        <h2>Personal Statements <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 400, marginLeft: 6 }}>Optional</span></h2>
        <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 16 }}>
          Attach college essays or past personal statements to give Personify more context about your voice.
        </p>

        {essayFiles.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            {essayFiles.map((f, i) => (
              <div
                key={`${f.name}-${i}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "10px 12px",
                  background: "var(--bg)",
                  borderRadius: 8,
                  marginBottom: 8,
                  fontSize: 13,
                }}
              >
                <span style={{ color: "#1e8449" }}>✓</span>
                <span style={{ fontWeight: 500 }}>{f.name}</span>
                <button
                  onClick={() => removeEssay(i)}
                  style={{ marginLeft: "auto", background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 13 }}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}

        <div
          onDragOver={(e) => { e.preventDefault(); setEssayDragging(true); }}
          onDragLeave={() => setEssayDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setEssayDragging(false);
            log.debug("[essay onDrop] dropped files:", e.dataTransfer.files?.length);
            stageEssays(e.dataTransfer.files);
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
            Drag and drop or click to attach
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)" }}>PDF, DOCX, or TXT</div>
          <input
            ref={essayInputRef}
            type="file"
            accept=".pdf,.txt,.docx"
            multiple
            style={{ display: "none" }}
            onChange={(e) => {
              const files = e.target.files;
              log.debug("[essay input onChange] files:", files?.length);
              stageEssays(files);
              e.target.value = "";
            }}
          />
        </div>
      </div>

      {/* Combined upload — wipe-and-rebuild the whole corpus */}
      <div style={{ marginTop: 4 }}>
        <button
          onClick={handleUploadAll}
          disabled={busy || !hasStaged}
          style={{
            width: "100%",
            background: BANNER_GRADIENT,
            color: "white",
            border: "none",
            borderRadius: 10,
            padding: "14px 20px",
            fontSize: 15,
            fontWeight: 600,
            cursor: busy || !hasStaged ? "not-allowed" : "pointer",
            opacity: busy || !hasStaged ? 0.5 : 1,
            transition: "opacity 0.15s",
          }}
        >
          {busy ? "Uploading…" : uploaded ? "Uploaded" : "Upload documents"}
        </button>

        {status.kind === "err" && status.msg && (
          <pre
            className={`status ${status.kind}`}
            style={{
              marginTop: 12,
              whiteSpace: "pre-wrap",
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              fontSize: 12.5,
            }}
          >
            {status.msg}
          </pre>
        )}
      </div>
    </>
  );
}