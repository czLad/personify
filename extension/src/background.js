const BACKEND_URL = "http://localhost:8000";

chrome.runtime.onInstalled.addListener(() => {
    console.log("[Personify] extension installed");
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message && message.type === "PING_BACKEND") {
        fetch(`${BACKEND_URL}/health`)
            .then((r) => r.json())
            .then((data) => sendResponse({ ok: true, data }))
            .catch((err) => sendResponse({ ok: false, error: err.message }));
        return true;
    }
});