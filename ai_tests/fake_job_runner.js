/**
 * Fake job page runner.
 *
 * Wires the smoke-test control panel buttons (Test backend, Upload
 * documents, Run Personify, Reset). The actual field-detection + paste
 * logic lives in extension/src/content_script.js — this file just
 * orchestrates the page.
 *
 * Why this exists: see ai_tests/fake_job_page.html top comment, and
 * SKILL.md for the rationale. tl;dr: exercise the extension's
 * content_script in a local environment so we can iterate on prompts and
 * RAG quality without loading the unpacked extension and finding a real
 * job posting every time.
 *
 * Upload model: separate inputs for resume vs essays purely for UX
 * clarity. The backend's /upload endpoint doesn't distinguish — both
 * roles go through ingest_document and append to the user's chunk store.
 * Each file is uploaded as its own /upload call (one HTTP request per
 * file). This makes PDFs work naturally; client-side concatenation would
 * require pdf-lib for PDF support, which isn't worth the dependency.
 */

(function () {
  "use strict";

  // The backend URL is read by content_script.js from this global. We
  // set it from the input on every action so the user can change it
  // without reloading the page.
  function syncBackendUrl() {
    const input = document.getElementById("backend-url");
    window.PERSONIFY_BACKEND_URL = (input.value || "http://localhost:8000").trim();
    return window.PERSONIFY_BACKEND_URL;
  }

  // ── Status helpers ──────────────────────────────────────────────────────
  const statusEl = () => document.getElementById("status");

  function setStatus(text, kind) {
    const el = statusEl();
    el.textContent = text;
    el.className = "";
    if (kind) el.classList.add(kind);
  }

  // ── Test backend ────────────────────────────────────────────────────────
  async function pingBackend() {
    const url = syncBackendUrl();
    setStatus(`Pinging ${url}/health ...`);
    try {
      const res = await fetch(`${url}/health`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = await res.json();
      setStatus(`Backend OK — ${body.service || "personify"} (${body.status})`, "ok");
    } catch (err) {
      setStatus(
        `Backend unreachable: ${err.message}\n` +
        `Hints: is uvicorn running on this port? Is CORS_ORIGINS in backend/.env\n` +
        `including the origin this page is served from?`,
        "bad",
      );
    }
  }

  // ── Upload one file via /upload ─────────────────────────────────────────
  // Returns a result object: { ok, filename, chunks_stored, stored_in, error? }
  async function uploadOneFile(url, file) {
    const fd = new FormData();
    fd.append("file", file, file.name);

    try {
      const res = await fetch(`${url}/upload`, { method: "POST", body: fd });
      const text = await res.text();
      let body;
      try { body = JSON.parse(text); } catch { body = { raw: text }; }

      if (!res.ok) {
        return {
          ok: false,
          filename: file.name,
          error: `HTTP ${res.status}: ${body.detail || body.raw || JSON.stringify(body)}`,
        };
      }
      return {
        ok: true,
        filename: body.filename,
        chunks_stored: body.chunks_stored,
        stored_in: body.stored_in,
        document_id: body.document_id,
      };
    } catch (err) {
      return { ok: false, filename: file.name, error: err.message };
    }
  }

  // ── Upload documents ────────────────────────────────────────────────────
  // Reads both file inputs, uploads each file as its own POST /upload.
  // The backend's ingest_document APPENDS to the user's chunk store
  // (ADR change: see embeddings.py docstring). So uploading a resume and
  // then several essays accumulates context across all uploads, which is
  // what we want for retrieval.
  async function uploadDocuments() {
    const url = syncBackendUrl();
    const resumeFile = document.getElementById("resume-input").files?.[0] || null;
    const essayFiles = Array.from(document.getElementById("essay-input").files || []);

    const allFiles = [];
    if (resumeFile) allFiles.push({ role: "resume", file: resumeFile });
    for (const f of essayFiles) allFiles.push({ role: "essay", file: f });

    if (allFiles.length === 0) {
      setStatus("Choose a resume and/or one or more essays first.", "warn");
      return;
    }

    setStatus(
      `Uploading ${allFiles.length} file(s) sequentially:\n` +
      allFiles.map((x) => `  • [${x.role}] ${x.file.name} (${x.file.size} bytes)`).join("\n"),
    );

    // Sequential, not parallel: the backend's in-memory store isn't
    // thread-safe and uploads are usually small. Sequential also makes
    // the status output easy to follow.
    const lines = ["Upload results:"];
    let totalChunks = 0;
    let anyOk = false;

    for (const { role, file } of allFiles) {
      const r = await uploadOneFile(url, file);
      if (r.ok) {
        anyOk = true;
        totalChunks += r.chunks_stored || 0;
        lines.push(
          `  OK  [${role}] ${r.filename}  ` +
          `chunks=${r.chunks_stored}  stored_in=${r.stored_in}` +
          (r.document_id ? `  doc_id=${r.document_id.slice(0, 8)}…` : ""),
        );
      } else {
        lines.push(`  ERR [${role}] ${r.filename}  ${r.error}`);
      }
    }

    lines.push("");
    lines.push(`Total chunks indexed across uploads: ${totalChunks}`);
    setStatus(lines.join("\n"), anyOk ? "ok" : "bad");

    if (anyOk) {
      document.getElementById("run-btn").disabled = false;
    }
  }

  // ── Run Personify ───────────────────────────────────────────────────────
  async function runPersonify() {
    syncBackendUrl();

    if (typeof window.personifyRunAutofill !== "function") {
      setStatus(
        "content_script.js did not register window.personifyRunAutofill.\n" +
        "Did the script load? Check the browser console.",
        "bad",
      );
      return;
    }

    setStatus("Running pipeline (classify → retrieve → generate) ...");
    const started = performance.now();

    try {
      const result = await window.personifyRunAutofill();
      const elapsed = ((performance.now() - started) / 1000).toFixed(1);

      const lines = [
        `Done in ${elapsed}s`,
        `  fields_detected: ${result.fields_detected}`,
        `  fields_filled:   ${result.fields_filled}`,
      ];
      if (result.pipeline_meta) {
        lines.push(`  pipeline_version: ${result.pipeline_meta.pipeline_version}`);
        lines.push(`  user_id:          ${result.pipeline_meta.user_id}`);
      }

      const allSelectors = ["#q-why", "#q-tradeoff", "#q-about", "#q-email"];
      const filledSelectors = new Set(
        (result.responses || []).map((r) => r.selector),
      );
      lines.push("");
      lines.push("Per-field outcome:");
      for (const sel of allSelectors) {
        const verdict = filledSelectors.has(sel) ? "FILLED " : "skipped";
        lines.push(`  ${verdict}  ${sel}`);
      }

      setStatus(lines.join("\n"), "ok");
    } catch (err) {
      const url = window.PERSONIFY_BACKEND_URL || "(unset)";
      setStatus(
        `Pipeline failed: ${err.message}\n` +
        `\n` +
        `Common causes:\n` +
        `  • Backend not running at ${url} (try "Test backend")\n` +
        `  • CORS blocked: the page origin must be in CORS_ORIGINS in\n` +
        `    backend/.env, and uvicorn must be restarted after editing it\n` +
        `  • Backend crashed mid-request: check the uvicorn terminal for\n` +
        `    a Python traceback\n` +
        `\n` +
        `Open DevTools → Network tab and click /autofill to see the real\n` +
        `HTTP response. The browser console will also have the precise CORS\n` +
        `error if that's what's blocking the request.`,
        "bad",
      );
    }
  }

  // ── Reset ───────────────────────────────────────────────────────────────
  function resetAnswers() {
    document.querySelectorAll("#application textarea, #application input[type=text]")
      .forEach((el) => { el.value = ""; });
    setStatus("Answers cleared.");
  }

  // ── Wire up ─────────────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("ping-btn").addEventListener("click", pingBackend);
    document.getElementById("upload-btn").addEventListener("click", uploadDocuments);
    document.getElementById("run-btn").addEventListener("click", runPersonify);
    document.getElementById("reset-btn").addEventListener("click", resetAnswers);
    syncBackendUrl();
  });
})();