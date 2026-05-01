/**
 * Personify background service worker.
 *
 * Manifest V3 service workers are non-persistent — they spin up on demand
 * and shut down when idle. We use this for:
 *   - Storing/retrieving the user's session token
 *   - Relaying messages between the popup and content scripts
 *   - Future: scheduled jobs via chrome.alarms
 */

const BACKEND_URL = "http://localhost:8000";

chrome.runtime.onInstalled.addListener(() => {
  console.log("[Personify] extension installed");
});

// Health check from the popup
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "PING_BACKEND") {
    fetch(`${BACKEND_URL}/health`)
      .then((r) => r.json())
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }
});
