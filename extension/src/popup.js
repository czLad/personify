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
  var SKIP = /\b(email|phone|url|linkedin|website|address|city|state|zip|country|name|first|last|salary|date|start|end|referral|how did you hear|backend|github|cover letter|twitter)\b/i;
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
        empty.style.display = "block";
        if (footer) footer.style.display = "none";
        return;
    }

    list.innerHTML = "";
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
function populateResponses(responses) {
    responses.forEach(function(r) {
        var card = document.querySelector('.question-card[data-selector="' + r.selector + '"]');
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
const BACKEND = "http://localhost:8000";

var loginBtn = document.getElementById("login-btn");
if (loginBtn) {
    loginBtn.addEventListener("click", function() {
        var email = document.getElementById("login-email").value.trim();
        var password = document.getElementById("login-password").value;
        var errorEl = document.getElementById("login-error");
        errorEl.style.display = "none";
        loginBtn.disabled = true;
        loginBtn.textContent = "Signing in…";

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
}

// Load profile when profile tab is clicked
document.querySelectorAll(".tab").forEach(function(tab) {
    if (tab.dataset.tab === "profile") {
        tab.addEventListener("click", loadProfile);
    }
});

// ── Auto scan on popup open ───────────────────────────────────────────────────
// Uses chrome.tabs from popup context (not service worker)
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
    });
});
