<script setup>
import { ref, onMounted } from 'vue'
import client from '@/api/client'

const firmId  = () => { try { return JSON.parse(localStorage.getItem('paraiq_user')||'{}').firm_id||'default' } catch { return 'default' } }

const matters  = ref([])
const selected = ref(null)
const summary  = ref(null)
const loading  = ref(false)

const TABLES = [
  { key:'documents',       label:'Documents',        icon:'📄' },
  { key:'correspondence',  label:'Correspondence',   icon:'✉' },
  { key:'calendar_events', label:'Calendar Events',  icon:'📅' },
  { key:'contacts',        label:'Contacts',          icon:'👥' },
  { key:'research_notes',  label:'Research Notes',   icon:'🔬' },
  { key:'reports',         label:'Reports',           icon:'📋' },
]

async function fetchMatters() {
  try {
    const { data } = await client.get('/cases/search?q=&firm_id=' + firmId())
    matters.value = data.cases || []
    if (matters.value.length) { selected.value = matters.value[0]; fetchSummary() }
  } catch {}
}

async function fetchSummary() {
  if (!selected.value) return
  loading.value = true
  try {
    const { data } = await client.get('/exports/matter/' + selected.value.id + '/summary')
    summary.value = data
  } catch { summary.value = null }
  finally { loading.value = false }
}

function downloadFile(url, filename) {
  const tok = token()
  fetch(url, { headers: { Authorization: 'Bearer ' + tok } })
    .then(r => r.blob())
    .then(blob => {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = filename
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
    })
}

function downloadCsv(tableKey) {
  const url = '/exports/matter/' + selected.value.id + '/csv?table=' + tableKey
  downloadFile(url, 'matter_' + selected.value.id + '_' + tableKey + '.csv')
}

function downloadJson() {
  const url = '/exports/matter/' + selected.value.id + '/json'
  downloadFile(url, 'matter_' + selected.value.id + '_full.json')
}

onMounted(fetchMatters)
</script>

<template>
  <div class="exp">
    <div class="exp__header">
      <div>
        <h1 class="exp__title">Exports</h1>
        <p class="exp__sub">Download matter data as CSV or JSON</p>
      </div>
    </div>

    <div class="matter-bar">
      <label class="bar-label">Matter</label>
      <select class="bar-select" v-model="selected" @change="fetchSummary">
        <option v-for="m in matters" :key="m.id" :value="m">{{ m.case_number }} — {{ m.client_name }}</option>
      </select>
    </div>

    <div v-if="selected" class="export-panel">
      <div class="export-section">
        <div class="section-title">Full Matter Export</div>
        <div class="full-export-card">
          <div class="full-export-icon">📦</div>
          <div class="full-export-body">
            <div class="full-export-name">Complete Matter Package</div>
            <div class="dim sm">All data for {{ selected?.client_name }} in a single JSON file</div>
          </div>
          <button class="btn-gold" @click="downloadJson">↓ Download JSON</button>
        </div>
      </div>

      <div class="export-section">
        <div class="section-title">Export by Table</div>
        <div v-if="loading" class="state-msg">Loading…</div>
        <div v-else class="table-grid">
          <div v-for="t in TABLES" :key="t.key" class="table-card">
            <div class="table-card__icon">{{ t.icon }}</div>
            <div class="table-card__body">
              <div class="table-name">{{ t.label }}</div>
              <div class="dim sm">{{ summary?.[t.key] ?? '—' }} records</div>
            </div>
            <button class="btn-secondary" @click="downloadCsv(t.key)" :disabled="!summary || !summary[t.key]">↓ CSV</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.exp { padding: 2rem; max-width: 800px; }
.exp__header { margin-bottom: 1.25rem; }
.exp__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.exp__sub   { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.matter-bar { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; }
.bar-label  { color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: .05em; }
.bar-select { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; padding: 0.4rem 0.75rem; max-width: 340px; }
.export-panel { display: flex; flex-direction: column; gap: 2rem; }
.export-section {}
.section-title { color: var(--text-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: .08em; margin-bottom: 0.75rem; text-transform: uppercase; }
.full-export-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; display: flex; align-items: center; gap: 1rem; padding: 1.25rem 1.5rem; }
.full-export-icon { font-size: 2rem; }
.full-export-body { flex: 1; }
.full-export-name { color: var(--text-primary); font-size: 0.95rem; font-weight: 600; margin-bottom: 0.25rem; }
.table-grid { display: grid; gap: 0.5rem; }
.table-card { align-items: center; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; display: flex; gap: 0.75rem; padding: 0.85rem 1rem; }
.table-card__icon { font-size: 1.2rem; }
.table-card__body { flex: 1; }
.table-name { color: var(--text-primary); font-size: 0.875rem; font-weight: 500; }
.sm { font-size: 0.78rem; }
.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1.1rem; transition: opacity .15s; }
.btn-gold:hover { opacity: .85; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.8rem; padding: 0.4rem 0.85rem; transition: all .15s; }
.btn-secondary:hover:not(:disabled) { background: var(--bg-raised); color: var(--text-primary); }
.btn-secondary:disabled { opacity: .4; cursor: not-allowed; }
.state-msg { color: var(--text-muted); padding: 2rem; text-align: center; }
.dim { color: var(--text-muted); }
</style>
