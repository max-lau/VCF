/* ═══════════════════════════════════════════════════════════
   paraiq-config.js — single source of truth
   Load BEFORE paraiq-auth.js on every page.
   All pages reference ParaIQ.API and ParaIQ.KEY
   instead of hardcoding values.
═══════════════════════════════════════════════════════════ */
window.ParaIQ = window.ParaIQ || {};
window.ParaIQ.API = "https://nlp.para-iq.com";
window.ParaIQ.KEY = "pk-84d8657019538fb44aeee9a6a58b2342c5b819c4cceecb3996570d9e980afa40";
