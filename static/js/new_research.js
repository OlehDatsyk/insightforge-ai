/**
 * new_research.js - mode selector + submission for starting a research
 * session (section 15: Quick / Standard / Deep / Custom modes).
 */
(function () {
  let selectedMode = "quick";
  const modeGrid = document.getElementById("mode-grid");
  const customFields = document.getElementById("custom-fields");
  const submitBtn = document.getElementById("submit-btn");
  const errorEl = document.getElementById("form-error");

  modeGrid.addEventListener("click", (e) => {
    const option = e.target.closest(".mode-option");
    if (!option) return;
    modeGrid.querySelectorAll(".mode-option").forEach((el) => el.classList.remove("selected"));
    option.classList.add("selected");
    selectedMode = option.dataset.mode;
    customFields.style.display = selectedMode === "custom" ? "grid" : "none";
  });

  submitBtn.addEventListener("click", async () => {
    errorEl.textContent = "";
    const question = document.getElementById("question").value.trim();
    if (question.length < 5) {
      errorEl.textContent = "Please enter a research question of at least 5 characters.";
      return;
    }

    const payload = { research_question: question, mode: selectedMode };
    if (selectedMode === "custom") {
      payload.max_tasks = parseInt(document.getElementById("custom-tasks").value, 10) || 5;
      payload.max_sources = parseInt(document.getElementById("custom-sources").value, 10) || 8;
    }

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Starting...';
    try {
      const session = await API.post("/research", payload);
      window.location.href = `/research/${session.id}/progress`;
    } catch (err) {
      errorEl.textContent = err.message;
      submitBtn.disabled = false;
      submitBtn.textContent = "Start Research";
    }
  });
})();
