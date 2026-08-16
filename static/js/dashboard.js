/**
 * dashboard.js - populates the dashboard's stat cards, provider status
 * panel, and recent-sessions list (section 17).
 */
(async function () {
  const statGrid = document.getElementById("stat-grid");
  const providerList = document.getElementById("provider-status-list");
  const recentList = document.getElementById("recent-sessions");

  function statCard(label, value, sub) {
    return `<div class="stat-card">
      <div class="stat-label">${label}</div>
      <div class="stat-value">${value}</div>
      ${sub ? `<div class="stat-sub">${sub}</div>` : ""}
    </div>`;
  }

  function statusBadge(status) {
    const map = {
      completed: "badge-success",
      failed: "badge-danger",
      running: "badge-info",
      pending: "badge-neutral",
    };
    return `<span class="badge ${map[status] || "badge-neutral"}">${status}</span>`;
  }

  try {
    const sessions = await API.get("/research?limit=100");
    const completed = sessions.filter((s) => s.status === "completed");
    const totalSources = completed.length; // placeholder aggregate; refined below via session detail is costly, keep simple
    const avgDuration = completed.length
      ? (completed.reduce((sum, s) => sum + (s.duration_seconds || 0), 0) / completed.length).toFixed(1) + "s"
      : "-";

    statGrid.innerHTML =
      statCard("Total Sessions", sessions.length) +
      statCard("Completed", completed.length) +
      statCard("Success Rate", sessions.length ? Math.round((completed.length / sessions.length) * 100) + "%" : "-") +
      statCard("Avg. Duration", avgDuration);

    if (!sessions.length) {
      recentList.innerHTML = `<div class="empty-state"><div class="icon">🗂️</div><p>No research yet.</p><a class="btn btn-primary btn-sm" href="/research/new">Start your first research</a></div>`;
    } else {
      recentList.innerHTML = sessions
        .slice(0, 8)
        .map(
          (s) => `<div class="flex-between" style="padding:10px 0;border-bottom:1px solid var(--border)">
            <div style="min-width:0">
              <a href="${s.status === 'completed' ? '/research/' + s.id : '/research/' + s.id + '/progress'}" style="font-weight:600;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:340px">${escapeHtml(s.research_question)}</a>
              <span class="faint" style="font-size:12px">${formatDate(s.created_at)} · ${s.mode}</span>
            </div>
            ${statusBadge(s.status)}
          </div>`
        )
        .join("");
    }
  } catch (err) {
    statGrid.innerHTML = `<div class="empty-state">Could not load dashboard stats: ${escapeHtml(err.message)}</div>`;
    recentList.innerHTML = "";
  }

  try {
    const providers = await API.get("/providers");
    providerList.innerHTML = providers
      .map(
        (p) => `<div class="stat-card" style="flex:1;min-width:150px">
          <div class="flex-between">
            <strong style="text-transform:capitalize">${p.name}</strong>
            <span class="badge ${p.configured ? "badge-success" : "badge-neutral"}">${p.configured ? "Configured" : "Not Configured"}</span>
          </div>
          <div class="faint mt-1" style="font-size:12px">${escapeHtml(p.model)}</div>
          ${p.role.length ? `<div class="faint" style="font-size:11px;margin-top:4px">Role: ${p.role.join(", ")}</div>` : ""}
        </div>`
      )
      .join("");
    providerList.style.display = "flex";
    providerList.style.flexWrap = "wrap";
    providerList.style.gap = "10px";
  } catch (err) {
    providerList.innerHTML = `<span class="muted">Could not load provider status.</span>`;
  }
})();
