/**
 * api.js
 * ======
 * Thin wrapper around fetch() for talking to the InsightForge AI backend.
 * Centralizes error handling so every page shows consistent, friendly
 * error messages instead of raw exceptions.
 */
const API = (() => {
  async function request(path, options = {}) {
    const opts = { headers: { "Content-Type": "application/json" }, ...options };
    if (opts.body && typeof opts.body !== "string") {
      opts.body = JSON.stringify(opts.body);
    }
    let res;
    try {
      res = await fetch(`/api${path}`, opts);
    } catch (err) {
      throw new APIError("Could not reach the server. Check your connection and try again.", 0);
    }
    if (!res.ok) {
      let detail = `Request failed (${res.status})`;
      try {
        const data = await res.json();
        if (data && data.detail) detail = data.detail;
      } catch (_) {
        /* non-JSON error body */
      }
      throw new APIError(detail, res.status);
    }
    if (res.status === 204) return null;
    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) return res.json();
    return res;
  }

  return {
    get: (path) => request(path, { method: "GET" }),
    post: (path, body) => request(path, { method: "POST", body }),
    del: (path) => request(path, { method: "DELETE" }),

    async downloadExport(sessionId, format) {
      const res = await fetch(`/api/research/${sessionId}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ format }),
      });
      if (!res.ok) {
        let detail = "Export failed.";
        try {
          const data = await res.json();
          if (data.detail) detail = data.detail;
        } catch (_) {}
        throw new APIError(detail, res.status);
      }
      const blob = await res.blob();
      const disposition = res.headers.get("content-disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : `report.${format}`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    },

    streamProgress(sessionId, onEvent) {
      const source = new EventSource(`/api/research/${sessionId}/stream`);
      source.onmessage = (evt) => {
        try {
          onEvent(JSON.parse(evt.data));
        } catch (_) {
          /* ignore malformed frame */
        }
      };
      source.onerror = () => {
        source.close();
      };
      return source;
    },
  };
})();

class APIError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}
