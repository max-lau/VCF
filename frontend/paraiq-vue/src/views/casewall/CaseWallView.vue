<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const token   = () => localStorage.getItem('paraiq_token')
const authHdr = () => ({ Authorization: 'Bearer ' + token() })
const firmId  = () => { try { return JSON.parse(localStorage.getItem('paraiq_user') || '{}').firm_id || 'default' } catch { return 'default' } }

const cases      = ref([])
const wall       = ref([])
const signals    = ref([])
const selectedId = ref(null)
const loading    = ref(false)

async function fetchCases() {
  const { data } = await axios.get('/cases/search?q=&firm_id=' + firmId(), { headers: authHdr() })
  cases.value = data.cases || []
  if (cases.value.length) selectCase(cases.value[0].id)
}

async function selectCase(id) {
  selectedId.value = id
  loading.value = true
  wall.value = []
  signals.value = []
  try {
    const [wallRes, intRes] = await Promise.all([
      axios.get(`/cases/${id}/wall`,         { headers: authHdr() }),
      axios.get(`/cases/${id}/intelligence`, { headers: authHdr() }),
    ])
    wall.value    = (wallRes.data.items || []).sort((a,b) => new Date(a.date) - new Date(b.date))
    signals.value = intRes.data.signals || []
  } catch {}
  finally { loading.value = false }
}

const selectedCase = () => cases.value.find(c => c.id === selectedId.value)

function typeIcon(t) {
  return { case_opened:'⬡', document:'◻', note:'◎', intelligence:'◈', timeline:'⊣' }[t] || '•'
}
function typeColor(t) {
  return { case_opened:'#c9a84c', document:'#4a7cf7', note:'#718096', intelligence:'#9f7aea', timeline:'#48bb78' }[t] || '#718096'
}
function sevColor(s) {
  return { critical:'#fc8181', warning:'#ecc94b', info:'#4a7cf7' }[s] || '#718096'
}
function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleString('en-US',{month:'short',day:'numeric',year:'numeric',hour:'2-digit',minute:'2-digit'})
}

onMounted(fetchCases)
</script>

