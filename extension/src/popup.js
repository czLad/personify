const statusEl = document.getElementById("status");

function setStatus(text, kind = "") {
  statusEl.textContent = text;
  statusEl.className = `status ${kind}`;
}

document.getElementById("ping-btn").addEventListener("click", () => {
  setStatus("Pinging backend…");
  chrome.runtime.sendMessage({ type: "PING_BACKEND" }, (resp) => {
    if (resp?.ok) {
      setStatus(`Backend OK (${resp.data.service})`, "ok");
    } else {
      setStatus(`Backend unreachable: ${resp?.error || "unknown"}`, "err");
    }
  });
});

document.getElementById("autofill-btn").addEventListener("click", async () => {
  setStatus("Running autofill…");
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  chrome.tabs.sendMessage(tab.id, { type: "AUTOFILL_TRIGGER" }, (resp) => {
    if (chrome.runtime.lastError) {
      setStatus("Open a job application page first", "err");
      return;
    }
    if (resp?.ok) {
      const r = resp.result;
      setStatus(`Filled ${r.fields_filled} of ${r.fields_detected} fields`, "ok");
    } else {
      setStatus(`Error: ${resp?.error || "unknown"}`, "err");
    }
  });
});
