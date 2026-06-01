"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function UploadPage() {
  const [status, setStatus] = useState<{ msg: string; kind?: "ok" | "err" }>({ msg: "" });
  const [busy, setBusy] = useState(false);

  async function handleUpload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fileInput = form.elements.namedItem("file") as HTMLInputElement;
    const file = fileInput.files?.[0];
    if (!file) {
      setStatus({ msg: "Please choose a file first", kind: "err" });
      return;
    }

    setBusy(true);
    setStatus({ msg: "Uploading…" });
    try {
      const res = await api.upload(file);
      setStatus({ msg: `Uploaded: ${res.filename} (${res.status})`, kind: "ok" });
    } catch (err) {
      setStatus({ msg: `Upload failed: ${(err as Error).message}`, kind: "err" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Upload Documents</h1>
      <p className="subtitle">Your resume and past essays are used to personalize generated responses.</p>

      <div className="card">
        <h2>Resume</h2>
        <form onSubmit={handleUpload}>
          <input type="file" name="file" accept=".pdf,.txt,.docx" />
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "Uploading…" : "Upload"}
          </button>
          {status.msg && <p className={`status ${status.kind ?? ""}`}>{status.msg}</p>}
        </form>
      </div>

      <div className="card">
        <h2>Optional: past essays</h2>
        <p style={{ color: "var(--muted)", fontSize: 14 }}>
          Upload college essays or past personal statements to give the agent more context.
          Coming soon.
        </p>
      </div>
    </>
  );
}