<template>
  <div class="wall">
    <div class="wall__header">
      <div>
        <h1 class="wall__title">Case Wall</h1>
        <p class="wall__sub">Unified matter dossier — all activity in one feed</p>
      </div>
    </div>

    <!-- Case selector -->
    <div class="case-tabs">
      <button v-for="c in cases" :key="c.id"
        :class="['case-tab', { 'case-tab--active': selectedId === c.id }]"
        @click="selectCase(c.id)">
        <span class="mono" style="font-size:0.75rem">{{ c.case_number }}</span>
        <span>{{ c.client_name }}</span>
      </button>
    </div>

    <div v-if="loading" class="state-msg">Loading case wall…</div>

    <div v-else class="wall-layout">

      <!-- Feed -->
      <div class="feed-col">
        <div class="feed-count dim">{{ wall.length }} events · {{ selectedCase()?.client_name }}</div>
        <div v-if="!wall.length" class="empty-state">
          <div class="empty-state__icon">⬡</div>
          <div class="empty-state__title">No activity yet</div>
        </div>
        <div v-else class="feed">
          <div v-for="(item, i) in wall" :key="i" class="feed-item">
            <div class="feed-item__spine">
              <div class="feed-item__dot" :style="{ background: typeColor(item.type) }">
                <span>{{ typeIcon(item.type) }}</span>
              </div>
              <div v-if="i < wall.length-1" class="feed-item__line"></div>
            </div>
            <div class="feed-item__body">
              <div class="feed-item__meta">
                <span class="type-badge" :style="{ background: typeColor(item.type)+'22', color: typeColor(item.type) }">
                  {{ item.type.replace('_',' ') }}
                </span>
                <span class="dim" style="font-size:0.75rem">{{ fmtDate(item.date) }}</span>
              </div>
              <div class="feed-item__title">{{ item.title }}</div>
              <div v-if="item.body" class="feed-item__body-text dim">{{ item.body }}</div>
              <!-- Doc meta -->
              <div v-if="item.meta?.risk_score" class="feed-item__tags">
                <span class="tag">Risk: {{ item.meta.risk_score }}</span>
                <span v-if="item.meta.sentiment" class="tag">{{ item.meta.sentiment }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Intelligence sidebar -->
      <div class="intel-col">
        <h3 class="intel-title">AI Signals</h3>
        <div v-if="!signals.length" class="dim" style="font-size:0.85rem">No signals yet.</div>
        <div v-for="(sig, i) in signals" :key="i" class="signal-card"
          :style="{ borderLeftColor: sevColor(sig.severity) }">
          <div class="signal-card__top">
            <span class="sig-sev" :style="{ color: sevColor(sig.severity) }">{{ sig.severity.toUpperCase() }}</span>
            <span v-if="sig.ai" class="ai-badge">AI</span>
          </div>
          <div class="signal-card__title">{{ sig.title }}</div>
          <div class="signal-card__desc dim">{{ sig.description }}</div>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.wall         { padding: 2rem; max-width: 1300px; }
.wall__header { margin-bottom: 1.5rem; }
.wall__title  { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.wall__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }

.case-tabs { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.5rem; }
.case-tab  { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; cursor: pointer; display: flex; flex-direction: column; gap: 0.1rem; padding: 0.6rem 1rem; text-align: left; transition: border-color .2s; font-size: 0.875rem; color: var(--text-muted); }
.case-tab:hover { border-color: var(--gold); color: var(--text-primary); }
.case-tab--active { border-color: var(--gold); color: var(--text-primary); background: rgba(201,168,76,.05); }

.wall-layout { display: grid; gap: 2rem; grid-template-columns: 1fr 340px; }

/* Feed */
.feed-count { font-size: 0.82rem; margin-bottom: 1.25rem; }
.feed       { display: flex; flex-direction: column; }
.feed-item  { display: flex; gap: 1rem; }
.feed-item__spine { align-items: center; display: flex; flex-direction: column; flex-shrink: 0; width: 28px; }
.feed-item__dot   { align-items: center; border-radius: 50%; color: #000; display: flex; font-size: 0.6rem; height: 24px; justify-content: center; width: 24px; flex-shrink: 0; }
.feed-item__line  { background: var(--border); flex: 1; margin: 4px 0; width: 2px; min-height: 20px; }
.feed-item__body  { padding-bottom: 1.5rem; flex: 1; min-width: 0; }
.feed-item__meta  { align-items: center; display: flex; gap: 0.6rem; margin-bottom: 0.35rem; }
.type-badge  { border-radius: 4px; font-size: 0.7rem; font-weight: 600; padding: 0.15rem 0.45rem; text-transform: capitalize; }
.feed-item__title     { color: var(--text-primary); font-size: 0.9rem; font-weight: 600; margin-bottom: 0.25rem; }
.feed-item__body-text { font-size: 0.82rem; line-height: 1.4; }
.feed-item__tags { display: flex; gap: 0.4rem; margin-top: 0.4rem; }
.tag { background: var(--border); border-radius: 4px; color: var(--text-muted); font-size: 0.72rem; padding: 0.1rem 0.4rem; }

/* Intel sidebar */
.intel-col    { }
.intel-title  { color: var(--text-muted); font-size: 0.75rem; font-weight: 600; letter-spacing: 0.05em; margin: 0 0 1rem; text-transform: uppercase; }
.signal-card  { border: 1px solid var(--border); border-left: 3px solid; border-radius: 8px; margin-bottom: 0.75rem; padding: 0.9rem 1rem; }
.signal-card__top   { align-items: center; display: flex; gap: 0.5rem; margin-bottom: 0.35rem; }
.sig-sev      { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.06em; }
.ai-badge     { background: rgba(201,168,76,.2); border-radius: 3px; color: var(--gold); font-size: 0.65rem; font-weight: 700; margin-left: auto; padding: 0.1rem 0.3rem; }
.signal-card__title { color: var(--text-primary); font-size: 0.85rem; font-weight: 600; line-height: 1.3; margin-bottom: 0.3rem; }
.signal-card__desc  { font-size: 0.78rem; line-height: 1.4; }

.empty-state { padding: 3rem 2rem; text-align: center; }
.empty-state__icon  { color: var(--gold); font-size: 2rem; margin-bottom: 0.75rem; opacity: 0.4; }
.empty-state__title { color: var(--text-muted); font-size: 1rem; }
.dim    { color: var(--text-muted); }
.mono   { font-family: var(--font-mono); }
.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
</style>
