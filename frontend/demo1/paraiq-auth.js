/* ═══════════════════════════════════════════════════════════
   paraiq-auth.js  —  Sprint 0: Auth foundation
   Exposes window.ParaIQ auth utilities globally.
   Load first on every page (before all other scripts).
═══════════════════════════════════════════════════════════ */
(function () {

  window.ParaIQ = window.ParaIQ || {};

  var TOKEN_KEY = 'paraiq_token';
  var USER_KEY  = 'paraiq_user';

  /* ── Token utilities ─────────────────────────────────── */

  ParaIQ.getToken = function () {
    return localStorage.getItem(TOKEN_KEY) || '';
  };

  ParaIQ.getUser = function () {
    var token = ParaIQ.getToken();
    if (!token) return null;
    try {
      var b64 = token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/');
      return JSON.parse(atob(b64));
    } catch (e) { return null; }
  };

  ParaIQ.getUserId = function () {
    var u = ParaIQ.getUser();
    return u ? (u.user_id || u.sub || u.id || 'guest') : 'guest';
  };

  ParaIQ.getRole = function () {
    var u = ParaIQ.getUser();
    return u ? (u.role || 'user') : null;
  };

  /* ── Auth headers for fetch calls ────────────────────── */

  ParaIQ.headers = function (isFormData) {
    var h = { 'X-API-Key': ParaIQ.KEY };
    var tok = ParaIQ.getToken();
    if (tok) h['Authorization'] = 'Bearer ' + tok;
    if (!isFormData) h['Content-Type'] = 'application/json';
    return h;
  };

  /* ── Role gating ─────────────────────────────────────── */

  ParaIQ.requireRole = function (minRole) {
    var hierarchy = { 'user': 1, 'manager': 2, 'admin': 3 };
    var current   = hierarchy[ParaIQ.getRole()] || 0;
    var required  = hierarchy[minRole] || 1;
    if (current < required) {
      window.location.replace('home.html');
      return false;
    }
    return true;
  };

  /* ── Logout — clears ALL paraiq_* keys ───────────────── */

  ParaIQ.logout = function () {
    Object.keys(localStorage)
      .filter(function (k) { return k.indexOf('paraiq_') === 0; })
      .forEach(function (k) { localStorage.removeItem(k); });
    window.location.replace('login.html');
  };

  /* ── Save token after login ──────────────────────────── */

  ParaIQ.saveToken = function (token) {
    localStorage.setItem(TOKEN_KEY, token);
  };

  /* ── Page guard — runs immediately ──────────────────── */

  var page = window.location.pathname.split('/').pop() || 'home.html';
  var PUBLIC = ['login.html', 'index.html'];

  if (PUBLIC.indexOf(page) !== -1) return;

  var token = ParaIQ.getToken();
  if (!token) {
    window.location.replace('login.html');
    return;
  }

  var payload = ParaIQ.getUser();
  if (!payload) {
    /* Malformed token — clear and redirect */
    ParaIQ.logout();
    return;
  }

  if (payload.exp && payload.exp * 1000 <= Date.now()) {
    /* Expired — clear and redirect */
    ParaIQ.logout();
    return;
  }

  /* ── Inject logout button into sidebar when ready ────── */
  document.addEventListener('DOMContentLoaded', function () {
    /* Show username in sidebar if element exists */
    var nameEl = document.getElementById('sb-username');
    if (nameEl && payload.username) nameEl.textContent = payload.username;

    /* Wire any logout buttons on the page */
    document.querySelectorAll('[data-action="logout"]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        ParaIQ.logout();
      });
    });
  });

})();
