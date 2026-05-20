<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const token   = () => localStorage.getItem('paraiq_token')
const authHdr = () => ({ Authorization: 'Bearer ' + token() })
const firmId  = () => { try { return JSON.parse(localStorage.getItem('paraiq_user') || '{}').firm_id || 'default' } catch { return 'default' } }

const cases      = ref([])
const events     = ref([])
const loading    = ref(false)
const selectedId = ref(null)
const selectedCase = computed(() => cases.value.find(c => c.id === selectedId.value))

async function fetchCases() {
  const { data } = await axios.get('/cases/search?q=&firm_id=' + firmId(), { headers: authHdr() })
  cases.value = data.cases || []
  if (cases.value.length) selectCase(cases.value[0].id)
}

async function selectCase(id) {
  selectedId.value = id
  loading.value = true
  events.value = []
  try {
    const { data } = await axios.get(`/cases/${id}/timeline`, { headers: authHdr() })
    // Normalise — timeline may have items with different shapes
    const raw = data.timeline || []
    events.value = raw
      .filter(e => e.date || e.date_normalized)
      .sort((a,b) => (a.date_normalized||a.date) > (b.date_normalized||b.date) ? 1 : -1)
  } catch { events.value = [] }
  finally { loading.value = false }
}

function sigColor(s) {
  return { high:'#fc8181', medium:'#ecc94b', low:'#48bb78' }[s] || '#718096'
}
function sigLabel(s) {
  return { high:'HIGH', medium:'MED', low:'LOW' }[s] || '—'
}
function fmtDate(e) { return e.date || e.date_normalized || '—' }

onMounted(fetchCases)
</script>

<template>
  <div class="tl">
    <div class="tl__header">
      <div>
        <h1 class="tl__title">Timeline</h1>
        <p class="tl__sub">Chronological case event extraction</p>
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

    <div v-if="loading" class="state-msg">Extracting timeline…</div>

    <div v-else-if="!events.length" class="empty-state">
      <div class="empty-state__icon">⊣</div>
      <div class="empty-state__title">No timeline events extracted yet</div>
      <div class="empty-state__sub">Upload and process documents to extract dates and events automatically.</div>
    </div>

    <div v-else class="timeline">
      <div class="tl-count dim">{{ events.length }} event{{ events.length !== 1 ? 's' : '' }} · {{ selectedCase?.client_name }}</div>
      <div v-for="(ev, i) in events" :key="i" class="tl-item">
        <div class="tl-item__spine">
          <div class="tl-item__dot" :style="{ background: sigColor(ev.significance) }"></div>
          <div v-if="i < events.length-1" class="tl-item__line"></div>
        </div>
        <div class="tl-item__body">
          <div class="tl-item__top">
            <span class="tl-item__date">{{ fmtDate(ev) }}</span>
            <span class="sig-pill" :style="{ background: sigColor(ev.significance)+'22', color: sigColor(ev.significance) }">
              {{ sigLabel(ev.significance) }}
            </span>
          </div>
          <div class="tl-item__event">{{ ev.event }}</div>
          <div v-if="ev.parties?.length" class="tl-item__parties dim">
            {{ ev.parties.join(' · ') }}
          </div>
          <div v-if="ev.source_doc" class="tl-item__source dim mono">{{ ev.source_doc }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tl { padding: 2rem; max-width: 800px; }
.tl__header { margin-bottom: 1.5rem; }
.tl__title  { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.tl__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }

.case-tabs { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.5rem; }
.case-tab  { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; cursor: pointer; display: flex; flex-direction: column; gap: 0.1rem; padding: 0.6rem 1rem; text-align: left; transition: border-color .2s; font-size: 0.875rem; color: var(--text-muted); }
.case-tab:hover { border-color: var(--gold); color: var(--text-primary); }
.case-tab--active { border-color: var(--gold); color: var(--text-primary); background: rgba(201,168,76,.05); }

.tl-count { font-size: 0.82rem; margin-bottom: 1.5rem; }

.timeline { display: flex; flex-direction: column; }
.tl-item  { display: flex; gap: 1rem; }
.tl-item__spine { align-items: center; display: flex; flex-direction: column; flex-shrink: 0; width: 20px; }
.tl-item__dot   { border-radius: 50%; flex-shrink: 0; height: 12px; width: 12px; }
.tl-item__line  { background: var(--border); flex: 1; margin: 4px 0; width: 2px; min-height: 24px; }
.tl-item__body  { padding-bottom: 1.5rem; flex: 1; }
.tl-item__top   { align-items: center; display: flex; gap: 0.75rem; margin-bottom: 0.35rem; }
.tl-item__date  { color: var(--text-muted); font-family: var(--font-mono); font-size: 0.8rem; }
.sig-pill       { border-radius: 3px; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.05em; padding: 0.1rem 0.4rem; }
.tl-item__event   { color: var(--text-primary); font-size: 0.9rem; line-height: 1.4; margin-bottom: 0.3rem; }
.tl-item__parties { font-size: 0.78rem; margin-bottom: 0.2rem; }
.tl-item__source  { font-size: 0.72rem; }

.dim    { color: var(--text-muted); }
.mono   { font-family: var(--font-mono); }
.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
.empty-state { padding: 4rem 2rem; text-align: center; }
.empty-state__icon  { color: var(--gold); font-size: 2.5rem; margin-bottom: 1rem; opacity: 0.4; }
.empty-state__title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; margin-bottom: 0.5rem; }
.empty-state__sub   { color: var(--text-muted); font-size: 0.875rem; max-width: 360px; margin: 0 auto; line-height: 1.5; }
</style>
