// Candidate backend ports, tried in order. host_permissions covers
// http://localhost/* so any local port is reachable; we probe these two so
// the backend works whether it's running on 8000 or 8001 with zero config.
const BACKEND_CANDIDATES = ["http://localhost:8000", "http://localhost:8001"];

chrome.runtime.onInstalled.addListener(() => {
    console.log("[Personify] extension installed");
});

// Resolve to the first candidate whose /health responds OK.
async function pingBackend() {
    for (const base of BACKEND_CANDIDATES) {
        try {
            const r = await fetch(`${base}/health`);
            if (r.ok) {
                const data = await r.json();
                return { ok: true, data, backendUrl: base };
            }
        } catch (_e) {
            // Port not listening — try the next candidate.
        }
    }
    return { ok: false, error: "No backend reachable on " + BACKEND_CANDIDATES.join(" or ") };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message && message.type === "PING_BACKEND") {
        pingBackend().then(sendResponse);
        return true;
    }
});