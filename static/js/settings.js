/**
 * settings.js - Provider Routing Dashboard (section 25). Lets the user
 * choose primary/fallback/secondary-fallback providers and per-stage
 * routing. Never touches API keys - those are environment-only.
 */
(function () {
  const ROUTE_SELECTS = ["primary", "fallback", "secondary_fallback", "planning", "analysis", "crosscheck", "synthesis"];

  function buildOptions(providers, includeAuto) {
    const opts = providers.map((p) => `<option value="${p}">${p[0].toUpperCase() + p.slice(1)}</option>`);
    if (includeAuto) opts.unshift(`<option value="auto">Auto (use fallback chain)</option>`);
    return opts.join("");
  }

  async function loadProviderStatus() {
    const el = document.getElementById("provider-status");
    try {
      const providers = await API.get("/providers");
      el.innerHTML = providers
        .map(
          (p) => `<div class="stat-card" style="flex:1;min-width:160px">
            <div class="flex-between">
              <strong style="text-transform:capitalize">${p.name}</strong>
              <span class="badge ${p.configured ? "badge-success" : "badge-neutral"}">${p.configured ? "Configured" : "Not Configured"}</span>
            </div>
            <div class="faint mt-1" style="font-size:12px">${escapeHtml(p.model)}</div>
          </div>`
        )
        .join("");
      el.style.display = "flex";
      el.style.flexWrap = "wrap";
      el.style.gap = "10px";
      return providers.filter((p) => p.configured).map((p) => p.name);
    } catch (err) {
      el.innerHTML = `<span class="muted">${escapeHtml(err.message)}</span>`;
      return [];
    }
  }

  async function loadRouting(configuredProviders) {
    try {
      const routing = await API.get("/settings/routing");
      ROUTE_SELECTS.forEach((key) => {
        const select = document.getElementById(`route-${key}`);
        const includeAuto = !["primary", "fallback", "secondary_fallback"].includes(key);
        select.innerHTML = buildOptions(configuredProviders.length ? configuredProviders : ["openai", "anthropic", "gemini"], includeAuto);
        if ([...select.options].some((o) => o.value === routing[key])) {
          select.value = routing[key];
        }
      });
    } catch (err) {
      showToast("Could not load routing settings: " + err.message, "error");
    }
  }

  async function loadLimits() {
    const el = document.getElementById("limits-grid");
    try {
      const cfg = await API.get("/config/status");
      const limits = cfg.limits;
      el.innerHTML = Object.entries(limits)
        .map(
          ([key, value]) => `<div class="stat-card">
            <div class="stat-label">${key.replace(/_/g, " ")}</div>
            <div class="stat-value" style="font-size:20px">${value}</div>
          </div>`
        )
        .join("");
    } catch (err) {
      el.innerHTML = `<span class="muted">${escapeHtml(err.message)}</span>`;
    }
  }

  document.getElementById("save-routing-btn").addEventListener("click", async () => {
    const payload = {};
    ROUTE_SELECTS.forEach((key) => {
      payload[key] = document.getElementById(`route-${key}`).value;
    });
    try {
      await API.post("/settings/routing", payload);
      showToast("Routing preferences saved.", "success");
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  (async function init() {
    const configured = await loadProviderStatus();
    await loadRouting(configured);
    await loadLimits();
  })();
})();
