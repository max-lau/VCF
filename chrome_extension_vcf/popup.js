const $ = (id) => document.getElementById(id);

// Load saved settings
chrome.storage.local.get(["baseUrl", "token"]).then((d) => {
  $("baseUrl").value = d.baseUrl || "http://localhost:5003";
  $("token").value = d.token || "";
});

$("save").addEventListener("click", async () => {
  const baseUrl = $("baseUrl").value.trim() || "http://localhost:5003";
  const token = $("token").value.trim();
  await chrome.storage.local.set({ baseUrl, token });

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
});
