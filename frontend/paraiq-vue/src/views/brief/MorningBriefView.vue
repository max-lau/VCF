<template>
  <div class="piq-page">
    <div class="piq-page-header">
      <h2 class="piq-page-title">☀️ Morning Brief</h2>
      <p class="piq-page-subtitle">{{ briefDate }} · synthesised from deadlines, approvals, risk signals</p>
    </div>
    <div v-if="loading" class="piq-loading">Generating brief…</div>
    <div v-else-if="error" class="piq-error">{{ error }}</div>
    <div v-else class="brief-layout">
      <div class="brief-card brief-card--summary">
        <div class="brief-card__header">
          <span class="brief-card__title">📋 Summary</span>
          <button class="piq-btn piq-btn--ghost piq-btn--sm" @click="regenerate" :disabled="regenerating">
            {{ regenerating ? "Regenerating…" : "↻ Regenerate" }}
          </button>
        </div>
        <pre class="brief-summary-text">{{ summaryText }}</pre>
      </div>
      <div class="brief-card">
        <div class="brief-card__header">
          <span class="brief-card__title">📅 Deadlines (72h)</span>
          <span class="brief-badge" :class="deadlines.length ? 'brief-badge--warn' : 'brief-badge--ok'">{{ deadlines.length }}</span>
        </div>
        <div v-if="!deadlines.length" class="brief-empty">No deadlines in the next 72 hours.</div>
        <div v-else class="brief-list">
          <div v-for="d in deadlines" :key="d.id" class="brief-item">
            <div class="brief-item__left">
              <span class="brief-urgency" :class="urgencyClass(d.days_away)">{{ d.urgency }}</span>
              <span class="brief-item__title">{{ d.title }}</span>
              <span v-if="d.is_court_date" class="court-chip">⚖ Court</span>
            </div>
            <span class="brief-item__meta">{{ d.client_name || d.case_number }}</span>
          </div>
        </div>
      </div>
      <div class="brief-card">
        <div class="brief-card__header">
          <span class="brief-card__title">✅ Pending Approvals</span>
          <span class="brief-badge" :class="approvals.length ? 'brief-badge--warn' : 'brief-badge--ok'">{{ approvals.length }}</span>
        </div>
        <div v-if="!approvals.length" class="brief-empty">No items awaiting approval.</div>
        <div v-else class="brief-list">
          <div v-for="q in approvals" :key="q.id" class="brief-item">
            <div class="brief-item__left">
              <span class="brief-type-chip">{{ q.item_type }}</span>
              <span class="brief-item__title">{{ q.title }}</span>
            </div>
            <RouterLink to="/approvals" class="brief-item__action">Review →</RouterLink>
          </div>
        </div>
      </div>
      <div class="brief-card" v-if="riskSnapshot">
        <div class="brief-card__header">
          <span class="brief-card__title">🔥 System Risk</span>
          <span class="brief-badge" :class="`brief-badge--${riskSnapshot.risk_level}`">{{ riskSnapshot.risk_level?.toUpperCase() }}</span>
        </div>
        <p class="brief-risk-summary">{{ riskSnapshot.summary }}</p>
        <p v-if="riskSnapshot.prediction" class="brief-risk-prediction">⚡ {{ riskSnapshot.prediction }}</p>
      </div>
      <div class="brief-card" v-if="matterChanges.length">
        <div class="brief-card__header">
          <span class="brief-card__title">📂 Matters Updated (24h)</span>
          <span class="brief-badge brief-badge--ok">{{ matterChanges.length }}</span>
        </div>
        <div class="brief-list">
          <div v-for="c in matterChanges" :key="c.id" class="brief-item">
            <span class="brief-item__title">{{ c.client_name }}</span>
            <span class="brief-item__meta">{{ c.case_number }} · {{ c.status }}</span>
          </div>
        </div>
      </div>
      <div class="brief-card" v-if="urgentNotifs.length">
        <div class="brief-card__header">
          <span class="brief-card__title">🔔 Urgent Notifications</span>
          <span class="brief-badge brief-badge--warn">{{ urgentNotifs.length }}</span>
        </div>
        <div class="brief-list">
          <div v-for="n in urgentNotifs" :key="n.id" class="brief-item">
            <span class="brief-item__title">{{ n.title }}</span>
            <span class="brief-item__meta">{{ n.body }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from "vue"
import { useAuthStore } from "@/stores/auth"

const auth         = useAuthStore()
const loading      = ref(true)
const regenerating = ref(false)
const error        = ref(null)
const brief        = ref(null)
const summaryText  = ref("")

const deadlines     = computed(() => brief.value?.deadlines || [])
const approvals     = computed(() => brief.value?.approval_queue || [])
const riskSnapshot  = computed(() => brief.value?.risk_snapshot || null)
const matterChanges = computed(() => brief.value?.matter_changes || [])
const urgentNotifs  = computed(() => brief.value?.urgent_notifications || [])
const briefDate     = computed(() => {
  if (!brief.value?.generated_at) return ""
  return new Date(brief.value.generated_at).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })
})

