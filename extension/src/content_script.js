/**
 * Personify content script.
 *
 * Runs in two host environments:
 *   1. Inside the real Chrome extension on supported job portals
 *      (Ashby, Greenhouse, Workday) — receives a chrome.runtime message
 *      from the popup to trigger autofill.
 *   2. Inside ai_tests/fake_job_page.html as a regular <script>
 *      tag — used as a local smoke test for the field detection + paste
 *      logic without needing to install the extension. The fake page
 *      calls window.personifyRunAutofill() directly.
 *
 * Responsibilities:
 *   1. Scan the DOM for form fields (Perceive)
 *   2. Send those fields to the backend for classification + generation
 *   3. Paste the generated responses into the right fields (Act)
 *
 * The intelligence (Decide) lives entirely in the backend. This script
 * never holds an API key and never calls an LLM directly.
 */

// Backend URL resolution. Order of precedence:
//   1. window.PERSONIFY_BACKEND_URL — explicit override set by the host page
//      (the fake job page uses this to point at a specific port).
//   2. A previously-resolved URL, cached for this page session.
//   3. Probe /health on each candidate port and use the first that answers,
//      so the extension works whether the backend runs on 8000 or 8001.
//   4. Fall back to the first candidate so callers always have a URL to hit
//      (and to surface a sensible error if nothing is running).
var BACKEND_CANDIDATES = ["http://localhost:8000", "http://localhost:8001"];
var _resolvedBackendUrl = null;

async function resolveBackendUrl() {
  if (typeof window !== "undefined" && window.PERSONIFY_BACKEND_URL) {
    return window.PERSONIFY_BACKEND_URL;
  }
  if (_resolvedBackendUrl) return _resolvedBackendUrl;
  for (const base of BACKEND_CANDIDATES) {
    try {
      const r = await fetch(`${base}/health`);
      if (r.ok) {
        _resolvedBackendUrl = base;
        return base;
      }
    } catch (_e) {
      // Port not listening / unreachable — try the next candidate.
    }
  }
  return BACKEND_CANDIDATES[0];
}

// Resolve the caller's user id for backend requests. Priority:
//   1. window.PERSONIFY_USER_ID — explicit override set by the host page (the
//      fake job page sets it from /auth/login).
//   2. The session synced into chrome.storage.local — written by the dashboard
//      sync (when localhost:3000 is loaded while logged in) or by the extension
//      popup's own login. This is what makes autofill on a real ATS page (e.g.
//      Ashby) run as the logged-in user instead of the backend's demo user.
// Async because chrome.storage is async; callers await it. Returns null when no
// identity is available, in which case the backend falls back to its demo user.
function getUserId() {
  const override = (typeof window !== "undefined" && window.PERSONIFY_USER_ID) || null;
  if (override) return Promise.resolve(override);
  if (typeof chrome === "undefined" || !chrome.storage || !chrome.storage.local) {
    return Promise.resolve(null);
  }
  return new Promise(function(resolve) {
    chrome.storage.local.get(["userId"], function(data) {
      resolve((data && data.userId) || null);
    });
  });
}

// ── Listen for "Autofill" trigger from popup ─────────────────────────────────
// Guarded so the script can be loaded outside a Chrome extension context
// (e.g. the fake job page). Without this guard, the file crashes on load
// in a plain web page because `chrome` is undefined.

if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message && message.type === "AUTOFILL_TRIGGER") {
      runAutofill()
        .then((result) => sendResponse({ ok: true, result }))
        .catch((err) => sendResponse({ ok: false, error: err.message }));
      return true;
    }
    if (message && message.type === "SCAN_FIELDS") {
      const fields = collectFields();
      sendResponse({ fields });
      return true;
    }
  });
}

// ── 1. Perceive ──────────────────────────────────────────────────────────────

/**
 * Scan the DOM for all visible form fields.
 *
 * TODO (MLE): build the composite selector strategy.
 * For now we use field id when available, fallback to a generated path.
 * Workday and Greenhouse will need the label + DOM-position fallback.
 */
function collectFields() {
  const inputs = document.querySelectorAll("textarea, input[type='text']");
  const fields = [];

  inputs.forEach((el, index) => {
    if (!isVisible(el)) return;

    const label = findLabelText(el) || el.placeholder || "(no label)";
    const selector = buildSelector(el, index);

    fields.push({
      selector,
      label,
      field_type: el.tagName.toLowerCase() === "textarea" ? "textarea" : "text",
    });
  });

  return fields;
}

