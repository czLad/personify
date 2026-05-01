/**
 * Personify content script.
 *
 * Runs on supported job application portals. Responsible for:
 *   1. Scanning the DOM for form fields (Perceive)
 *   2. Sending those fields to the backend for classification + generation
 *   3. Pasting the generated responses into the right fields (Act)
 *
 * The intelligence (Decide) lives entirely in the backend. This script
 * never holds an API key and never calls an LLM directly.
 */

const BACKEND_URL = "http://localhost:8000";

// ── Listen for "Autofill" trigger from popup ─────────────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "AUTOFILL_TRIGGER") {
    runAutofill()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true; // keep the message channel open for async response
  }
});

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

  const res = await fetch(`${BACKEND_URL}/autofill`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  return {
    fields_detected: fields.length,
    fields_filled: filled,
    pipeline_meta: data.meta,
  };
}
