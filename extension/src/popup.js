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
