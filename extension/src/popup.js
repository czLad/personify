// ── Prompt variant classifier ─────────────────────────────────────────────────
var MOTIVATION_CUES = /\b(why|what (draws|excites|motivates)|interested in|reasons? (you|to)|this (role|company|position|team)|fit for)\b/i;
var STORY_CUES = /\b(describe a (time|situation|challenge|project|moment)|tell us about a (time|situation|challenge|project)|give an example|walk us through|a time when|when (you|did))\b/i;
var SKIP = /\b(email|phone|url|linkedin|website|address|city|state|zip|country|name|first|last|salary|date|start|end|referral|how did you hear)\b/i;

function classifyQuestion(label) {
    if (MOTIVATION_CUES.test(label)) return { variant: "motivation", color: "#6D65FC", emoji: "💡" };
    if (STORY_CUES.test(label)) return { variant: "story", color: "#e67e22", emoji: "📖" };
    return { variant: "background", color: "#1e8449", emoji: "👤" };
}
function isPersonalStatement(label) {
  var SKIP = /\b(email|phone|url|linkedin|website|address|city|state|zip|country|name|first|last|salary|date|start|end|referral|how did you hear|backend|github|twitter)\b/i;
  if (SKIP.test(label)) return false;
  if (label.length < 10) return false;
  return true;
}

// ── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach(function(tab) {
    tab.addEventListener("click", function() {
        document.querySelectorAll(".tab").forEach(function(t) { t.classList.remove("active"); });
        document.querySelectorAll(".tab-content").forEach(function(c) { c.classList.remove("active"); });
        tab.classList.add("active");
        document.getElementById("tab-" + tab.dataset.tab).classList.add("active");
    });
});

// ── Render questions ──────────────────────────────────────────────────────────
function renderQuestions(questions) {
    questions = questions.filter(function(q) { return isPersonalStatement(q.label); });
    var list = document.getElementById("questions-list");
    var empty = document.getElementById("no-questions");
    var loading = document.getElementById("loading");
    var footer = document.getElementById("autofill-footer");

    loading.style.display = "none";

    if (!questions || questions.length === 0) {
        list.innerHTML = "";
        empty.style.display = "block";
        if (footer) footer.style.display = "none";
        return;
    }

    list.innerHTML = "";
    empty.style.display = "none";
    if (footer) footer.style.display = "block";

    questions.forEach(function(q) {
        var classification = classifyQuestion(q.label);
        var card = document.createElement("div");
        card.className = "question-card";
        card.dataset.selector = q.selector;
        card.innerHTML =
          '<div class="question-label">Detected question</div>' +
          '<div class="question-text">' + q.label + '</div>' +
          '<div class="response-box" style="display:none"></div>';
        list.appendChild(card);
    });
}

// ── Populate responses ────────────────────────────────────────────────────────
// Match each answer to its question card WITHOUT putting the selector inside an
// attribute-value query: the selector is CSS-escaped (e.g. "#\\35 b15..." for an
// id starting with a digit), and a [data-selector="..."] query would re-interpret
// that escape and fail to match the literally-stored value. So we compare in JS
// with === instead. Falls back to matching by question label text, which stays
// stable even if the page's element ids/positions drift between scan and run.
function populateResponses(responses) {
    var cards = document.querySelectorAll(".question-card");
    responses.forEach(function(r) {
        var card = null;
        for (var i = 0; i < cards.length && !card; i++) {
            if (cards[i].dataset.selector === r.selector) card = cards[i];
        }
        if (!card && r.label) {
            for (var j = 0; j < cards.length && !card; j++) {
                var qt = cards[j].querySelector(".question-text");
                if (qt && qt.textContent.trim() === String(r.label).trim()) card = cards[j];
            }
        }
        if (!card) return;
        var box = card.querySelector(".response-box");
        if (box) {
            box.textContent = r.response;
            box.style.display = "block";
        }
    });
}

// ── Personify all button ──────────────────────────────────────────────────────
var personifyBtn = document.getElementById("personify-all-btn");
var footerStatus = document.getElementById("footer-status");

