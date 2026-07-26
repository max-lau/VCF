<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import DiscoveryUpload from '@/components/DiscoveryUpload.vue'
import DocumentViewer from '@/components/DocumentViewer.vue'

const token   = () => localStorage.getItem('paraiq_token')
const firmId  = () => localStorage.getItem('paraiq_firm_id') || 'default'
const authHdr = () => ({ Authorization: 'Bearer ' + token() })

// ── Document viewer state ───────────────────────────────────────────────────
const viewingDoc   = ref(null)
const docMatters   = ref([])
const docMatterMap = ref({})

// ── Document list state ────────────────────────────────────────────────────
const files       = ref([])
const loading     = ref(true)
const search      = ref('')
const filterCase  = ref('')
const filterRoute = ref('')
const filterStatus= ref('')

const ROUTES   = ['intake_scan','email_attachment','manual','other']
const STATUSES = ['pending','processed']

// ── Upload state ───────────────────────────────────────────────────────────
const showPicker      = ref(false)
const showUpload      = ref(false)
const uploadMatterId  = ref(0)
const uploadMatterName= ref('')
const uploadCaseNum   = ref('')
const matters         = ref([])
const mattersLoading  = ref(false)
const mattersError    = ref('')

// ── Fetch documents ────────────────────────────────────────────────────────
async function fetchFiles() {
  loading.value = true
  try {
    const { data } = await axios.get('/documents/?limit=200', { headers: authHdr() })
    files.value = data.files || []
  } catch { files.value = [] }
  finally { loading.value = false }
}

// ── Fetch matters for picker ───────────────────────────────────────────────
async function fetchMatters() {
  mattersLoading.value = true
  mattersError.value   = ''
  try {
    const { data } = await axios.get(
      `/cases/search?q=&firm_id=${firmId()}`,
      { headers: authHdr() }
    )
    matters.value = data.cases || []
  } catch {
    mattersError.value = 'Could not load matters.'
    matters.value = []
  } finally {
    mattersLoading.value = false
  }
}

// ── Picker flow ────────────────────────────────────────────────────────────
function openPicker() {
  showPicker.value = true
  fetchMatters()
}

function selectMatter(m) {
  uploadMatterId.value   = m.id
  uploadMatterName.value = m.client_name || m.name || m.title || `Matter #${m.id}`
  uploadCaseNum.value    = m.case_number || ''
  showPicker.value       = false
  showUpload.value       = true
}

function closePicker() {
  showPicker.value = false
}

function onUploadClose() {
  showUpload.value = false
}

async function redactDoc(file) {
  try {
    const { data } = await axios.post(`/redact/case-document/${file.id}`, {}, { headers: authHdr() })
    if (data.download_url) {
      window.open(data.download_url, '_blank')
    }
  } catch (e) {
    alert(e.response?.data?.detail || 'Redaction failed')
  }
}

function onUploaded() {
  // Give backend ~1.5s to register then refresh the list
  setTimeout(fetchFiles, 1500)
}

// ── Computed ───────────────────────────────────────────────────────────────
const filtered = computed(() => files.value.filter(f => {
  const q = search.value.toLowerCase()
  const matchQ      = !q || f.original_name?.toLowerCase().includes(q) || f.case_number?.toLowerCase().includes(q)
  const matchCase   = !filterCase.value   || f.case_number === filterCase.value
  const matchRoute  = !filterRoute.value  || f.route === filterRoute.value
  const matchStatus = !filterStatus.value || f.status === filterStatus.value
  return matchQ && matchCase && matchRoute && matchStatus
}))

const cases = computed(() => [...new Set(files.value.map(f => f.case_number).filter(Boolean))])

const statsByRoute = computed(() => {
  const counts = {}
  files.value.forEach(f => { counts[f.route] = (counts[f.route]||0)+1 })
  return counts
})

// ── Helpers ────────────────────────────────────────────────────────────────
function routeColor(r) {
  return { intake_scan:'#4a7cf7', email_attachment:'#48bb78', manual:'#c9a84c', other:'#a0aec0' }[r] || '#718096'
}
function statusColor(s) {
  return { pending:'#718096', processed:'#48bb78', error:'#fc8181' }[s] || '#718096'
}
function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleString('en-US', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })
}

onMounted(fetchFiles)

// ── Document viewer ─────────────────────────────────────────────────────────
function openDoc(file) {
  // The /documents/{doc_id}/annotated endpoint uses case_documents.id
  // Discovery files use a different ID space, so we need to find the matching case_document
  // For now, we open by the discovery file ID and the backend will look it up by name
  viewingDoc.value = file.id
}

function closeDoc() {
  viewingDoc.value = null
}
</script>

