<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import DiscoveryUpload from '@/components/DiscoveryUpload.vue'

const token   = () => localStorage.getItem('paraiq_token')
const firmId  = () => localStorage.getItem('paraiq_firm_id') || 'default'
const authHdr = () => ({ Authorization: 'Bearer ' + token() })

// ── Document list state ────────────────────────────────────────────────────
const files       = ref([])
const loading     = ref(true)
const search      = ref('')
const filterCase  = ref('')
const filterRoute = ref('')
const filterStatus= ref('')

const ROUTES   = ['digital','ocr','audio','zip','image']
const STATUSES = ['pending','text_extracted','ocr_complete','processed','error']

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
    const { data } = await axios.get('/discovery/queue?limit=200', { headers: authHdr() })
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
  return { digital:'#4a7cf7', ocr:'#48bb78', audio:'#c9a84c', zip:'#a0aec0', image:'#9f7aea' }[r] || '#718096'
}
function statusColor(s) {
  return { pending:'#718096', text_extracted:'#4a7cf7', ocr_complete:'#48bb78', processed:'#48bb78', error:'#fc8181' }[s] || '#718096'
}
function fmtSize(b) {
  if (!b) return '—'
  return b < 1024 ? b+'B' : b < 1048576 ? (b/1024).toFixed(1)+'KB' : (b/1048576).toFixed(1)+'MB'
}
function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleString('en-US', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })
}

onMounted(fetchFiles)
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
            <th>Privilege</th>
            <th>Size</th>
            <th>Uploaded</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in filtered" :key="f.id">
            <td class="dim mono">{{ f.id }}</td>
            <td>
              <div class="filename">{{ f.original_name }}</div>
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
            <!-- Privilege badge — soft scan flag from pipeline -->
            <td>
              <span v-if="f.privilege_flag === true || f.privilege_flag === 1" class="priv-badge">
                ⚠ Review
              </span>
              <span v-else-if="f.privilege_flag === false || f.privilege_flag === 0" class="priv-clear">
                ✓ Clear
              </span>
              <span v-else class="dim" style="font-size:0.75rem">—</span>
            </td>
            <td class="dim">{{ fmtSize(f.file_size) }}</td>
            <td class="dim nowrap">{{ fmtDate(f.created_at) }}</td>
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
</style>
