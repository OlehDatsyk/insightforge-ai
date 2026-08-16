/**
 * history.js - powers both /history (all sessions, section 21) and
 * /reports (completed reports only) since they share the same table UI.
 */
(function () {
  const mode = window.__PAGE_MODE__ || "history";
  const tbody = document.getElementById("history-body");
  const searchBox = document.getElementById("search-box");
  const statusFilter = document.getElementById("status-filter");

  let allSessions = [];
  let activeStatus = "";

  function statusBadge(status) {
    const map = { completed: "badge-success", failed: "badge-danger", running: "badge-info", pending: "badge-neutral" };
    return `<span class="badge ${map[status] || "badge-neutral"}">${status}</span>`;
  }

  function rowHtml(s) {
    const resultHref = s.status === "completed" ? `/research/${s.id}` : `/research/${s.id}/progress`;
    if (mode === "reports") {
      return `<tr>
        <td><a href="${resultHref}">${escapeHtml(s.research_question)}</a></td>
        <td><span class="badge badge-neutral">${s.mode}</span></td>
        <td class="faint">${formatDate(s.created_at)}</td>
        <td class="flex-gap">
          <a class="btn btn-ghost btn-sm" href="${resultHref}">View</a>
          <button class="btn btn-danger btn-sm" data-delete="${s.id}">Delete</button>
        </td>
      </tr>`;
    }
    return `<tr>
      <td><a href="${resultHref}">${escapeHtml(s.research_question)}</a></td>
      <td><span class="badge badge-neutral">${s.mode}</span></td>
      <td>${statusBadge(s.status)}</td>
      <td class="faint">${formatDate(s.created_at)}</td>
      <td class="faint">${s.duration_seconds ? s.duration_seconds.toFixed(1) + "s" : "-"}</td>
      <td class="flex-gap">
        <a class="btn btn-ghost btn-sm" href="${resultHref}">Open</a>
        <button class="btn btn-danger btn-sm" data-delete="${s.id}">Delete</button>
      </td>
    </tr>`;
  }

  function render() {
    const query = (searchBox.value || "").toLowerCase();
    let list = allSessions.filter((s) => s.research_question.toLowerCase().includes(query));
    if (mode === "reports") {
      list = list.filter((s) => s.status === "completed");
    } else if (activeStatus) {
      list = list.filter((s) => s.status === activeStatus);
    }
    const colspan = mode === "reports" ? 4 : 6;
    tbody.innerHTML = list.length
      ? list.map(rowHtml).join("")
      : `<tr><td colspan="${colspan}" class="muted text-center" style="padding:32px 0">No results found.</td></tr>`;
  }

  tbody.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-delete]");
    if (!btn) return;
    const id = btn.dataset.delete;
    if (!confirm("Delete this research session permanently?")) return;
    try {
      await API.del(`/research/${id}`);
      allSessions = allSessions.filter((s) => s.id !== id);
      render();
      showToast("Research session deleted.", "success");
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  searchBox.addEventListener("input", render);
  if (statusFilter) {
    statusFilter.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      statusFilter.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeStatus = btn.dataset.status;
      render();
    });
  }

  (async function init() {
    try {
      allSessions = await API.get("/research?limit=200");
      render();
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="6" class="muted text-center">${escapeHtml(err.message)}</td></tr>`;
    }
  })();
})();
