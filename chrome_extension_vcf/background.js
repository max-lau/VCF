/**
 * background.js — API proxy for the ACP-VCF Prep Panel.
 *
 * Content scripts run inside claims.vcf.gov's origin, so a direct fetch to
 * localhost:8000 would be blocked by CORS. The service worker fetches with
 * the extension's own host_permissions instead, so no backend CORS changes
 * are needed.
 *
 * Message shape from content/popup:
 *   { type: "api", path: "/vcf/prep", method: "GET", body?: {...} }
 * Reply:
 *   { ok: true, status, data } | { ok: false, status?, error }
 */

async function getSettings() {
  const d = await chrome.storage.local.get(["baseUrl", "token"]);
  return {
    baseUrl: (d.baseUrl || "http://localhost:5003").replace(/\/+$/, ""),
    token: d.token || "",
  };
}

async function apiCall({ path, method = "GET", body = null }) {
  const { baseUrl, token } = await getSettings();
  if (!token && path !== "/health") {
    return { ok: false, error: "No token set — open the extension popup and paste your ACP-VCF JWT." };
  }
  try {
    const res = await fetch(baseUrl + path, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch (_) { /* non-JSON body */ }
    if (!res.ok) {
      const detail = (data && (data.detail || data.error)) || res.statusText;
      const hint = res.status === 401
        ? " (token missing/expired — update it in the extension popup)"
        : "";
      return { ok: false, status: res.status, error: `${detail}${hint}` };
    }
    return { ok: true, status: res.status, data };
  } catch (e) {
    return { ok: false, error: `Cannot reach ${baseUrl} — is the backend running? (${e.message})` };
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "api") {
    apiCall(msg).then(sendResponse);
    return true; // keep the message channel open for the async reply
  }
});