<template>
  <div class="docs">

    <!-- ── Header ─────────────────────────────────────────────────────── -->
    <div class="docs__header">
      <div>
        <h1 class="docs__title">Documents</h1>
        <p class="docs__sub">All uploaded and processed files</p>
      </div>
      <button class="btn-upload" @click="openPicker">
        ↑ Upload Documents
      </button>
    </div>

    <!-- ── Stats ──────────────────────────────────────────────────────── -->
    <div class="stats-bar">
      <div class="stat-card">
        <div class="stat-card__val">{{ files.length }}</div>
        <div class="stat-card__label">Total Files</div>
      </div>
      <div v-for="(count, route) in statsByRoute" :key="route" class="stat-card">
        <div class="stat-card__val" :style="{ color: routeColor(route) }">{{ count }}</div>
        <div class="stat-card__label">{{ route }}</div>
      </div>
    </div>

    <!-- ── Filters ─────────────────────────────────────────────────────── -->
    <div class="filters">
      <input v-model="search" class="piq-input" placeholder="Search filename or case…" style="max-width:280px" />
      <select v-model="filterCase" class="piq-input" style="max-width:180px">
        <option value="">All cases</option>
        <option v-for="c in cases" :key="c" :value="c">{{ c }}</option>
      </select>
      <select v-model="filterRoute" class="piq-input" style="max-width:130px">
        <option value="">All types</option>
        <option v-for="r in ROUTES" :key="r" :value="r">{{ r }}</option>
      </select>
      <select v-model="filterStatus" class="piq-input" style="max-width:170px">
        <option value="">All statuses</option>
        <option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
      </select>
    </div>

    <!-- ── Table ──────────────────────────────────────────────────────── -->
    <div v-if="loading" class="state-msg">Loading documents…</div>
    <div v-else-if="!filtered.length" class="state-msg dim">No documents match your filter.</div>

    <div v-else class="piq-table-wrap">
      <table class="piq-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Filename</th>
            <th>Case</th>
            <th>Type</th>
            <th>Status</th>
            <th>Uploaded</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in filtered" :key="f.id" class="doc-row">
            <td class="dim mono">{{ f.id }}</td>
            <td>
              <div class="filename" @click="openDoc(f)">{{ f.original_name }}</div>
              <div v-if="f.file_hash" class="dim mono" style="font-size:0.72rem">{{ f.file_hash }}</div>
            </td>
            <td class="dim mono">{{ f.case_number || '—' }}</td>
            <td>
              <span class="route-pill" :style="{ background: routeColor(f.route)+'22', color: routeColor(f.route) }">
                {{ f.route }}
              </span>
            </td>
            <td>
              <span class="status-pill" :style="{ background: statusColor(f.status)+'22', color: statusColor(f.status) }">
                {{ f.status?.replace('_',' ') }}
              </span>
            </td>
            <td class="dim nowrap">{{ fmtDate(f.created_at) }}</td>
            <td>
              <button class="link-btn" @click.stop="redactDoc(f)">Redact</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ── Matter Picker Modal ─────────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="showPicker" class="modal-overlay" @click.self="closePicker">
        <div class="picker-modal">
          <div class="picker-header">
            <div>
              <h2 class="picker-title">Select Matter</h2>
              <p class="picker-sub">Choose the matter these documents belong to</p>
            </div>
            <button class="close-btn" @click="closePicker">✕</button>
          </div>

          <div v-if="mattersLoading" class="picker-state">Loading matters…</div>
          <div v-else-if="mattersError" class="picker-state error-text">{{ mattersError }}</div>
          <div v-else-if="!matters.length" class="picker-state dim">No matters found.</div>

          <div v-else class="matter-list">
            <button
              v-for="m in matters"
              :key="m.id"
              class="matter-row"
              @click="selectMatter(m)"
            >
              <div class="matter-row__left">
                <div class="matter-row__name">{{ m.client_name || m.name || m.title || `Matter #${m.id}` }}</div>
                <div class="matter-row__meta dim mono">
                  {{ m.case_number || '' }}
                  <span v-if="m.court"> · {{ m.court }}</span>
                </div>
              </div>
              <span class="matter-row__arrow">→</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Discovery Upload Modal (reused component) ───────────────────── -->
    <DiscoveryUpload
      :show="showUpload"
      :matter-id="uploadMatterId"
      :matter-name="uploadMatterName"
      :case-number="uploadCaseNum"
      @close="onUploadClose"
      @uploaded="onUploaded"
    />

    <!-- ── Document Viewer Panel (inline annotations) ─────────────────── -->
    <Teleport to="body">
      <div v-if="viewingDoc" class="dv-overlay" @click.self="closeDoc">
        <div class="dv-panel">
          <DocumentViewer :doc-id="viewingDoc" @close="closeDoc" />
        </div>
      </div>
    </Teleport>

  </div>
</template>

<style scoped>
.docs { padding: 2rem; max-width: 1200px; }

/* Header */
.docs__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 1.5rem;
  gap: 1rem;
}
.docs__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.docs__sub   { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }

