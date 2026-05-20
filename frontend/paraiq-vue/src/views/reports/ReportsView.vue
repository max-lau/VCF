<script setup>
import { ref, onMounted } from 'vue'
import client from '@/api/client'

const firmId  = () => { try { return JSON.parse(localStorage.getItem('paraiq_user')||'{}').firm_id||'default' } catch { return 'default' } }

const matters        = ref([])
const reports        = ref([])
const selectedMatter = ref(null)
const loading        = ref(false)
const generating     = ref({})

const REPORT_TYPES = [
  { key:'case_summary',        label:'Case Summary',          icon:'📋' },
  { key:'timeline_report',     label:'Timeline Report',       icon:'📅' },
  { key:'privilege_log',       label:'Privilege Log',         icon:'🔒' },
  { key:'discovery_index',     label:'Discovery Index',       icon:'🗂' },
  { key:'contradiction_report',label:'Contradiction Report',  icon:'⚡' },
  { key:'deadline_report',     label:'Deadline Report',       icon:'⏰' },
  { key:'correspondence_log',  label:'Correspondence Log',    icon:'✉' },
  { key:'contact_sheet',       label:'Contact Sheet',         icon:'👥' },
]

async function fetchMatters() {
  try {
    const { data } = await client.get('/cases/search?q=&firm_id=' + firmId())
    matters.value = data.cases || []
    if (matters.value.length) { selectedMatter.value = matters.value[0]; fetchReports() }
  } catch {}
}

async function fetchReports() {
  if (!selectedMatter.value) return
  loading.value = true
  try {
    const { data } = await client.get('/reports/matter/' + selectedMatter.value.id)
    reports.value = data
  } catch { reports.value = [] }
  finally { loading.value = false }
}

async function generate(type) {
  if (!selectedMatter.value) return
  generating.value = { ...generating.value, [type]: true }
  try {
    await client.post('/reports/generate/' + selectedMatter.value.id + '/' + type, null)
    fetchReports()
  } catch {} finally {
    const g = { ...generating.value }
    delete g[type]
    generating.value = g
  }
}

async function deleteReport(id) {
  if (!confirm('Delete this report?')) return
  await client.delete('/reports/' + id)
  fetchReports()
}

function fmtDate(d) {
  return d ? new Date(d).toLocaleString('en-US', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' }) : '—'
}

onMounted(fetchMatters)
</script>

<template>
  <div class="rpt">
    <div class="rpt__header">
      <div>
        <h1 class="rpt__title">Reports</h1>
        <p class="rpt__sub">Generate and download matter reports</p>
      </div>
    </div>

    <div class="matter-bar">
      <label class="bar-label">Matter</label>
      <select class="bar-select" v-model="selectedMatter" @change="fetchReports">
        <option v-for="m in matters" :key="m.id" :value="m">{{ m.case_number }} — {{ m.client_name }}</option>
      </select>
    </div>

    <div class="generate-grid">
      <div v-for="rt in REPORT_TYPES" :key="rt.key" class="gen-card" @click="generate(rt.key)">
        <div class="gen-icon">{{ rt.icon }}</div>
        <div class="gen-label">{{ rt.label }}</div>
        <div v-if="generating[rt.key]" class="gen-spinner">generating…</div>
        <div v-else class="gen-cta">Generate ↓</div>
      </div>
    </div>

    <div v-if="reports.length" class="reports-section">
      <div class="section-title">Generated Reports</div>
      <div v-if="loading" class="state-msg">Loading…</div>
      <div v-else class="rpt-list">
        <div v-for="r in reports" :key="r.id" class="rpt-row">
          <span class="rpt-icon">📄</span>
          <div class="rpt-info">
            <div class="rpt-name">{{ r.title }}</div>
            <div class="dim sm">{{ r.report_type.replace(/_/g,' ') }} · {{ fmtDate(r.created_at) }}</div>
          </div>
          <span class="status-pill">{{ r.status }}</span>
          <button class="del-btn" @click="deleteReport(r.id)">✕</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rpt { padding: 2rem; max-width: 1000px; }
.rpt__header { margin-bottom: 1.25rem; }
.rpt__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.rpt__sub   { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.matter-bar { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; }
.bar-label  { color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: .05em; }
.bar-select { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; padding: 0.4rem 0.75rem; max-width: 340px; }
.generate-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px,1fr)); gap: 0.75rem; margin-bottom: 2rem; }
.gen-card  { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; cursor: pointer; padding: 1.25rem 1rem; text-align: center; transition: border-color .15s, background .15s; }
.gen-card:hover { border-color: var(--gold); background: rgba(201,168,76,.05); }
.gen-icon  { font-size: 1.75rem; margin-bottom: 0.6rem; }
.gen-label { color: var(--text-primary); font-size: 0.8rem; font-weight: 600; margin-bottom: 0.4rem; }
.gen-cta   { color: var(--gold); font-size: 0.72rem; }
.gen-spinner { color: var(--text-muted); font-size: 0.72rem; }
.reports-section { margin-top: 1rem; }
.section-title { color: var(--text-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: .08em; margin-bottom: 0.75rem; text-transform: uppercase; }
.rpt-list { display: flex; flex-direction: column; gap: 0.4rem; }
.rpt-row  { align-items: center; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; display: flex; gap: 0.75rem; padding: 0.75rem 1rem; }
.rpt-icon { font-size: 1.2rem; }
.rpt-info { flex: 1; }
.rpt-name { color: var(--text-primary); font-size: 0.875rem; font-weight: 500; }
.sm { font-size: 0.78rem; }
.status-pill { background: rgba(72,187,120,.15); border-radius: 4px; color: #48bb78; font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.4rem; text-transform: capitalize; }
.del-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.2rem 0.4rem; }
.del-btn:hover { color: #fc8181; }
.state-msg { color: var(--text-muted); padding: 2rem; text-align: center; }
.dim { color: var(--text-muted); }
</style>
