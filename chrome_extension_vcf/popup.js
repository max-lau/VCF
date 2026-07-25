const $ = (id) => document.getElementById(id);

// Load saved settings
chrome.storage.local.get(["baseUrl", "token"]).then((d) => {
  $("baseUrl").value = d.baseUrl || "http://localhost:5003";
  $("token").value = d.token || "";
});

async function testConnection() {
  const out = $("out");
  out.textContent = "Testing…";
  out.className = "";

  // 1. Reachability (auth-exempt endpoint)
  const health = await chrome.runtime.sendMessage({ type: "api", path: "/health" });
  if (!health.ok) {
    out.textContent = `✗ ${health.error}`;
    out.className = "err";
    return;
  }

  // 2. Auth (JWT-gated endpoint)
  const auth = await chrome.runtime.sendMessage({ type: "api", path: "/vcf/prep?limit=1" });
  if (!auth.ok) {
    out.textContent = `✓ backend reachable · ✗ auth failed: ${auth.error}`;
    out.className = "err";
    return;
  }

  const n = (auth.data && auth.data.count) ?? 0;
  out.textContent = `✓ connected & authenticated · ${n} prep sheet(s) visible`;
  out.className = "ok";
}

$("save").addEventListener("click", async () => {
  const baseUrl = $("baseUrl").value.trim() || "http://localhost:5003";
  const token = $("token").value.trim();
  await chrome.storage.local.set({ baseUrl, token });
  await testConnection();
});

$("grab").addEventListener("click", async () => {
  const out = $("out");
  out.textContent = "Looking for ACP-VCF tab…";
  out.className = "";

  try {
    const tabs = await chrome.tabs.query({ url: ["http://localhost:5174/*", "http://127.0.0.1:5174/*"] });
    const tab = tabs.find((t) => t.active) || tabs[0];
    if (!tab) {
      out.textContent = "✗ No ACP-VCF tab found. Open http://localhost:5174 and log in.";
      out.className = "err";
      return;
    }

    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => localStorage.getItem("paraiq_token") || localStorage.getItem("token") || "",
    });
    const token = (results && results[0] && results[0].result) || "";

    if (!token) {
      out.textContent = "✗ Token not found. Make sure you are logged in to ACP-VCF.";
      out.className = "err";
      return;
    }

    $("token").value = token;
    out.textContent = "✓ Token copied from ACP-VCF tab. Click Save & test connection.";
    out.className = "ok";
  } catch (e) {
    out.textContent = `✗ Could not read token: ${e.message}`;
    out.className = "err";
  }
});