function isVisible(el) {
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function findLabelText(el) {
  // try associated <label for="...">
  if (el.id) {
    const lbl = document.querySelector(`label[for="${el.id}"]`);
    if (lbl) return lbl.textContent.trim();
  }
  // try wrapping label
  const wrapping = el.closest("label");
  if (wrapping) return wrapping.textContent.trim();
  // try aria-label
  if (el.getAttribute("aria-label")) return el.getAttribute("aria-label");
  return null;
}

function buildSelector(el, index) {
  // TODO: replace with composite (id + label + DOM position) once the strategy is finalized.
  if (el.id) return `#${CSS.escape(el.id)}`;
  return `personify-field-${index}`;
}

// ── 2. Decide (delegates to backend) ─────────────────────────────────────────

async function callBackend(fields) {
  const company = guessCompanyName();
  const jobDescription = scrapeJobDescription();

  // Send X-User-Id only when the host page set an identity. The /upload
  // and /autofill calls MUST agree on user_id or retrieval looks under the
  // wrong user and finds no chunks.
  const headers = { "Content-Type": "application/json" };
  const userId = await getUserId();
  if (userId) headers["X-User-Id"] = userId;

  const backendUrl = await resolveBackendUrl();
  const res = await fetch(`${backendUrl}/autofill`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      fields,
      job_description: jobDescription,
      company_name: company,
    }),
  });

  if (!res.ok) {
    throw new Error(`Backend returned ${res.status}`);
  }
  return res.json();
}

function guessCompanyName() {
  // Quick heuristic — improve in MLOps work.
  const titleParts = document.title.split(/[|\-—]/);
  return (titleParts[titleParts.length - 1] || "").trim();
}

function scrapeJobDescription() {
  // TODO (MLE): tailor scraping per portal.
  const candidates = document.querySelectorAll(
    "[class*='description'], [class*='job-description'], main"
  );
  for (const c of candidates) {
    const text = c.textContent?.trim();
    if (text && text.length > 200) return text.slice(0, 4000);
  }
  return "";
}

// ── 3. Act ───────────────────────────────────────────────────────────────────

function pasteResponses(responses) {
  let pasted = 0;

  for (const { selector, response } of responses) {
    const el = document.querySelector(selector);
    if (!el) {
      console.warn(`[Personify] Could not find ${selector} to paste into`);
      continue;
    }

    setNativeValue(el, response);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    pasted += 1;
  }

  return pasted;
}

/**
 * React/Vue intercept the native setter on input elements. To make the
 * framework "see" our update, we have to call the native setter directly.
 */
function setNativeValue(el, value) {
  const proto = Object.getPrototypeOf(el);
  const descriptor = Object.getOwnPropertyDescriptor(proto, "value");
  const setter = descriptor && descriptor.set;
  if (setter) setter.call(el, value);
  else el.value = value;
}

// ── Orchestration ────────────────────────────────────────────────────────────

async function runAutofill() {
  const fields = collectFields();
  console.log(`[Personify] Detected ${fields.length} fields`);

  if (fields.length === 0) {
    return { fields_detected: 0, fields_filled: 0 };
  }

  const data = await callBackend(fields);
  const filled = pasteResponses(data.responses);

  // Attach each answer's question label (from the fields we just scanned) so the
  // panels can match answers to question cards by stable label text, not only by
  // selector — selectors can drift, or be CSS-escaped, between the scan and run.
  const labelBySelector = {};
  fields.forEach((f) => { labelBySelector[f.selector] = f.label; });
  const responses = (data.responses || []).map((r) => ({
    selector: r.selector,
    response: r.response,
    label: labelBySelector[r.selector] || null,
  }));

  // Publish the generated responses so EVERY Personify UI instance (the
  // injected side panel and the toolbar popup) can show the answer under its
  // matching question — not only the panel that triggered the run. Keyed by
  // page URL so a panel on a different page doesn't pick these up. The popups
  // read this on open and react to changes live via chrome.storage.onChanged.
  if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
    chrome.storage.local.set({
      personify_last_responses: {
        url: location.href,
        ts: Date.now(),
        responses: responses,
      },
    });
  }

  return {
    fields_detected: fields.length,
    fields_filled: filled,
    pipeline_meta: data.meta,
    // Surface the per-field response array so the smoke-test UI can
    // show what was generated for each selector. The real extension
    // ignores this; only the fake page uses it.
    responses: responses,
  };
}

