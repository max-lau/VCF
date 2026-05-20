/* ═══════════════════════════════════════════════════════════
   paraiq-persist.js  —  Sprint 0: User-scoped persistence
   Keys namespaced by user ID — clears on logout via
   ParaIQ.logout() which wipes all paraiq_* keys.
═══════════════════════════════════════════════════════════ */
(function () {

  /* ── Pages to skip ───────────────────────────────────── */
  var SKIP_PAGES = [
    'home','dashboard','insights','index','model',
    'intake','login','admin'
  ];

  /* ── Result containers to watch (all pages combined) ─── */
  var TARGETS = [
    /* Original NLP pages */
    '#results',
    '#pdfResults',
    '#textResults',
    '#redactionPanel',
    '.results-grid',
    '#contraBody',
    '#diarizationBody',
    '#evasionBody',
    '#qaBody',
    /* Discovery module */
    '#queueList',
    '#batesManifest',
    '#dedupList',
    '#privLog',
    '#cocList',
    /* Media & messaging */
    '#audioResult',
    '#videoResult',
    '#emailResult',
    '#smsResult',
    '#chatResult',
    '#transcriptionHistory',
    '#messageHistory',
    /* Intelligence */
    '#privResult',
    '#entResult',
    /* Cases */
    '#casesTbody',
    '#docList',
    '#timelineList',
    '#notesList',
  ];

  var MIN_LEN    = 150;
  var SAVE_WAIT  = 700;
  var BANNER_TTL = 12000;

  /* ── User-scoped storage key ─────────────────────────── */
  var page    = window.location.pathname.split('/').pop().replace('.html','') || 'home';
  var userId  = (window.ParaIQ && window.ParaIQ.getUserId) ? window.ParaIQ.getUserId() : 'guest';
  var STORE_KEY = 'paraiq_' + userId + '_persist_' + page;
  var saveTimer = null;

  /* ── Inject banner styles ────────────────────────────── */
  function injectStyles() {
    if (document.getElementById('piq-persist-styles')) return;
    var s = document.createElement('style');
    s.id  = 'piq-persist-styles';
    s.textContent = [
      '#piq-restore-banner {',
      '  position:fixed; bottom:20px; left:50%; transform:translateX(-50%);',
      '  z-index:9999; background:#1e293b; border:1px solid #334155;',
      '  border-left:3px solid #7c3aed; color:#e2e8f0; font-size:13px;',
      '  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;',
      '  padding:10px 14px; border-radius:10px; display:flex;',
      '  align-items:center; gap:10px; box-shadow:0 4px 24px rgba(0,0,0,0.4);',
      '  animation:piqSlideUp 0.25s ease; white-space:nowrap;',
      '}',
      '@keyframes piqSlideUp {',
      '  from{opacity:0;transform:translateX(-50%) translateY(12px)}',
      '  to{opacity:1;transform:translateX(-50%) translateY(0)}',
      '}',
      '#piq-restore-banner .piq-label{color:#94a3b8}',
      '#piq-restore-banner .piq-ts{color:#a78bfa;font-weight:600}',
      '#piq-restore-btn{background:#7c3aed;color:#fff;border:none;',
      '  padding:5px 12px;border-radius:6px;cursor:pointer;',
      '  font-size:12px;font-weight:600;transition:background 0.12s}',
      '#piq-restore-btn:hover{background:#6d28d9}',
      '#piq-clear-btn{background:transparent;color:#475569;border:none;',
      '  padding:5px 8px;border-radius:6px;cursor:pointer;font-size:12px;',
      '  transition:color 0.12s}',
      '#piq-clear-btn:hover{color:#e2e8f0}',
    ].join('\n');
    document.head.appendChild(s);
  }

  /* ── Get live containers ─────────────────────────────── */
  function getContainers() {
    var found = {};
    TARGETS.forEach(function (sel) {
      var el = document.querySelector(sel);
      if (el) found[sel] = el;
    });
    return found;
  }

  /* ── Save ────────────────────────────────────────────── */
  function saveState() {
    var containers = getContainers();
    var data = {};
    var hasContent = false;
    Object.keys(containers).forEach(function (sel) {
      var html = containers[sel].innerHTML.trim();
      if (html.length > MIN_LEN) { data[sel] = html; hasContent = true; }
    });
    if (!hasContent) return;
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ ts: Date.now(), data: data }));
    } catch (e) {}
  }

  /* ── Load ────────────────────────────────────────────── */
  function loadState() {
    try {
      var raw = localStorage.getItem(STORE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  /* ── Clear ───────────────────────────────────────────── */
  function clearState() {
    try { localStorage.removeItem(STORE_KEY); } catch (e) {}
  }

  /* ── Restore ─────────────────────────────────────────── */
  function restoreState(saved) {
    var containers = getContainers();
    Object.keys(saved.data).forEach(function (sel) {
      if (containers[sel]) {
        containers[sel].innerHTML = saved.data[sel];
        containers[sel].style.display = '';
        /* Re-show result boxes that default to display:none */
        var parent = containers[sel].closest('.result-box');
        if (parent) parent.classList.add('show');
      }
    });
  }

  /* ── Format age ──────────────────────────────────────── */
  function formatAge(ts) {
    var diff = Math.floor((Date.now() - ts) / 1000);
    if (diff < 60)    return diff + 's ago';
    if (diff < 3600)  return Math.floor(diff/60) + 'm ago';
    if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
    return Math.floor(diff/86400) + 'd ago';
  }

  /* ── Banner ──────────────────────────────────────────── */
  function showRestoreBanner(saved) {
    if (document.getElementById('piq-restore-banner')) return;
    injectStyles();
    var banner = document.createElement('div');
    banner.id = 'piq-restore-banner';
    banner.innerHTML =
      '<span class="piq-label">📂 Saved results · </span>' +
      '<span class="piq-ts">' + formatAge(saved.ts) + '</span>' +
      '<button id="piq-restore-btn">↩ Restore</button>' +
      '<button id="piq-clear-btn" title="Discard">✕</button>';
    document.body.appendChild(banner);
    document.getElementById('piq-restore-btn').onclick = function () {
      restoreState(saved); banner.remove();
    };
    document.getElementById('piq-clear-btn').onclick = function () {
      clearState(); banner.remove();
    };
    setTimeout(function () {
      if (banner.parentNode) {
        banner.style.transition = 'opacity 0.4s';
        banner.style.opacity = '0';
        setTimeout(function () { if (banner.parentNode) banner.remove(); }, 400);
      }
    }, BANNER_TTL);
  }

  /* ── MutationObserver ────────────────────────────────── */
  function setupObservers() {
    var containers = getContainers();
    Object.keys(containers).forEach(function (sel) {
      new MutationObserver(function () {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveState, SAVE_WAIT);
      }).observe(containers[sel], { childList:true, subtree:true, characterData:true });
    });
  }

  /* ── Init ────────────────────────────────────────────── */
  function init() {
    if (SKIP_PAGES.indexOf(page) !== -1) return;
    var saved = loadState();
    if (saved && saved.data && Object.keys(saved.data).length > 0) {
      setTimeout(function () { showRestoreBanner(saved); }, 900);
    }
    setupObservers();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
