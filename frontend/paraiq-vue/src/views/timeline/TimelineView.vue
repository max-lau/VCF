<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const token   = () => localStorage.getItem('paraiq_token')
const authHdr = () => ({ Authorization: 'Bearer ' + token() })
const firmId  = () => { try { return JSON.parse(localStorage.getItem('paraiq_user') || '{}').firm_id || 'default' } catch { return 'default' } }

const cases        = ref([])
const events       = ref([])
const loading      = ref(false)
const selectedId   = ref(null)
const selectedCase = computed(() => cases.value.find(c => c.id === selectedId.value))

// Filters
const filterSig    = ref('all')
const filterParty  = ref('all')
const filterFrom   = ref('')
const filterTo     = ref('')
const searchText   = ref('')

// Kanban modal
const showKanban   = ref(false)
const kanbanEvent  = ref(null)
const kanbanForm   = reactive({ title: '', card_type: 'deadline', column_id: 'research', due_date: '' })
const kanbanSaving = ref(false)
const kanbanToast  = ref('')

// Export
const exporting    = ref(false)

import { reactive } from 'vue'

const COLUMNS   = ['intake','research','discovery','motions','trial_prep','closed']
const CARD_TYPES = ['task','deadline','motion','depo','filing']

const allParties = computed(() => {
  const set = new Set()
  events.value.forEach(e => (e.parties || []).forEach(p => set.add(p)))
  return [...set].sort()
})

const filteredEvents = computed(() => {
  return events.value.filter(ev => {
    if (filterSig.value !== 'all' && ev.significance !== filterSig.value) return false
    if (filterParty.value !== 'all' && !(ev.parties || []).includes(filterParty.value)) return false
    const d = ev.date_normalized || ev.date || ''
    if (filterFrom.value && d < filterFrom.value) return false
    if (filterTo.value   && d > filterTo.value)   return false
    if (searchText.value) {
      const q = searchText.value.toLowerCase()
      const hay = (ev.event || '') + ' ' + (ev.parties || []).join(' ') + ' ' + (ev.source_doc || '')
      if (!hay.toLowerCase().includes(q)) return false
    }
    return true
  })
})

async function fetchCases() {
  const { data } = await axios.get('/cases/search?q=&firm_id=' + firmId(), { headers: authHdr() })
  cases.value = data.cases || []
  if (cases.value.length) selectCase(cases.value[0].id)
}

async function selectCase(id) {
  selectedId.value = id
  loading.value = true
  events.value = []
  filterSig.value = 'all'; filterParty.value = 'all'
  filterFrom.value = ''; filterTo.value = ''; searchText.value = ''
  try {
    const { data } = await axios.get(`/cases/${id}/timeline`, { headers: authHdr() })
    const raw = data.timeline || []
    events.value = raw
      .filter(e => e.date || e.date_normalized)
      .sort((a, b) => {
        const da = a.date_normalized || a.date || ''
        const db = b.date_normalized || b.date || ''
        return da > db ? 1 : -1
      })
  } catch { events.value = [] }
  finally { loading.value = false }
}

function sigColor(s) {
  return { high: '#fc8181', medium: '#ecc94b', low: '#48bb78' }[s] || '#718096'
}
function sigLabel(s) {
  return { high: 'HIGH', medium: 'MED', low: 'LOW' }[s] || '—'
}
function fmtDate(ev) { return ev.date || ev.date_normalized || '—' }

// ── Kanban card creation ──────────────────────────────────────────────────────
function openKanban(ev) {
  kanbanEvent.value = ev
  kanbanForm.title     = ev.event?.slice(0, 80) || ''
  kanbanForm.card_type = ev.significance === 'high' ? 'deadline' : 'task'
  kanbanForm.column_id = 'research'
  kanbanForm.due_date  = ev.date_normalized || ev.date || ''
  showKanban.value = true
}

async function saveKanbanCard() {
  if (!kanbanForm.title.trim() || !selectedId.value) return
  kanbanSaving.value = true
  try {
    await axios.post(`/kanban/cases/${selectedId.value}/cards`, {
      case_id:   selectedId.value,
      title:     kanbanForm.title.trim(),
      card_type: kanbanForm.card_type,
      column_id: kanbanForm.column_id,
      due_date:  kanbanForm.due_date || null,
      notes:     `Source: ${kanbanEvent.value?.source_doc || ''}`,
    }, { headers: authHdr() })
    showKanban.value = false
    kanbanToast.value = 'Card added to Kanban board'
    setTimeout(() => { kanbanToast.value = '' }, 2500)
  } catch { kanbanToast.value = 'Failed to create card' }
  finally { kanbanSaving.value = false }
}

