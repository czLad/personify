const MOCK_QUESTIONS = [
  { selector: "#field_1", label: "Why do you want to work at this company?" },
  { selector: "#field_2", label: "Describe a time you solved a difficult technical problem." },
  { selector: "#field_3", label: "What makes you a strong candidate for this role?" },
];

// Mock generated responses — swap these out when wiring to backend
const MOCK_RESPONSES = {
  "#field_1": "I've long admired this company's mission to build tools that empower people. My background in full-stack engineering and my passion for developer-focused products make this an exciting opportunity to contribute meaningfully from day one.",
  "#field_2": "During my internship, our deployment pipeline was taking 45 minutes per run. I profiled the bottlenecks, parallelized the test suite, and introduced caching for unchanged modules — cutting build time to under 8 minutes and unblocking the whole team.",
  "#field_3": "I bring a rare combination of strong frontend instincts and backend depth. I've shipped production features across the full stack, I move fast without cutting corners, and I care deeply about the user experience behind every technical decision.",
};

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("tab-" + tab.dataset.tab).classList.add("active");
  });
});

function renderQuestions(questions) {
  var list = document.getElementById("questions-list");
  var empty = document.getElementById("no-questions");
  var loading = document.getElementById("loading");

  loading.style.display = "none";

  if (!questions || questions.length === 0) {
    empty.style.display = "block";
    return;
  }

  list.innerHTML = "";

  questions.forEach(function(q) {
    var card = document.createElement("div");
    card.className = "question-card";
    card.innerHTML =
      '<div class="question-label">Detected question</div>' +
      '<div class="question-text">' + q.label + '</div>' +
      '<button class="autofill-btn" data-selector="' + q.selector + '">Autofill</button>' +
      '<div class="card-status"></div>' +
      '<div class="response-box" style="display:none"></div>';

    var btn = card.querySelector(".autofill-btn");
    var status = card.querySelector(".card-status");
    var responseBox = card.querySelector(".response-box");

    btn.addEventListener("click", function() {
      btn.disabled = true;
      btn.textContent = "Generating…";
      status.textContent = "";
      status.className = "card-status";
      responseBox.style.display = "none";

      // TODO: replace setTimeout with real backend call
      // chrome.tabs.sendMessage(tabId, { type: "AUTOFILL_TRIGGER", selector: q.selector }, ...)
      setTimeout(function() {
        var response = MOCK_RESPONSES[q.selector] || "Generated response will appear here.";

        btn.textContent = "✓ Filled";
        btn.classList.add("done");
        status.textContent = "Response pasted into field";
        status.className = "card-status ok";

        responseBox.textContent = response;
        responseBox.style.display = "block";
      }, 1000);
    });

    list.appendChild(card);
  });
}

renderQuestions(MOCK_QUESTIONS);
