/**
 * progress.js - live research progress view. Uses Server-Sent Events for
 * real-time updates (section 18) with a polling fallback if SSE fails.
 *
 * IMPORTANT: only ever renders the safe, high-level progress log the
 * backend produces (session.progress_log) - never any hidden model
 * reasoning/chain-of-thought (section 11).
 */
(function () {
  const container = document.querySelector("[data-session-id]");
  const sessionId = container.dataset.sessionId;

  const STAGES = [
    { key: "planning", label: "Planning research" },
    { key: "searching", label: "Searching sources" },
    { key: "analyzing", label: "Analyzing sources" },
    { key: "crosschecking", label: "Cross-checking information" },
    { key: "synthesizing", label: "Generating report" },
  ];

  const stageList = document.getElementById("stage-list");
  const logFeed = document.getElementById("log-feed");
  const progressFill = document.getElementById("overall-fill");
  const progressPercent = document.getElementById("progress-percent");
  const statusBadge = document.getElementById("status-badge");
  const questionText = document.getElementById("question-text");
  const actions = document.getElementById("progress-actions");
  const viewResultsBtn = document.getElementById("view-results-btn");

  stageList.innerHTML = STAGES.map(
    (s) => `<div class="stage-row" data-stage="${s.key}">
      <div class="stage-dot">•</div>
      <div class="stage-info">
        <div class="stage-name">${s.label}</div>
      </div>
    </div>`
  ).join("");

  const seenLogTimestamps = new Set();

  function renderStages(currentStage, status) {
    const idx = STAGES.findIndex((s) => s.key === currentStage);
    STAGES.forEach((s, i) => {
      const row = stageList.querySelector(`[data-stage="${s.key}"]`);
      row.classList.remove("done", "active", "failed");
      const dot = row.querySelector(".stage-dot");
      if (status === "failed" && i === idx) {
        row.classList.add("failed");
        dot.textContent = "✕";
      } else if (i < idx || status === "completed") {
        row.classList.add("done");
        dot.textContent = "✓";
      } else if (i === idx) {
        row.classList.add("active");
        dot.textContent = i + 1;
      } else {
        dot.textContent = i + 1;
      }
    });
  }

  function appendLogs(entries) {
    entries.forEach((entry) => {
      const key = entry.timestamp + entry.message;
      if (seenLogTimestamps.has(key)) return;
      seenLogTimestamps.add(key);
      const line = document.createElement("div");
      line.className = "log-line";
      const time = new Date(entry.timestamp).toLocaleTimeString();
      line.innerHTML = `<span class="log-time">${time}</span><span>✓ ${escapeHtml(entry.message)}</span>`;
      logFeed.prepend(line);
    });
  }

  function applyUpdate(data) {
    progressFill.style.width = `${data.progress_percent}%`;
    progressPercent.textContent = `${data.progress_percent}%`;
    renderStages(data.stage, data.status);
    if (data.log && data.log.length) appendLogs(data.log);

    if (data.status === "completed") {
      statusBadge.textContent = "completed";
      statusBadge.className = "badge badge-success";
      actions.style.display = "block";
      viewResultsBtn.href = `/research/${sessionId}`;
      setTimeout(() => (window.location.href = `/research/${sessionId}`), 1200);
    } else if (data.status === "failed") {
      statusBadge.textContent = "failed";
      statusBadge.className = "badge badge-danger";
      showToast(data.error_message || "Research failed.", "error");
    } else {
      statusBadge.textContent = data.status;
      statusBadge.className = "badge badge-info";
    }
  }

  async function loadInitial() {
    try {
      const session = await API.get(`/research/${sessionId}`);
      questionText.textContent = session.research_question;
      applyUpdate({
        status: session.status,
        stage: session.current_stage,
        progress_percent: session.progress_percent,
        error_message: session.error_message,
        log: session.progress_log,
      });
      if (session.status === "completed") {
        window.location.href = `/research/${sessionId}`;
        return true;
      }
      return false;
    } catch (err) {
      showToast(err.message, "error");
      return true;
    }
  }

  async function pollFallback() {
    const done = await loadInitial();
    if (!done) setTimeout(pollFallback, 2500);
  }

  (async function init() {
    const done = await loadInitial();
    if (done) return;

    if (window.EventSource) {
      const source = API.streamProgress(sessionId, applyUpdate);
      source.onerror = () => {
        source.close();
        pollFallback();
      };
    } else {
      pollFallback();
    }
  })();
})();