if (personifyBtn) {
    personifyBtn.addEventListener("click", function() {
        personifyBtn.disabled = true;
        personifyBtn.textContent = "Generating";
        personifyBtn.classList.add("loading-dots");
        if (footerStatus) { footerStatus.textContent = ""; footerStatus.className = "card-status"; }

        chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
            chrome.tabs.sendMessage(tabs[0].id, { type: "AUTOFILL_TRIGGER" }, function(resp) {
                personifyBtn.classList.remove("loading-dots");

                if (chrome.runtime.lastError || !resp) {
                    personifyBtn.textContent = "⟡ Personify My Application";
                    personifyBtn.disabled = false;
                    if (footerStatus) {
                        footerStatus.textContent = "Error: " + (chrome.runtime.lastError ? chrome.runtime.lastError.message : "No response");
                        footerStatus.className = "card-status err";
                    }
                    return;
                }

                if (resp.ok) {
                    populateResponses(resp.result.responses || []);
                    personifyBtn.textContent = "✓ Done";
                    personifyBtn.classList.add("done");
                    if (footerStatus) {
                        footerStatus.textContent = "Filled " + resp.result.fields_filled + " of " + resp.result.fields_detected + " fields";
                        footerStatus.className = "card-status ok";
                    }
                } else {
                    personifyBtn.textContent = "⟡ Personify My Application";
                    personifyBtn.disabled = false;
                    if (footerStatus) {
                        footerStatus.textContent = "Error: " + (resp.error || "unknown");
                        footerStatus.className = "card-status err";
                    }
                }
            });
        });
    });
}

// ── Profile tab ──────────────────────────────────────────────────────────────
// Backend URL resolution — mirrors content_script.js / background.js: probe
// each candidate's /health and use the first that answers, so the popup's
// login and /documents calls work whether the backend runs on 8000 or 8001.
// Cached after the first successful probe.
var BACKEND_CANDIDATES = ["http://localhost:8000", "http://localhost:8001"];
var _resolvedBackend = null;

function resolveBackend() {
    if (_resolvedBackend) return Promise.resolve(_resolvedBackend);
    return (function tryNext(i) {
        if (i >= BACKEND_CANDIDATES.length) return BACKEND_CANDIDATES[0]; // fallback
        var base = BACKEND_CANDIDATES[i];
        return fetch(base + "/health")
            .then(function(r) {
                if (r.ok) { _resolvedBackend = base; return base; }
                return tryNext(i + 1);
            })
            .catch(function() { return tryNext(i + 1); });
    })(0);
}

var loginBtn = document.getElementById("login-btn");
if (loginBtn) {
    loginBtn.addEventListener("click", function() {
        var email = document.getElementById("login-email").value.trim();
        var password = document.getElementById("login-password").value;
        var errorEl = document.getElementById("login-error");
        errorEl.style.display = "none";
        loginBtn.disabled = true;
        loginBtn.textContent = "Signing in…";

        resolveBackend().then(function(BACKEND) {
            fetch(BACKEND + "/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email: email, password: password }),
            })
            .then(function(r) { return r.ok ? r.json() : r.json().then(function(e) { throw new Error(e.detail || "Login failed"); }); })
            .then(function(data) {
                chrome.storage.local.set({
                    token: data.access_token,
                    userId: data.user_id,
                    userEmail: email,
                }, function() {
                    loadProfile();
                });
            })
            .catch(function(err) {
                errorEl.textContent = err.message;
                errorEl.style.display = "block";
                loginBtn.disabled = false;
                loginBtn.textContent = "Sign in";
            });
        });
    });
}

