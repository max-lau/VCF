/**
 * content.js — ACP-VCF Prep Panel on claims.vcf.gov.
 *
 * Injects a collapsible side panel (shadow DOM, so VCF's CSS can't touch it)
 * showing the selected prep sheet with one-click copy per field.
 *
 * DELIBERATE LIMIT: this script never reads, fills, or submits anything on
 * the VCF page itself. The VCF requires human interaction — the panel is a
 * teleprompter, the paralegal does the typing/pasting.
 */

(() => {
  if (window.__acpVcfPanelInjected) return;
  window.__acpVcfPanelInjected = true;

  const api = (path, method = "GET", body = null) =>
    chrome.runtime.sendMessage({ type: "api", path, method, body });

  // ── Shell + shadow root ────────────────────────────────────────────────────
  const host = document.createElement("div");
  host.id = "acp-vcf-panel-host";
  document.documentElement.appendChild(host);
  const root = host.attachShadow({ mode: "open" });

  root.innerHTML = `
  <style>
    :host { all: initial; }
    * { box-sizing: border-box; font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }

    .tab {
      position: fixed; right: 0; top: 40%; z-index: 2147483646;
      writing-mode: vertical-rl; text-orientation: mixed;
      background: #14141c; color: #d4af37; border: 1px solid #2a2a36; border-right: none;
      border-radius: 8px 0 0 8px; padding: 14px 8px; font-size: 12px;
      letter-spacing: .12em; cursor: pointer; user-select: none;
      box-shadow: -4px 0 18px rgba(0,0,0,.35);
    }

    .panel {
      position: fixed; top: 0; right: 0; height: 100vh; width: 400px; max-width: 92vw;
      z-index: 2147483647; background: #101018; color: #e8e8ee;
      border-left: 1px solid #2a2a36; box-shadow: -10px 0 40px rgba(0,0,0,.5);
      display: flex; flex-direction: column;
      transform: translateX(105%); transition: transform .22s ease;
    }
    .panel.open { transform: translateX(0); }

    .head { padding: 14px 16px; border-bottom: 1px solid #2a2a36;
      display: flex; align-items: center; justify-content: space-between; }
    .logo { color: #d4af37; font-weight: 300; letter-spacing: .1em; font-size: 16px; }
    .close { background: none; border: 1px solid #2a2a36; color: #9a9aa6;
      border-radius: 6px; padding: 2px 10px; cursor: pointer; font-size: 12px; }

    .body { flex: 1; overflow-y: auto; padding: 12px 16px 24px; }
    .msg { font-size: 12px; color: #9a9aa6; padding: 8px 0; }
    .err { color: #e67a7a; }

    select, button.primary {
      width: 100%; background: #14141c; color: #e8e8ee; border: 1px solid #2a2a36;
      border-radius: 8px; padding: 8px 10px; font-size: 13px; margin-bottom: 10px;
    }
    button.primary { color: #d4af37; border-color: #d4af37; cursor: pointer; }
    button.primary:disabled { opacity: .45; cursor: default; }

    .banner { border: 1px solid rgba(230,90,90,.5); color: #e67a7a; font-size: 11px;
      border-radius: 8px; padding: 7px 10px; margin: 8px 0 12px; letter-spacing: .04em; }

    .sec { font-size: 11px; text-transform: uppercase; letter-spacing: .1em;
      color: #d4af37; margin: 16px 0 6px; }
    .progress { font-size: 11px; color: #d4af37; }

    .row { display: grid; grid-template-columns: 1fr auto; gap: 8px;
      padding: 7px 0; border-bottom: 1px solid #1e1e28; align-items: center; }
    .row .lbl { font-size: 10px; color: #7a7a88; text-transform: uppercase;
      letter-spacing: .06em; grid-column: 1 / -1; }
    .row .val { font-size: 13px; background: #14141c; border-radius: 6px;
      padding: 5px 9px; overflow-wrap: anywhere; font-family: ui-monospace, monospace;
      cursor: grab; border: 1px solid transparent; }
    .row .val:active { cursor: grabbing; }
    .row .val.dragging { opacity: .55; border-color: #d4af37; }
    .acp-vcf-drop-target { outline: 2px dashed #d4af37 !important; outline-offset: 2px !important;
      background: rgba(212,175,55,.08) !important; }
    .row .q { font-size: 12px; color: #e8e8ee; grid-column: 1 / -1; }
    .copy { background: none; border: 1px solid #2a2a36; color: #9a9aa6;
      border-radius: 100px; padding: 3px 12px; font-size: 11px; cursor: pointer; white-space: nowrap; }
    .copy.done { border-color: #3ecf8e; color: #3ecf8e; }
    .chip { font-size: 9px; border: 1px solid #2a2a36; color: #7a7a88;
      border-radius: 100px; padding: 1px 7px; margin-left: 6px; }

    .foot { display: flex; gap: 10px; align-items: center; margin-top: 16px; }
    .status { font-size: 11px; color: #9a9aa6; }
  </style>

  <div class="tab" id="tab">ACP-VCF PREP</div>
  <div class="panel" id="panel">
    <div class="head">
      <span class="logo">ACP-VCF</span>
      <span class="progress" id="progress"></span>
      <button class="close" id="close">hide</button>
    </div>
    <div class="body" id="body">
      <div class="msg">Loading prep sheets…</div>
    </div>
  </div>`;

  const $ = (sel) => root.querySelector(sel);
  const panel = $("#panel");
  let prep = null, prepId = null, prepDemo = false;
  const copied = new Set();

  $("#tab").addEventListener("click", () => {
    panel.classList.toggle("open");
    if (panel.classList.contains("open") && !prep) loadList();
  });
  $("#close").addEventListener("click", () => panel.classList.remove("open"));

  // Highlight VCF.gov input fields when a prep value is dragged over them.
  const DROP_SEL = "input[type='text'], input[type='email'], input[type='password'], textarea, select";
  document.addEventListener("dragover", (e) => {
    const t = e.target.closest(DROP_SEL);
    if (!t) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    t.classList.add("acp-vcf-drop-target");
  });
  document.addEventListener("dragleave", (e) => {
    const t = e.target.closest(DROP_SEL);
    if (t) t.classList.remove("acp-vcf-drop-target");
  });
  document.addEventListener("drop", (e) => {
    const t = e.target.closest(DROP_SEL);
    if (t) t.classList.remove("acp-vcf-drop-target");
  });

  function setBody(html) { $("#body").innerHTML = html; }
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // ── Prep list ──────────────────────────────────────────────────────────────
  async function loadList() {
    setBody(`<div class="msg">Loading prep sheets…</div>`);
    const r = await api("/vcf/prep?limit=25");
    if (!r.ok) return setBody(`<div class="msg err">${esc(r.error)}</div>`);
    const preps = (r.data && r.data.preps) || [];
    if (!preps.length)
      return setBody(`<div class="msg">No prep sheets yet. Generate one in ACP-VCF → VCF Account first.</div>`);
    setBody(`
      <div class="msg">Select a client prep sheet:</div>
      <select id="sel">
        ${preps.map((p) => `<option value="${p.id}">
          #${p.id} · ${esc(p.client_name || "unnamed")} · ${esc(p.status)}${p.demo_mode ? " · DEMO" : ""}
        </option>`).join("")}
      </select>
      <button class="primary" id="load">Load prep sheet</button>`);
    $("#load").addEventListener("click", () => loadPrep($("#sel").value));
  }

  // ── Prep sheet ─────────────────────────────────────────────────────────────
  async function loadPrep(id) {
    setBody(`<div class="msg">Loading prep #${esc(id)}…</div>`);
    const r = await api(`/vcf/prep/${id}`);
    if (!r.ok) return setBody(`<div class="msg err">${esc(r.error)}</div>`);
    prep = r.data.prep; prepId = r.data.prep_id; prepDemo = !!r.data.demo_mode;
    copied.clear();
    render(r.data.status);
  }

  function fieldRow(key, label, value, hint) {
    return `
      <div class="row">
        <span class="lbl">${esc(label)}${hint ? ` <span class="chip">${esc(hint)}</span>` : ""}</span>
        <span class="val" draggable="true" data-val="${esc(value || "")}" ${value ? "" : "disabled"}>${esc(value || "—")}</span>
        <button class="copy" data-key="${esc(key)}" data-val="${esc(value || "")}"
          ${value ? "" : "disabled"}>copy</button>
      </div>`;
  }

  function render(status) {
    const a = prep.account_information || {};
    const rows = [
      ["user_name", "User Name", a.user_name],
      ["email", "Email", a.email],
      ["confirm_email", "Confirm email", a.confirm_email],
      ["first_name", "First Name", a.first_name],
      ["last_name", "Last Name", a.last_name],
      ["password", "Password", a.password, "16+ / Aa1!"],
      ["confirm_password", "Confirm password", a.confirm_password],
    ];
    const sqs = prep.security_questions || [];
    window.__acpVcfTotal = rows.length + sqs.length;

    setBody(`
      ${prepDemo ? `<div class="banner">DEMO DATA — synthesized security answers. Not for a real client account.</div>` : ""}
      <div class="sec">Account Information</div>
      ${rows.map((r) => fieldRow(...r)).join("")}
      <div class="sec">Security Questions</div>
      ${sqs.map((q, i) => `
        <div class="row">
          <span class="q">Q${i + 1}. ${esc(q.question || "— select with client —")}
            ${q.synthesized ? `<span class="chip">synthesized</span>` : ""}</span>
          <span class="val" draggable="true" data-val="${esc(q.answer || "")}" ${q.answer ? "" : "disabled"}>${esc(q.answer || "—")}</span>
          <button class="copy" data-key="sq${i}" data-val="${esc(q.answer || "")}"
            ${q.answer ? "" : "disabled"}>copy</button>
        </div>`).join("")}
      <div class="foot">
        <button class="primary" id="done" style="width:auto">✓ Account created</button>
        <span class="status" id="st">status: ${esc(status)}</span>
      </div>
      <div class="msg" style="margin-top:8px">
        ← back to <a href="#" id="back" style="color:#d4af37">prep list</a>
      </div>`);
    updateProgress();

    root.querySelectorAll(".copy").forEach((btn) =>
      btn.addEventListener("click", async () => {
        const val = btn.getAttribute("data-val");
        try { await navigator.clipboard.writeText(val); }
        catch (_) {
          const ta = document.createElement("textarea");
          ta.value = val; document.body.appendChild(ta);
          ta.select(); document.execCommand("copy"); ta.remove();
        }
        copied.add(btn.getAttribute("data-key"));
        btn.classList.add("done"); btn.textContent = "✓";
        updateProgress();
      }));

    // Drag-and-drop: drag a value from the panel and drop it onto a VCF field.
    root.querySelectorAll(".val[draggable='true']").forEach((el) => {
      el.addEventListener("dragstart", (e) => {
        const val = el.getAttribute("data-val") || el.textContent;
        e.dataTransfer.setData("text/plain", val);
        e.dataTransfer.effectAllowed = "copy";
        el.classList.add("dragging");
      });
      el.addEventListener("dragend", () => el.classList.remove("dragging"));
    });

    $("#back").addEventListener("click", (e) => { e.preventDefault(); prep = null; loadList(); });
    $("#done").addEventListener("click", async () => {
      $("#done").disabled = true;
      const r = await api(`/vcf/prep/${prepId}/status`, "PATCH", {
        status: "account_created",
        vcf_username: (prep.account_information || {}).user_name || null,
      });
      $("#st").textContent = r.ok ? "status: account_created ✓" : `error: ${r.error}`;
      $("#done").disabled = false;
    });
  }

  function updateProgress() {
    $("#progress").textContent =
      prep ? `${copied.size} / ${window.__acpVcfTotal || 0} copied` : "";
  }
})();