// ── Floating trigger button ───────────────────────────────────────────────────

// ── Sidebar panel (Simplify-style) ───────────────────────────────────────────

function injectSidebar() {
  if (document.getElementById("personify-sidebar-root")) return;

  // Wrapper keeps tab + iframe together so they move as one unit
  const root = document.createElement("div");
  root.id = "personify-sidebar-root";
  Object.assign(root.style, {
    position: "fixed",
    top: "0",
    right: "0",
    height: "100vh",
    zIndex: "2147483647",
    display: "flex",
    flexDirection: "row",
    alignItems: "flex-start",
    pointerEvents: "none",
  });

  // ── Tab trigger ──────────────────────────────────────────────────────────
  const tab = document.createElement("button");
  tab.id = "personify-tab";
  tab.title = "Personify";
  tab.innerHTML = `<img src="${chrome.runtime.getURL('icons/logo-transparent.png')}" width="28" height="28" style="display:block;" />`;
  Object.assign(tab.style, {
    pointerEvents: "auto",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: "2px",
    width: "40px",
    height: "72px",
    position: "fixed",
    top: "50%",
    right: "0",
    transform: "translateY(-50%)",
    background: "#ffffff",
    border: "none",
    borderRadius: "10px 0 0 10px",
    cursor: "pointer",
    boxShadow: "-3px 0 12px rgba(0,0,0,0.12)",
    transition: "width 0.15s, right 0.25s cubic-bezier(0.4,0,0.2,1)",
    flexShrink: "0",
  });
  tab.addEventListener("mouseenter", () => { tab.style.width = "44px"; });
  tab.addEventListener("mouseleave", () => { tab.style.width = "40px"; });

  // ── iframe panel ─────────────────────────────────────────────────────────
  const panel = document.createElement("iframe");
  panel.id = "personify-panel";
  panel.src = chrome.runtime.getURL("src/popup.html");
  Object.assign(panel.style, {
    pointerEvents: "auto",
    width: "360px",
    height: "100vh",
    border: "none",
    background: "#fff",
    boxShadow: "-4px 0 24px rgba(0,0,0,0.12)",
    transform: "translateX(360px)",
    transition: "transform 0.25s cubic-bezier(0.4,0,0.2,1)",
    alignSelf: "flex-start",
  });

  let open = false;
  tab.addEventListener("click", () => {
    open = !open;
    panel.style.transform = open ? "translateX(0)" : "translateX(360px)";
    tab.style.right = open ? "360px" : "0";
    // Re-scan on open so fields an SPA rendered after injection (e.g. Ashby's
    // application form) get picked up, instead of showing the stale snapshot
    // taken at document_idle.
    if (open && panel.contentWindow) {
      panel.contentWindow.postMessage({ source: "personify", type: "RESCAN" }, "*");
    }
  });

  root.appendChild(tab);
  root.appendChild(panel);
  document.body.appendChild(root);
}

if (typeof chrome !== "undefined" && chrome.runtime) {
  // On the dashboard, sync auth token to chrome.storage so the extension popup
  // can use it without a separate login. Next.js may serve on 3000 or 3001
  // (e.g. when 3000 is taken), so both origins count as "the dashboard".
  const DASHBOARD_ORIGINS = ["http://localhost:3000", "http://localhost:3001"];
  if (DASHBOARD_ORIGINS.includes(window.location.origin)) {
    const token = localStorage.getItem("token");
    const userId = localStorage.getItem("user_id");
    const userEmail = localStorage.getItem("user_email");
    if (token) {
      chrome.storage.local.set({ token, userId, userEmail });
    } else {
      chrome.storage.local.remove(["token", "userId", "userEmail"]);
    }
  } else {
    injectSidebar();
  }
}

// Expose for the fake job page (smoke test). The real extension calls
// runAutofill() via chrome.runtime messaging instead.
if (typeof window !== "undefined") {
  window.personifyRunAutofill = runAutofill;
}