function loadProfile() {
    chrome.storage.local.get(["token", "userId", "userEmail"], function(data) {
        var loading = document.getElementById("profile-loading");
        var signedOut = document.getElementById("profile-signed-out");
        var content = document.getElementById("profile-content");

        if (!data.token) {
            loading.style.display = "none";
            signedOut.style.display = "block";
            return;
        }

        var headers = { "Authorization": "Bearer " + data.token };
        if (data.userId) headers["X-User-Id"] = data.userId;

        // Show email from storage immediately, then confirm with /auth/me
        var email = data.userEmail || data.userId || "Unknown";
        var initial = email[0].toUpperCase();
        document.getElementById("profile-avatar").textContent = initial;
        document.getElementById("profile-name").textContent = email.split("@")[0];
        document.getElementById("profile-email").textContent = email;

        loading.style.display = "none";
        content.style.display = "block";

        // Fetch real documents from backend
        resolveBackend().then(function(BACKEND) {
            fetch(BACKEND + "/documents", { headers: headers })
                .then(function(r) { return r.ok ? r.json() : []; })
                .then(function(docs) {
                    var hasResume = docs.some(function(d) { return d.doc_type === "resume"; });
                    var hasOther = docs.some(function(d) { return d.doc_type !== "resume"; });
                    var resumeEl = document.getElementById("profile-resume-status");
                    var docsEl = document.getElementById("profile-docs-status");
                    resumeEl.textContent = hasResume ? "✓ Uploaded" : "Not uploaded";
                    resumeEl.className = "profile-value " + (hasResume ? "profile-ok" : "");
                    docsEl.textContent = hasOther ? "✓ Uploaded" : "None";
                    docsEl.className = "profile-value " + (hasOther ? "profile-ok" : "");
                })
                .catch(function() {
                    document.getElementById("profile-resume-status").textContent = "—";
                    document.getElementById("profile-docs-status").textContent = "—";
                });
        });
    });
}

// Load profile when profile tab is clicked
document.querySelectorAll(".tab").forEach(function(tab) {
    if (tab.dataset.tab === "profile") {
        tab.addEventListener("click", loadProfile);
    }
});

// ── Stored autofill responses ─────────────────────────────────────────────────
// The content script writes the generated answers to chrome.storage after a
// run. Every panel instance (this toolbar popup AND the injected side panel)
// reads them here, so the answer shows under its question regardless of which
// panel triggered the run. Scoped by page URL so answers from one page don't
// appear on a panel attached to a different page.
function applyStoredResponses(stored) {
    if (!stored || !stored.responses || !stored.responses.length) return;
    if (typeof chrome === "undefined" || !chrome.tabs) {
        populateResponses(stored.responses);
        return;
    }
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
        var url = tabs && tabs[0] && tabs[0].url;
        if (url && stored.url && url === stored.url) {
            populateResponses(stored.responses);
        }
    });
}

function loadStoredResponses() {
    if (typeof chrome === "undefined" || !chrome.storage || !chrome.storage.local) return;
    chrome.storage.local.get(["personify_last_responses"], function(data) {
        applyStoredResponses(data && data.personify_last_responses);
    });
}

// Live update: when a run completes anywhere, refresh this panel too.
if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.onChanged) {
    chrome.storage.onChanged.addListener(function(changes, area) {
        if (area === "local" && changes.personify_last_responses) {
            applyStoredResponses(changes.personify_last_responses.newValue);
        }
    });
}

// ── Scan the active tab for fields ────────────────────────────────────────────
// Uses chrome.tabs from popup context (not service worker). Called on load and
// again each time the injected side panel is reopened, so fields a single-page
// app (e.g. Ashby) renders AFTER the panel first loaded still get picked up.
function doScan() {
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
        if (!tabs || !tabs[0]) {
            renderQuestions([]);
            return;
        }
        chrome.tabs.sendMessage(tabs[0].id, { type: "SCAN_FIELDS" }, function(resp) {
            if (chrome.runtime.lastError || !resp) {
                renderQuestions([]);
                return;
            }
            renderQuestions(resp.fields || []);
            // Cards now exist — backfill any answers from a previous run on
            // this page (covers opening a panel after autofill already ran).
            loadStoredResponses();
        });
    });
}

// The content script posts this when the user opens the side panel, so the
// panel re-scans at that moment (matching how the toolbar popup scans on open).
window.addEventListener("message", function(e) {
    if (e.data && e.data.source === "personify" && e.data.type === "RESCAN") {
        doScan();
    }
});

doScan();