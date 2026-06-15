<template>
  <div class="piq-page">
    <div class="piq-page-header">
      <h2 class="piq-page-title">⏱ Time Capture</h2>
      <p class="piq-page-subtitle">Review and certify your tracked sessions into billable entries</p>
    </div>

    <!-- Summary cards -->
    <div class="tc-summary">
      <div class="tc-stat">
        <div class="tc-stat__value">{{ summary.pending_sessions }}</div>
        <div class="tc-stat__label">Pending Sessions</div>
        <div class="tc-stat__sub">{{ fmtMins(summary.pending_mins) }}</div>
      </div>
      <div class="tc-stat">
        <div class="tc-stat__value">${{ summary.certified_total_amount?.toFixed(2) }}</div>
        <div class="tc-stat__label">Certified This Period</div>
        <div class="tc-stat__sub">{{ fmtMins(summary.certified_total_mins) }}</div>
      </div>
      <div class="tc-stat">
        <div class="tc-stat__value">${{ summary.hourly_rate?.toFixed(2) || "—" }}/hr</div>
        <div class="tc-stat__label">Your Billing Rate</div>
        <div class="tc-stat__sub">{{ summary.hourly_rate ? "Active" : "Not set — contact admin" }}</div>
      </div>
    </div>

    <!-- Pending sessions -->
    <div class="tc-section-header">
      <span>Pending Certification</span>
      <div class="tc-header-actions">
        <button v-if="selected.length" class="piq-btn piq-btn--success piq-btn--sm" @click="certifySelected">
          ✓ Certify {{ selected.length }} selected
        </button>
        <button v-if="sessions.length" class="piq-btn piq-btn--ghost piq-btn--sm" @click="selectAll">
          {{ selected.length === sessions.length ? "Deselect all" : "Select all" }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="piq-loading">Loading sessions…</div>
    <div v-else-if="!sessions.length" class="piq-empty-state">
      <span style="font-size:32px">⏱</span>
      <p>No pending sessions. Time is captured automatically while you work on matters.</p>
    </div>

    <div v-else class="tc-list">
      <div v-for="s in sessions" :key="s.id" class="tc-card"
        :class="{ 'tc-card--selected': selected.includes(s.id) }">
        <div class="tc-card__check">
          <input type="checkbox" :value="s.id" v-model="selected" class="tc-checkbox" />
        </div>
        <div class="tc-card__body">
          <div class="tc-card__top">
            <div class="tc-card__matter">
              <span class="tc-case-num">{{ s.case_number }}</span>
              <span class="tc-client">{{ s.client_name }}</span>
            </div>
            <div class="tc-card__meta">
              <span class="tc-duration">{{ fmtMins(s.duration_mins) }}</span>
              <span v-if="s.billable_amount" class="tc-amount">${{ parseFloat(s.billable_amount).toFixed(2) }}</span>
              <span v-else class="tc-amount tc-amount--none">No rate set</span>
            </div>
          </div>
          <div class="tc-card__time">
            {{ fmtDatetime(s.started_at) }} → {{ fmtTime(s.ended_at) }}
          </div>
          <div class="tc-card__controls">
            <select v-model="s.activity_type" class="piq-input tc-select"
              @change="updateSession(s.id, { activity_type: s.activity_type })">
              <option v-for="t in ACTIVITY_TYPES" :key="t" :value="t">{{ t }}</option>
            </select>
            <input v-if="s.activity_type === 'other'" v-model="s.remarks"
              class="piq-input tc-remarks" placeholder="Describe the activity…"
              @blur="updateSession(s.id, { remarks: s.remarks })" />
            <input type="number" v-model.number="s.duration_mins" min="1"
              class="piq-input tc-dur-input"
              @change="updateSession(s.id, { duration_mins: s.duration_mins })" />
            <span class="tc-mins-label">mins</span>
            <button class="tc-discard-btn" @click="discardSession(s.id)" title="Discard">✕</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Certified entries ledger -->
    <div class="tc-section-header" style="margin-top:32px">
      <span>Certified Time Ledger</span>
    </div>
    <div v-if="!entries.length" class="piq-empty-state" style="padding:16px 0">
      <p style="color:var(--text-tertiary);font-size:13px">No certified entries yet.</p>
    </div>
    <div v-else class="table-wrap">
      <table class="piq-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Matter</th>
            <th>Activity</th>
            <th>Duration</th>
            <th>Rate</th>
            <th>Amount</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in entries" :key="e.id">
            <td class="dim nowrap">{{ e.date?.slice(0,10) }}</td>
            <td><span class="tc-case-num">{{ e.case_number }}</span> {{ e.client_name }}</td>
            <td><span class="type-pill">{{ e.activity_type }}</span></td>
            <td class="dim">{{ fmtMins(e.duration_mins) }}</td>
            <td class="dim">${{ e.hourly_rate?.toFixed(2) }}/hr</td>
            <td class="tc-amount">${{ e.billable_amount?.toFixed(2) }}</td>
            <td class="dim">{{ e.description || e.remarks || "—" }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"

const token    = () => localStorage.getItem("paraiq_token")
const authHdr  = () => ({ Authorization: "Bearer " + token() })

const loading  = ref(true)
const sessions = ref([])
const entries  = ref([])
const summary  = ref({})
const selected = ref([])

const ACTIVITY_TYPES = ["viewing","drafting","reviewing","research","correspondence","other"]

async function fetchAll() {
  loading.value = true
  try {
    const [s, e, sum] = await Promise.all([
      fetch("/time/sessions/pending", { headers: authHdr() }).then(r => r.json()),
      fetch("/time/entries",          { headers: authHdr() }).then(r => r.json()),
      fetch("/time/summary",          { headers: authHdr() }).then(r => r.json()),
    ])
    sessions.value = s.sessions || []
    entries.value  = e.entries  || []
    summary.value  = sum
  } catch (e) {
    console.error("Time fetch failed:", e)
  } finally {
    loading.value = false
  }
}

async function updateSession(id, patch) {
  await fetch(`/time/sessions/${id}`, {
    method: "PATCH",
    headers: { ...authHdr(), "Content-Type": "application/json" },
    body: JSON.stringify(patch)
  })
  await fetchAll()
}

async function discardSession(id) {
  if (!confirm("Discard this session? It will not be billed.")) return
  await fetch(`/time/sessions/${id}/discard`, { method: "POST", headers: authHdr() })
  sessions.value = sessions.value.filter(s => s.id !== id)
  selected.value = selected.value.filter(s => s !== id)
}

async function certifySelected() {
  if (!selected.value.length) return
  if (!confirm(`Certify ${selected.value.length} session(s) as billable time entries?`)) return
  await fetch("/time/certify", {
    method: "POST",
    headers: { ...authHdr(), "Content-Type": "application/json" },
    body: JSON.stringify({ session_ids: selected.value })
  })
  selected.value = []
  await fetchAll()
}

function selectAll() {
  if (selected.value.length === sessions.value.length) {
    selected.value = []
  } else {
    selected.value = sessions.value.map(s => s.id)
  }
}

function fmtMins(mins) {
  if (!mins) return "0m"
  const h = Math.floor(mins / 60)
  const m = Math.round(mins % 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function fmtDatetime(iso) {
  if (!iso) return ""
  return new Date(iso).toLocaleString("en-US", { month:"short", day:"numeric", hour:"2-digit", minute:"2-digit" })
}

function fmtTime(iso) {
  if (!iso) return ""
  return new Date(iso).toLocaleTimeString("en-US", { hour:"2-digit", minute:"2-digit" })
}

onMounted(fetchAll)
</script>

<style scoped>
.tc-summary       { display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px; }
.tc-stat          { background:var(--surface-card);border:1px solid var(--border);border-radius:10px;padding:16px; }
.tc-stat__value   { font-size:24px;font-weight:700;color:var(--text-primary); }
.tc-stat__label   { font-size:12px;color:var(--text-tertiary);margin-top:4px; }
.tc-stat__sub     { font-size:11px;color:var(--text-tertiary);margin-top:2px; }
.tc-section-header { display:flex;align-items:center;justify-content:space-between;font-size:13px;font-weight:600;color:var(--text-secondary);margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--border); }
.tc-header-actions { display:flex;gap:8px; }
.tc-list          { display:flex;flex-direction:column;gap:8px; }
.tc-card          { display:flex;gap:12px;background:var(--surface-card);border:1px solid var(--border);border-radius:10px;padding:14px;transition:border-color .15s; }
.tc-card--selected { border-color:var(--accent); }
.tc-card__check   { flex-shrink:0;padding-top:2px; }
.tc-checkbox      { width:16px;height:16px;accent-color:var(--accent);cursor:pointer; }
.tc-card__body    { flex:1;min-width:0; }
.tc-card__top     { display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:4px; }
.tc-card__matter  { display:flex;align-items:center;gap:8px; }
.tc-case-num      { font-size:11px;color:var(--text-tertiary);background:var(--surface-hover);padding:1px 6px;border-radius:4px; }
.tc-client        { font-size:13px;font-weight:600;color:var(--text-primary); }
.tc-card__meta    { display:flex;align-items:center;gap:10px;flex-shrink:0; }
.tc-duration      { font-size:13px;font-weight:600;color:var(--text-primary); }
.tc-amount        { font-size:13px;font-weight:700;color:#34d399; }
.tc-amount--none  { color:var(--text-tertiary);font-weight:400; }
.tc-card__time    { font-size:12px;color:var(--text-tertiary);margin-bottom:8px; }
.tc-card__controls { display:flex;align-items:center;gap:8px;flex-wrap:wrap; }
.tc-select        { width:140px;padding:4px 8px;font-size:12px; }
.tc-remarks       { flex:1;min-width:160px;padding:4px 8px;font-size:12px; }
.tc-dur-input     { width:70px;padding:4px 8px;font-size:12px;text-align:right; }
.tc-mins-label    { font-size:12px;color:var(--text-tertiary); }
.tc-discard-btn   { background:none;border:none;color:var(--text-tertiary);cursor:pointer;font-size:14px;padding:4px;border-radius:4px; }
.tc-discard-btn:hover { color:#f87171;background:rgba(239,68,68,.1); }
@media (max-width:768px) { .tc-summary { grid-template-columns:1fr; } }
</style>