async function fetchBrief() {
  try {
    const res = await fetch("/brief/today", { headers: { Authorization: `Bearer ${auth.token}` } })
    if (!res.ok) throw new Error(res.status)
    const data = await res.json()
    brief.value      = data.brief
    summaryText.value = data.summary_text
  } catch (e) {
    error.value = `Failed to load brief: ${e.message}`
  } finally {
    loading.value = false
  }
}

async function regenerate() {
  regenerating.value = true
  try {
    const res = await fetch("/brief/generate", { method: "POST", headers: { Authorization: `Bearer ${auth.token}` } })
    if (!res.ok) throw new Error(res.status)
    const data = await res.json()
    summaryText.value = data.summary_text
    await fetchBrief()
  } catch (e) {
    error.value = `Regenerate failed: ${e.message}`
  } finally {
    regenerating.value = false
  }
}

function urgencyClass(daysAway) {
  if (daysAway === 0) return "urgency--today"
  if (daysAway === 1) return "urgency--tomorrow"
  return "urgency--soon"
}

onMounted(fetchBrief)
</script>

<style scoped>
.brief-layout         { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.brief-card           { background: var(--surface-card); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.brief-card--summary  { grid-column: 1 / -1; }
.brief-card__header   { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.brief-card__title    { font-size: 13px; font-weight: 600; color: var(--text-primary); flex: 1; }
.brief-summary-text   { font-size: 13px; line-height: 1.7; color: var(--text-secondary); white-space: pre-wrap; margin: 0; }
.brief-list           { display: flex; flex-direction: column; gap: 8px; }
.brief-item           { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 8px; border-radius: 6px; font-size: 13px; }
.brief-item:hover     { background: var(--surface-hover, rgba(255,255,255,.04)); }
.brief-item__left     { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
.brief-item__title    { color: var(--text-primary); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.brief-item__meta     { color: var(--text-tertiary); font-size: 12px; white-space: nowrap; }
.brief-item__action   { color: var(--accent); font-size: 12px; text-decoration: none; }
.brief-empty          { color: var(--text-tertiary); font-size: 13px; padding: 8px 0; }
.brief-risk-summary   { font-size: 13px; color: var(--text-secondary); margin: 0 0 6px; }
.brief-risk-prediction { font-size: 12px; color: var(--text-tertiary); margin: 0; }
.brief-badge          { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.brief-badge--ok      { background: rgba(16,185,129,.15); color: #34d399; }
.brief-badge--warn    { background: rgba(245,158,11,.15); color: #fbbf24; }
.brief-badge--warning { background: rgba(245,158,11,.15); color: #fbbf24; }
.brief-badge--critical { background: rgba(239,68,68,.15); color: #f87171; }
.brief-badge--low     { background: rgba(16,185,129,.15); color: #34d399; }
.brief-urgency        { font-size: 11px; font-weight: 600; text-transform: uppercase; padding: 1px 6px; border-radius: 8px; white-space: nowrap; }
.urgency--today       { background: rgba(239,68,68,.15); color: #f87171; }
.urgency--tomorrow    { background: rgba(245,158,11,.15); color: #fbbf24; }
.urgency--soon        { background: rgba(99,102,241,.15); color: #818cf8; }
.brief-type-chip      { font-size: 11px; color: var(--text-tertiary); background: var(--surface-hover); padding: 1px 6px; border-radius: 6px; white-space: nowrap; }
.court-chip           { font-size: 11px; color: #f87171; background: rgba(239,68,68,.1); padding: 1px 6px; border-radius: 6px; }
@media (max-width: 768px) { .brief-layout { grid-template-columns: 1fr; } }
</style>