/* Upload button — matches Discovery view style */
.btn-upload {
  background: var(--gold, #c9a84c);
  border: none;
  color: #0d0d14;
  font-size: 0.875rem;
  font-weight: 700;
  padding: 0.6rem 1.25rem;
  border-radius: 8px;
  cursor: pointer;
  white-space: nowrap;
  letter-spacing: 0.02em;
  transition: opacity 0.15s, box-shadow 0.15s;
  flex-shrink: 0;
}
.btn-upload:hover {
  opacity: 0.88;
  box-shadow: 0 4px 16px rgba(201,168,76,0.35);
}

/* Stats */
.stats-bar { display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.stat-card  { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.25rem; min-width: 100px; }
.stat-card__val   { font-size: 1.5rem; font-weight: 700; color: var(--text-primary); }
.stat-card__label { color: var(--text-muted); font-size: 0.75rem; margin-top: 0.2rem; }

/* Filters */
.filters { display: flex; gap: 0.75rem; margin-bottom: 1rem; flex-wrap: wrap; }

/* Table */
.piq-table-wrap { border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; }
.piq-table { border-collapse: collapse; font-size: 0.875rem; width: 100%; }
.piq-table th {
  background: var(--bg-card); border-bottom: 1px solid var(--border);
  color: var(--text-muted); font-size: 0.72rem; font-weight: 600;
  letter-spacing: 0.05em; padding: 0.65rem 0.9rem;
  text-align: left; text-transform: uppercase;
}
.piq-table td { border-bottom: 1px solid var(--border); padding: 0.7rem 0.9rem; vertical-align: top; }
.piq-table tr:last-child td { border-bottom: none; }
.piq-table tr:hover td { background: rgba(255,255,255,.02); }

.filename    { color: var(--text-primary); font-size: 0.85rem; font-weight: 500; word-break: break-all; }
.route-pill  { border-radius: 4px; font-size: 0.72rem; font-weight: 600; padding: 0.2rem 0.5rem; text-transform: uppercase; }
.status-pill { border-radius: 4px; font-size: 0.72rem; font-weight: 600; padding: 0.2rem 0.5rem; white-space: nowrap; }

/* Privilege badges */
.priv-badge {
  background: rgba(201,168,76,0.12);
  color: #c9a84c;
  border: 1px solid rgba(201,168,76,0.3);
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0.2rem 0.5rem;
  white-space: nowrap;
  cursor: pointer;
}
.priv-badge:hover { background: rgba(201,168,76,0.2); }
.priv-clear {
  background: rgba(72,187,120,0.1);
  color: #48bb78;
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0.2rem 0.5rem;
}

/* Matter picker modal */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.7);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}

.picker-modal {
  background: var(--surface, #111122);
  border: 1px solid var(--border-color, #2a2a3a);
  border-radius: 14px;
  width: 100%; max-width: 520px;
  max-height: 80vh;
  overflow-y: auto;
  display: flex; flex-direction: column;
  box-shadow: 0 24px 64px rgba(0,0,0,0.6);
}

.picker-header {
  display: flex; align-items: flex-start;
  justify-content: space-between;
  padding: 24px 24px 16px;
  border-bottom: 1px solid var(--border-color, #2a2a3a);
}
.picker-title {
  font-size: 1rem; font-weight: 700;
  color: var(--text-primary, #e0e0e0); margin: 0 0 4px;
  font-family: var(--font-display);
  color: var(--gold, #c9a84c);
}
.picker-sub { font-size: 0.78rem; color: var(--text-muted, #888); margin: 0; }

.close-btn {
  background: none; border: none;
  color: var(--text-muted, #888); font-size: 16px;
  cursor: pointer; padding: 4px 8px; border-radius: 4px;
  transition: color 0.15s; line-height: 1;
}
.close-btn:hover { color: var(--text-primary, #e0e0e0); }

.picker-state { padding: 2rem; text-align: center; color: var(--text-muted); font-size: 0.875rem; }

.matter-list { padding: 12px; display: flex; flex-direction: column; gap: 6px; }

.matter-row {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--input-bg, #0d0d1a);
  border: 1px solid var(--border-color, #1e1e30);
  border-radius: 8px;
  padding: 12px 16px;
  cursor: pointer; text-align: left; width: 100%;
  transition: border-color 0.15s, background 0.15s;
}
.matter-row:hover {
  border-color: var(--gold, #c9a84c);
  background: rgba(201,168,76,0.05);
}
.matter-row__name {
  font-size: 0.875rem; font-weight: 600;
  color: var(--text-primary, #e0e0e0);
  margin-bottom: 2px;
}
.matter-row__meta { font-size: 0.75rem; }
.matter-row__arrow { color: var(--gold, #c9a84c); font-size: 1rem; flex-shrink: 0; margin-left: 12px; }

/* Shared */
.dim    { color: var(--text-muted); }
.mono   { font-family: var(--font-mono); }
.nowrap { white-space: nowrap; }
.error-text { color: #fc8181; }
.state-msg  { color: var(--text-muted); padding: 3rem; text-align: center; }
.doc-row { cursor: pointer; transition: background .12s; }
.doc-row:hover { background: rgba(201,168,76,.06); }

.dv-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.7); backdrop-filter: blur(4px); z-index: 200; display: flex; align-items: center; justify-content: center; padding: 2rem; }
.dv-panel { width: 100%; max-width: 900px; max-height: 88vh; }
</style>
