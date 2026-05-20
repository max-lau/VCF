<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const token   = () => localStorage.getItem('paraiq_token')
const authHdr = () => ({ Authorization: 'Bearer ' + token() })
const firmId  = () => { try { return JSON.parse(localStorage.getItem('paraiq_user') || '{}').firm_id || 'default' } catch { return 'default' } }

const cases    = ref([])
const signals  = ref([])   // { case_id, case_number, client_name, severity, title, description, ai }
const deadlines= ref([])
const loading  = ref(true)
const filterSev= ref('')
const filterCase=ref('')

async function fetchAll() {
  loading.value = true
  try {
    // Fetch cases + deadlines in parallel
    const [casesRes, dlRes] = await Promise.all([
      axios.get('/cases/search?q=&firm_id=' + firmId(), { headers: authHdr() }),
      axios.get('/dashboard/deadlines').catch(() => ({ data: { deadlines: [] } })),
    ])
    cases.value    = casesRes.data.cases || []
    deadlines.value= dlRes.data.deadlines || []

    // Fetch intelligence for each case in parallel
    const results = await Promise.allSettled(
      cases.value.map(c =>
        axios.get(`/cases/${c.id}/intelligence`, { headers: authHdr() })
          .then(r => ({ case_id: c.id, case_number: c.case_number, client_name: c.client_name, signals: r.data.signals || [] }))
      )
    )

    const allSignals = []
    results.forEach(r => {
      if (r.status === 'fulfilled') {
        const { case_id, case_number, client_name, signals: sigs } = r.value
        sigs.forEach(s => allSignals.push({ ...s, case_id, case_number, client_name }))
      }
    })
    // Sort: critical first, then warning, then info
    const order = { critical: 0, warning: 1, info: 2 }
    allSignals.sort((a,b) => (order[a.severity]??3) - (order[b.severity]??3))
    signals.value = allSignals
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const filtered = computed(() => signals.value.filter(s => {
  const matchSev  = !filterSev.value  || s.severity === filterSev.value
  const matchCase = !filterCase.value || s.case_id === Number(filterCase.value)
  return matchSev && matchCase
}))

const counts = computed(() => ({
  critical: signals.value.filter(s => s.severity === 'critical').length,
  warning:  signals.value.filter(s => s.severity === 'warning').length,
  info:     signals.value.filter(s => s.severity === 'info').length,
  total:    signals.value.length,
}))

function sevColor(s) {
  return { critical:'#fc8181', warning:'#ecc94b', info:'#4a7cf7' }[s] || '#718096'
}
function sevBg(s) {
  return { critical:'rgba(252,129,129,.1)', warning:'rgba(236,201,75,.1)', info:'rgba(74,124,247,.1)' }[s] || 'rgba(160,174,192,.08)'
}
function sevIcon(s) {
  return { critical:'⚠', warning:'◉', info:'◎' }[s] || '•'
}

onMounted(fetchAll)
</script>

<template>
  <div class="feed">

    <div class="feed__header">
      <div>
        <h1 class="feed__title">Case Intelligence Feed</h1>
        <p class="feed__sub">AI-powered signals across all active matters</p>
      </div>
      <button class="refresh-btn" :disabled="loading" @click="fetchAll">
        {{ loading ? 'Loading…' : '↻ Refresh' }}
      </button>
    </div>

    <!-- Summary cards -->
    <div class="summary-bar">
      <div class="sum-card sum-card--critical" @click="filterSev = filterSev === 'critical' ? '' : 'critical'">
        <div class="sum-card__val">{{ counts.critical }}</div>
        <div class="sum-card__label">Critical</div>
      </div>
      <div class="sum-card sum-card--warning" @click="filterSev = filterSev === 'warning' ? '' : 'warning'">
        <div class="sum-card__val">{{ counts.warning }}</div>
        <div class="sum-card__label">Warnings</div>
      </div>
      <div class="sum-card sum-card--info" @click="filterSev = filterSev === 'info' ? '' : 'info'">
        <div class="sum-card__val">{{ counts.info }}</div>
        <div class="sum-card__label">Info</div>
      </div>
      <div class="sum-card" @click="filterSev = ''">
        <div class="sum-card__val">{{ counts.total }}</div>
        <div class="sum-card__label">All Signals</div>
      </div>
    </div>

    <!-- Deadline radar -->
    <div v-if="deadlines.length" class="deadlines">
      <div class="deadlines__title">⏱ Upcoming Deadlines (30 days)</div>
      <div v-for="d in deadlines" :key="d.case_number + d.date" class="deadline-row">
        <span class="deadline-date mono">{{ d.date }}</span>
        <span class="deadline-case dim">{{ d.case_number }}</span>
        <span class="deadline-desc">{{ d.description || d.event }}</span>
        <span class="deadline-days" :class="d.days_until <= 7 ? 'urgent' : ''">
          {{ d.days_until }}d
        </span>
      </div>
    </div>

    <!-- Filters -->
    <div class="filters">
      <select v-model="filterSev" class="piq-input" style="max-width:160px">
        <option value="">All severities</option>
        <option value="critical">Critical</option>
        <option value="warning">Warning</option>
        <option value="info">Info</option>
      </select>
      <select v-model="filterCase" class="piq-input" style="max-width:220px">
        <option value="">All cases</option>
        <option v-for="c in cases" :key="c.id" :value="c.id">{{ c.case_number }}</option>
      </select>
      <span class="dim" style="font-size:0.85rem;align-self:center">{{ filtered.length }} signal{{ filtered.length !== 1 ? 's' : '' }}</span>
    </div>

    <div v-if="loading" class="state-msg">Analyzing cases…</div>
    <div v-else-if="!filtered.length" class="state-msg dim">No signals match your filter.</div>

    <!-- Signal cards -->
    <div v-else class="signal-list">
      <div v-for="(sig, i) in filtered" :key="i"
           class="signal-card"
           :style="{ borderLeftColor: sevColor(sig.severity), background: sevBg(sig.severity) }">
        <div class="signal-card__top">
          <span class="signal-icon" :style="{ color: sevColor(sig.severity) }">{{ sevIcon(sig.severity) }}</span>
          <span class="signal-sev" :style="{ color: sevColor(sig.severity) }">{{ sig.severity.toUpperCase() }}</span>
          <span class="signal-case dim mono">{{ sig.case_number }}</span>
          <span v-if="sig.ai" class="ai-badge">AI</span>
        </div>
        <div class="signal-title">{{ sig.title }}</div>
        <div class="signal-desc dim">{{ sig.description }}</div>
        <div class="signal-matter dim">{{ sig.client_name }}</div>
      </div>
    </div>

  </div>
</template>

<style scoped>
.feed         { padding: 2rem; max-width: 900px; }
.feed__header { align-items: flex-start; display: flex; justify-content: space-between; margin-bottom: 1.5rem; }
.feed__title  { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.feed__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.refresh-btn  { background: none; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; transition: all .2s; }
.refresh-btn:hover:not(:disabled) { border-color: var(--gold); color: var(--gold); }
.refresh-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* Summary */
.summary-bar { display: flex; gap: 0.75rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.sum-card    { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; cursor: pointer; min-width: 100px; padding: 1rem 1.25rem; transition: border-color .2s; }
.sum-card:hover { border-color: var(--gold); }
.sum-card__val   { font-size: 1.6rem; font-weight: 700; }
.sum-card__label { color: var(--text-muted); font-size: 0.75rem; margin-top: 0.15rem; }
.sum-card--critical .sum-card__val { color: #fc8181; }
.sum-card--warning  .sum-card__val { color: #ecc94b; }
.sum-card--info     .sum-card__val { color: #4a7cf7; }

/* Deadlines */
.deadlines { background: rgba(236,201,75,.06); border: 1px solid rgba(236,201,75,.2); border-radius: 8px; margin-bottom: 1.5rem; padding: 1rem 1.25rem; }
.deadlines__title { color: #ecc94b; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.04em; margin-bottom: 0.75rem; text-transform: uppercase; }
.deadline-row  { align-items: center; display: flex; font-size: 0.85rem; gap: 1rem; padding: 0.35rem 0; }
.deadline-date { flex-shrink: 0; font-size: 0.8rem; }
.deadline-case { flex-shrink: 0; font-size: 0.78rem; }
.deadline-desc { color: var(--text-primary); flex: 1; }
.deadline-days { flex-shrink: 0; font-size: 0.8rem; font-weight: 700; color: var(--text-muted); }
.deadline-days.urgent { color: #fc8181; }

/* Filters */
.filters { display: flex; gap: 0.75rem; margin-bottom: 1.25rem; flex-wrap: wrap; align-items: center; }

/* Signal cards */
.signal-list { display: flex; flex-direction: column; gap: 0.75rem; }
.signal-card {
  border: 1px solid var(--border); border-left: 3px solid; border-radius: 8px;
  padding: 1.1rem 1.25rem; transition: opacity .2s;
}
.signal-card__top { align-items: center; display: flex; gap: 0.6rem; margin-bottom: 0.5rem; }
.signal-icon { font-size: 1rem; flex-shrink: 0; }
.signal-sev  { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; }
.signal-case { font-size: 0.78rem; }
.ai-badge    { background: rgba(201,168,76,.2); border-radius: 4px; color: var(--gold); font-size: 0.65rem; font-weight: 700; letter-spacing: 0.05em; margin-left: auto; padding: 0.1rem 0.35rem; }
.signal-title  { color: var(--text-primary); font-size: 0.95rem; font-weight: 600; margin-bottom: 0.4rem; line-height: 1.3; }
.signal-desc   { color: var(--text-muted); font-size: 0.83rem; line-height: 1.5; margin-bottom: 0.35rem; }
.signal-matter { font-size: 0.75rem; }

.dim    { color: var(--text-muted); }
.mono   { font-family: var(--font-mono); }
.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
</style>
