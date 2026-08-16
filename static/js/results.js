/**
 * results.js - renders the final structured research report: executive
 * summary, key findings, detailed analysis, comparison, conflicting
 * information, limitations, conclusion, and sources with quality scoring
 * (sections 12, 13, 14, 19). Also wires up export buttons (section 20).
 */
(function () {
  const root = document.getElementById("results-root");
  const sessionId = root.dataset.sessionId;
  const body = document.getElementById("results-body");

  function qualityBars(score) {
    const filled = Math.round((score || 0) * 5);
    let html = '<div class="quality-bar">';
    for (let i = 0; i < 5; i++) {
      const on = i < filled;
      html += `<span style="background:${on ? "var(--accent-soft)" : "var(--border)"}"></span>`;
    }
    html += "</div>";
    return html;
  }

  function trustBadge(label) {
    const map = { verified: "badge-success", conflicting: "badge-danger", uncertain: "badge-warning" };
    return `<span class="badge ${map[label] || "badge-neutral"}">${label}</span>`;
  }

  function renderSources(sources) {
    if (!sources.length) return '<p class="muted">No sources were collected.</p>';
    return `<div class="source-list">${sources
      .map(
        (s) => `<div class="source-card">
          <div class="flex-between">
            <a class="source-title" href="${s.url}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.title)}</a>
            ${trustBadge(s.trust_label)}
          </div>
          <div class="source-meta">
            <span>${escapeHtml(s.domain)}</span>
            <span>Relevance ${Math.round(s.relevance_score * 100)}%</span>
            <span>Bias risk: ${s.bias_risk}</span>
            ${qualityBars(s.overall_quality)}
          </div>
          <div class="source-summary">${escapeHtml(s.summary)}</div>
        </div>`
      )
      .join("")}</div>`;
  }

  function renderConflicts(conflicts) {
    if (!conflicts || !conflicts.length) {
      return '<p class="muted">✅ No conflicting information was detected between sources.</p>';
    }
    return conflicts
      .map(
        (c) => `<div class="conflict-card mt-1">
          <h4>⚠️ Conflicting information: ${escapeHtml(c.topic)}</h4>
          <p class="muted" style="margin:0">${escapeHtml(c.description)}</p>
          <div class="conflict-sides">
            <div class="conflict-side"><b>${escapeHtml(c.source_a_title)}</b>${escapeHtml(c.source_a_value)}</div>
            <div class="conflict-side"><b>${escapeHtml(c.source_b_title)}</b>${escapeHtml(c.source_b_value)}</div>
          </div>
        </div>`
      )
      .join("");
  }

  function renderReport(session) {
    const r = session.report;
    if (!r) {
      body.innerHTML = `<div class="empty-state">
        <div class="icon">⏳</div>
        <p>This research session hasn't finished yet.</p>
        <a class="btn btn-primary btn-sm" href="/research/${sessionId}/progress">View progress</a>
      </div>`;
      return;
    }

    body.innerHTML = `
      <div class="flex-between">
        <div>
          <h1 class="mb-0">${escapeHtml(r.title)}</h1>
          <p class="muted mt-0">${escapeHtml(session.research_question)}</p>
        </div>
      </div>

      <div class="flex-gap mt-1">
        <div class="pill-select" id="export-buttons">
          ${["markdown", "html", "pdf", "txt", "json"]
            .map((f) => `<button data-format="${f}">${f.toUpperCase()}</button>`)
            .join("")}
        </div>
        <span class="faint" style="font-size:12px">Export report</span>
      </div>

      <div class="card mt-2">
        <div class="section-title">Executive Summary</div>
        <p>${escapeHtml(r.executive_summary)}</p>
      </div>

      ${r.methodology ? `<div class="card"><div class="section-title">Methodology</div><p>${escapeHtml(r.methodology)}</p></div>` : ""}

      ${
        r.key_findings.length
          ? `<div class="card"><div class="section-title">Key Findings</div><ul style="padding-left:20px">${r.key_findings
              .map((f) => `<li>${escapeHtml(f)}</li>`)
              .join("")}</ul></div>`
          : ""
      }

      ${r.detailed_analysis ? `<div class="card"><div class="section-title">Detailed Analysis</div><p style="white-space:pre-wrap">${escapeHtml(r.detailed_analysis)}</p></div>` : ""}

      ${r.comparison ? `<div class="card"><div class="section-title">Comparison</div><p style="white-space:pre-wrap">${escapeHtml(r.comparison)}</p></div>` : ""}

      <div class="card">
        <div class="section-title">Conflicting Information</div>
        ${renderConflicts(r.conflicts)}
      </div>

      ${
        r.limitations.length
          ? `<div class="card"><div class="section-title">Limitations</div><ul style="padding-left:20px">${r.limitations
              .map((l) => `<li>${escapeHtml(l)}</li>`)
              .join("")}</ul></div>`
          : ""
      }

      ${r.conclusion ? `<div class="card"><div class="section-title">Conclusion</div><p>${escapeHtml(r.conclusion)}</p></div>` : ""}

      <div class="card">
        <div class="section-title">Sources (${r.sources_json.length})</div>
        ${renderSources(r.sources_json)}
      </div>
    `;

    document.getElementById("export-buttons").addEventListener("click", async (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      const format = btn.dataset.format;
      btn.disabled = true;
      try {
        await API.downloadExport(sessionId, format);
        showToast(`Exported as ${format.toUpperCase()}`, "success");
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        btn.disabled = false;
      }
    });
  }

  (async function init() {
    try {
      const session = await API.get(`/research/${sessionId}`);
      renderReport(session);
    } catch (err) {
      body.innerHTML = `<div class="empty-state"><div class="icon">⚠️</div><p>${escapeHtml(err.message)}</p></div>`;
    }
  })();
})();