// ── Export ────────────────────────────────────────────────────────────────────
function exportCSV() {
  const rows = [['Date', 'Event', 'Significance', 'Parties', 'Source Document']]
  filteredEvents.value.forEach(ev => {
    rows.push([
      fmtDate(ev),
      (ev.event || '').replace(/,/g, ';'),
      ev.significance || '—',
      (ev.parties || []).join('; '),
      ev.source_doc || '—',
    ])
  })
  const csv = rows.map(r => r.map(c => `"${c}"`).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `timeline-${selectedCase.value?.case_number || 'export'}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

async function exportPDF() {
  exporting.value = true
  try {
    const resp = await axios.get(
      `/export/timeline/${selectedId.value}`,
      { headers: authHdr(), responseType: 'blob' }
    )
    const url = URL.createObjectURL(new Blob([resp.data], { type: 'application/pdf' }))
    const a   = document.createElement('a')
    a.href    = url
    a.download = `timeline-${selectedCase.value?.case_number || 'export'}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch { alert('PDF export failed') }
  finally { exporting.value = false }
}

onMounted(fetchCases)
</script>

<template>
  <div class="tl">
    <!-- Header -->
    <div class="tl__header">
      <div>
        <h1 class="tl__title">Timeline</h1>
        <p class="tl__sub">Chronological case event extraction</p>
      </div>
      <div class="tl__exports" v-if="events.length">
        <button class="btn-export" @click="exportCSV">↓ CSV</button>
        <button class="btn-export" @click="exportPDF" :disabled="exporting">
          {{ exporting ? 'Exporting…' : '↓ PDF' }}
        </button>
      </div>
    </div>

    <!-- Case selector -->
    <div class="case-tabs">
      <button v-for="c in cases" :key="c.id"
        :class="['case-tab', { 'case-tab--active': selectedId === c.id }]"
        @click="selectCase(c.id)">
        <span class="mono" style="font-size:0.72rem;opacity:0.6">{{ c.case_number }}</span>
        <span>{{ c.client_name }}</span>
      </button>
    </div>

    <!-- Filter bar -->
    <div v-if="events.length || loading" class="filter-bar">
      <input
        v-model="searchText"
        class="filter-input"
        placeholder="Search events…"
      />
      <select v-model="filterSig" class="filter-select">
        <option value="all">All significance</option>
        <option value="high">High</option>
        <option value="medium">Medium</option>
        <option value="low">Low</option>
      </select>
      <select v-model="filterParty" class="filter-select" v-if="allParties.length">
        <option value="all">All parties</option>
        <option v-for="p in allParties" :key="p" :value="p">{{ p }}</option>
      </select>
      <input type="date" v-model="filterFrom" class="filter-input date-input" title="From date" />
      <span class="dim" style="font-size:0.75rem">→</span>
      <input type="date" v-model="filterTo"   class="filter-input date-input" title="To date" />
      <button v-if="filterSig !== 'all' || filterParty !== 'all' || filterFrom || filterTo || searchText"
        class="btn-clear" @click="filterSig='all';filterParty='all';filterFrom='';filterTo='';searchText=''">
        ✕ Clear
      </button>
    </div>

    <div v-if="loading" class="state-msg">Extracting timeline…</div>

    <div v-else-if="!events.length" class="empty-state">
      <div class="empty-state__icon">⊣</div>
      <div class="empty-state__title">No timeline events extracted yet</div>
      <div class="empty-state__sub">Upload and process documents to extract dates and events automatically.</div>
    </div>

    <template v-else>
      <div class="tl-count dim">
        {{ filteredEvents.length }} of {{ events.length }} event{{ events.length !== 1 ? 's' : '' }}
        · {{ selectedCase?.client_name }}
      </div>

      <!-- Timeline -->
      <div class="timeline">
        <div v-for="(ev, i) in filteredEvents" :key="i" class="tl-item">

          <!-- Spine -->
          <div class="tl-item__spine">
            <div class="tl-item__dot"
              :style="{ background: sigColor(ev.significance), boxShadow: `0 0 0 3px ${sigColor(ev.significance)}22` }">
            </div>
            <div v-if="i < filteredEvents.length - 1" class="tl-item__line"></div>
          </div>

          <!-- Body -->
          <div class="tl-item__body">
            <div class="tl-item__top">
              <span class="tl-item__date">{{ fmtDate(ev) }}</span>
              <span class="sig-pill"
                :style="{ background: sigColor(ev.significance)+'22', color: sigColor(ev.significance) }">
                {{ sigLabel(ev.significance) }}
              </span>
              <span v-if="ev.source === 'nlp_extractor'" class="ai-badge">✦ AI</span>
            </div>
            <div class="tl-item__event">{{ ev.event }}</div>
            <div v-if="ev.parties?.length" class="tl-item__parties">
              <span v-for="p in ev.parties" :key="p" class="party-chip">{{ p }}</span>
            </div>
            <div class="tl-item__footer">
              <span v-if="ev.source_doc" class="tl-item__source mono dim">📄 {{ ev.source_doc }}</span>
              <button class="btn-kanban" @click="openKanban(ev)" title="Create Kanban card from this event">
                ⚖ Add to board
              </button>
            </div>
          </div>
        </div>

        <div v-if="!filteredEvents.length" class="empty-filter">
          No events match the current filters.
        </div>
      </div>
    </template>

    <!-- Kanban modal -->
    <Teleport to="body">
      <div v-if="showKanban" class="modal-backdrop" @click.self="showKanban = false">
        <div class="tl-modal">
          <div class="tl-modal__header">
            <span>Add to Kanban board</span>
            <button class="modal-close" @click="showKanban = false">✕</button>
          </div>
          <div class="tl-modal__body">
            <div class="tl-modal__source dim" v-if="kanbanEvent">
              From: {{ fmtDate(kanbanEvent) }} · {{ kanbanEvent.source_doc }}
            </div>
            <div class="field">
              <label class="field__label">Card title *</label>
              <input v-model="kanbanForm.title" class="piq-input w100" placeholder="Task title" />
            </div>
            <div class="field">
              <label class="field__label">Type</label>
              <select v-model="kanbanForm.card_type" class="piq-input w100">
                <option v-for="t in CARD_TYPES" :key="t" :value="t">{{ t }}</option>
              </select>
            </div>
            <div class="field">
              <label class="field__label">Column</label>
              <select v-model="kanbanForm.column_id" class="piq-input w100">
                <option v-for="c in COLUMNS" :key="c" :value="c">{{ c.replace('_',' ') }}</option>
              </select>
            </div>
            <div class="field">
              <label class="field__label">Due date</label>
              <input type="date" v-model="kanbanForm.due_date" class="piq-input w100" />
            </div>
          </div>
          <div class="tl-modal__footer">
            <button class="btn-secondary" @click="showKanban = false">Cancel</button>
            <button class="btn-gold" @click="saveKanbanCard"
              :disabled="kanbanSaving || !kanbanForm.title.trim()">
              {{ kanbanSaving ? 'Saving…' : 'Add to board' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Toast -->
    <Transition name="toast">
      <div v-if="kanbanToast" class="kb-toast">{{ kanbanToast }}</div>
    </Transition>
  </div>
</template>

<style scoped>
.tl { padding: 2rem; max-width: 860px; }

.tl__header  { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.5rem; }
.tl__title   { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.tl__sub     { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.tl__exports { display: flex; gap: 0.5rem; align-items: center; }
.btn-export  { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.78rem; padding: 0.35rem 0.85rem; transition: all .15s; }
.btn-export:hover:not(:disabled) { border-color: var(--gold); color: var(--gold); }
.btn-export:disabled { opacity: 0.4; cursor: not-allowed; }

.case-tabs { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.25rem; }
.case-tab  { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; cursor: pointer; display: flex; flex-direction: column; gap: 0.1rem; padding: 0.6rem 1rem; text-align: left; transition: border-color .2s; font-size: 0.875rem; color: var(--text-muted); }
.case-tab:hover      { border-color: var(--gold); color: var(--text-primary); }
.case-tab--active    { border-color: var(--gold); color: var(--text-primary); background: rgba(201,168,76,.05); }

/* Filter bar */
.filter-bar    { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-bottom: 1.25rem; padding: 0.75rem 1rem; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; }
.filter-input  { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 5px; color: var(--text-primary); font-family: inherit; font-size: 0.8rem; outline: none; padding: 0.3rem 0.65rem; }
.filter-input:focus { border-color: var(--gold); }
.filter-select { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 5px; color: var(--text-primary); font-family: inherit; font-size: 0.8rem; outline: none; padding: 0.3rem 0.65rem; cursor: pointer; }
.date-input    { width: 130px; }
.btn-clear     { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.78rem; padding: 0.2rem 0.5rem; }
.btn-clear:hover { color: #fc8181; }

.tl-count { font-size: 0.82rem; margin-bottom: 1.5rem; }

/* Timeline spine */
.timeline  { display: flex; flex-direction: column; position: relative; }
.tl-item   { display: flex; gap: 1.25rem; }
.tl-item__spine { align-items: center; display: flex; flex-direction: column; flex-shrink: 0; width: 24px; padding-top: 3px; }
.tl-item__dot   { border-radius: 50%; flex-shrink: 0; height: 14px; width: 14px; transition: transform 0.2s; }
.tl-item:hover .tl-item__dot { transform: scale(1.25); }
.tl-item__line  { background: rgba(255,255,255,0.15); flex: 1; margin: 6px 0; width: 3px; min-height: 32px; border-radius: 2px; }

.tl-item__body   { padding-bottom: 1.75rem; flex: 1; min-width: 0; }
.tl-item__top    { align-items: center; display: flex; gap: 0.6rem; margin-bottom: 0.4rem; flex-wrap: wrap; }
.tl-item__date   { color: var(--text-muted); font-family: var(--font-mono); font-size: 0.8rem; }
.sig-pill        { border-radius: 3px; font-size: 0.65rem; font-weight: 700; letter-spacing: 0.05em; padding: 0.1rem 0.4rem; }
.ai-badge        { background: rgba(159,122,234,.15); border-radius: 3px; color: #9f7aea; font-size: 0.65rem; font-weight: 700; padding: 0.1rem 0.4rem; }
.tl-item__event  { color: var(--text-primary); font-size: 0.9rem; line-height: 1.5; margin-bottom: 0.4rem; }
.tl-item__parties { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-bottom: 0.4rem; }
.party-chip      { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); font-size: 0.7rem; padding: 0.1rem 0.45rem; }
.tl-item__footer { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.tl-item__source { font-size: 0.72rem; }
.btn-kanban      { background: none; border: 1px solid var(--border); border-radius: 5px; color: var(--text-muted); cursor: pointer; font-size: 0.72rem; padding: 0.2rem 0.6rem; opacity: 0; transition: opacity 0.15s, border-color 0.15s, color 0.15s; white-space: nowrap; }
.tl-item:hover .btn-kanban { opacity: 1; }
.btn-kanban:hover { border-color: var(--gold); color: var(--gold); }

.empty-filter { color: var(--text-muted); padding: 2rem; text-align: center; font-size: 0.875rem; }

/* Kanban modal */
.modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.65); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.tl-modal { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 10px; width: 420px; display: flex; flex-direction: column; box-shadow: 0 24px 80px rgba(0,0,0,.5); }
.tl-modal__header { align-items: center; border-bottom: 1px solid var(--border); color: var(--text-primary); display: flex; font-size: 0.95rem; font-weight: 600; justify-content: space-between; padding: 1rem 1.25rem; }
.tl-modal__source { font-size: 0.75rem; margin-bottom: 0.75rem; }
.tl-modal__body   { display: flex; flex-direction: column; gap: 0.85rem; padding: 1.25rem; }
.tl-modal__footer { border-top: 1px solid var(--border); display: flex; gap: 0.5rem; justify-content: flex-end; padding: 1rem 1.25rem; }
.modal-close { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1rem; }

/* Toast */
.kb-toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: var(--bg-raised); border: 1px solid var(--border); color: var(--text-primary); font-size: 0.8rem; padding: 8px 16px; border-radius: 8px; z-index: 2000; }
.toast-enter-active, .toast-leave-active { transition: all 0.2s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(6px); }

/* Shared form styles */
.field { display: flex; flex-direction: column; gap: 0.3rem; }
.field__label { color: var(--text-muted); font-size: 0.68rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.piq-input { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-family: inherit; font-size: 0.875rem; outline: none; padding: 0.5rem 0.75rem; }
.piq-input:focus { border-color: var(--gold); }
.w100 { width: 100%; box-sizing: border-box; }
.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1.1rem; }
.btn-gold:disabled { opacity: .45; cursor: not-allowed; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; }

.dim  { color: var(--text-muted); }
.mono { font-family: var(--font-mono); }
.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
.empty-state { padding: 4rem 2rem; text-align: center; }
.empty-state__icon  { color: var(--gold); font-size: 2.5rem; margin-bottom: 1rem; opacity: 0.4; }
.empty-state__title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; margin-bottom: 0.5rem; }
.empty-state__sub   { color: var(--text-muted); font-size: 0.875rem; max-width: 360px; margin: 0 auto; line-height: 1.5; }
</style>
