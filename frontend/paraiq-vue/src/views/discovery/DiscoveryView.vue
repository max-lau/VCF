<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import DiscoveryUpload from '@/components/DiscoveryUpload.vue'

const token   = () => localStorage.getItem('paraiq_token')
const authHdr = () => ({ Authorization: 'Bearer ' + token() })

const stats      = ref(null)
const queue      = ref([])
const catalog    = ref([])
const duplicates = ref([])
const loading    = ref(true)
const showUpload = ref(false)

function onDocUploaded() { fetchAll() }
const activeTab  = ref('queue')

async function fetchAll() {
  loading.value = true
  try {
    const [sRes, qRes] = await Promise.all([
      axios.get('/discovery/stats',   { headers: authHdr() }),
      axios.get('/discovery/queue?limit=100',  { headers: authHdr() }),
    ])
    stats.value = sRes.data
    queue.value = qRes.data.files || []
  } catch {}
  finally { loading.value = false }
}

async function fetchDuplicates() {
  try {
    const { data } = await axios.get('/discovery/duplicates', { headers: authHdr() })
    duplicates.value = data.duplicates || data.groups || []
  } catch { duplicates.value = [] }
}

function switchTab(t) {
  activeTab.value = t
  if (t === 'duplicates' && !duplicates.value.length) fetchDuplicates()
}

const PIPELINE = [
  { key: 'pending',        label: 'Pending',        color: '#718096' },
  { key: 'text_extracted', label: 'Text Extracted',  color: '#4a7cf7' },
  { key: 'ocr_complete',   label: 'OCR Complete',    color: '#9f7aea' },
  { key: 'processed',      label: 'Processed',       color: '#48bb78' },
  { key: 'error',          label: 'Error',           color: '#fc8181' },
]

function countByStatus(s) { return queue.value.filter(f => f.status === s).length }
function routeColor(r) {
  return {digital:'#4a7cf7',ocr:'#48bb78',audio:'#c9a84c',zip:'#a0aec0',image:'#9f7aea'}[r]||'#718096'
}
function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})
}
function fmtSize(b) {
  if (!b) return '—'
  return b < 1048576 ? (b/1024).toFixed(1)+'KB' : (b/1048576).toFixed(1)+'MB'
}

onMounted(fetchAll)
</script>

<template>
  <div class="disc">
    <div class="disc__header">
      <div>
        <h1 class="disc__title">Discovery</h1>
        <p class="disc__sub">Intake pipeline · processing status · duplicate detection</p>
      </div>
      <button class="upload-btn" @click="showUpload = true">↑ Upload Documents</button>
    </div>

    <DiscoveryUpload
      :show="showUpload"
      :matter-id="0"
      matter-name="Discovery Intake"
      @close="showUpload = false"
      @uploaded="onDocUploaded"
    />

    <!-- Stats -->
    <div v-if="stats" class="stats-grid">
      <div class="stat-card">
        <div class="stat-card__val">{{ stats.total }}</div>
        <div class="stat-card__label">Total Files</div>
      </div>
      <div v-for="(count, route) in stats.by_route" :key="route" class="stat-card">
        <div class="stat-card__val" :style="{ color: routeColor(route) }">{{ count }}</div>
        <div class="stat-card__label">{{ route }}</div>
      </div>
    </div>

    <!-- Pipeline bar -->
    <div class="pipeline">
      <div v-for="step in PIPELINE" :key="step.key" class="pipeline-step">
        <div class="pipeline-step__count" :style="{ color: step.color }">{{ countByStatus(step.key) }}</div>
        <div class="pipeline-step__label">{{ step.label }}</div>
        <div class="pipeline-step__bar" :style="{ background: step.color + '33' }">
          <div class="pipeline-step__fill" :style="{ background: step.color, width: queue.length ? (countByStatus(step.key)/queue.length*100)+'%' : '0%' }"></div>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="tabs">
      <button v-for="t in ['queue','duplicates']" :key="t"
        :class="['tab', { 'tab--active': activeTab === t }]"
        @click="switchTab(t)">
        {{ t.charAt(0).toUpperCase() + t.slice(1) }}
      </button>
    </div>

    <div v-if="loading" class="state-msg">Loading…</div>

    <!-- Queue tab -->
    <div v-else-if="activeTab === 'queue'">
      <div v-if="!queue.length" class="state-msg dim">No files in queue.</div>
      <div v-else class="piq-table-wrap">
        <table class="piq-table">
          <thead>
            <tr><th>ID</th><th>Filename</th><th>Case</th><th>Route</th><th>Status</th><th>Size</th><th>Date</th></tr>
          </thead>
          <tbody>
            <tr v-for="f in queue" :key="f.id">
              <td class="dim mono">{{ f.id }}</td>
              <td>
                <div class="filename">{{ f.original_name }}</div>
              </td>
              <td class="dim mono">{{ f.case_number || '—' }}</td>
              <td><span class="route-pill" :style="{ background: routeColor(f.route)+'22', color: routeColor(f.route) }">{{ f.route }}</span></td>
              <td>
                <span class="status-pill" :class="'status-pill--'+f.status">
                  {{ f.status?.replace(/_/g,' ') }}
                </span>
              </td>
              <td class="dim">{{ fmtSize(f.file_size) }}</td>
              <td class="dim nowrap">{{ fmtDate(f.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Duplicates tab -->
    <div v-else-if="activeTab === 'duplicates'">
      <div v-if="!duplicates.length" class="state-msg dim">No duplicate groups found.</div>
      <div v-else v-for="(group, i) in duplicates" :key="i" class="dup-group">
        <div class="dup-group__header">Duplicate group {{ i+1 }} · {{ group.files?.length || 2 }} files · hash: <span class="mono">{{ group.hash || group.file_hash }}</span></div>
        <div v-for="f in (group.files || [])" :key="f.id" class="dup-row">
          <span>{{ f.original_name }}</span>
          <span class="dim">{{ f.case_number }}</span>
          <span class="dim">{{ fmtDate(f.created_at) }}</span>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped>
.disc { padding: 2rem; max-width: 1200px; }
.disc__header { margin-bottom: 1.5rem; display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
.upload-btn { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1rem; white-space: nowrap; transition: opacity .15s; }
.upload-btn:hover { opacity: 0.85; }
.disc__title  { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.disc__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }

.stats-grid { display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.25rem; min-width: 100px; }
.stat-card__val   { font-size: 1.5rem; font-weight: 700; color: var(--text-primary); }
.stat-card__label { color: var(--text-muted); font-size: 0.75rem; margin-top: 0.2rem; text-transform: capitalize; }

.pipeline { display: grid; gap: 0.75rem; grid-template-columns: repeat(auto-fill, minmax(150px,1fr)); margin-bottom: 1.5rem; }
.pipeline-step { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 0.9rem; }
.pipeline-step__count { font-size: 1.4rem; font-weight: 700; margin-bottom: 0.2rem; }
.pipeline-step__label { color: var(--text-muted); font-size: 0.75rem; margin-bottom: 0.5rem; }
.pipeline-step__bar   { border-radius: 4px; height: 4px; overflow: hidden; }
.pipeline-step__fill  { height: 100%; border-radius: 4px; transition: width .5s; }

.tabs { display: flex; gap: 0.25rem; border-bottom: 1px solid var(--border); margin-bottom: 1.5rem; }
.tab  { background: none; border: none; border-bottom: 2px solid transparent; color: var(--text-muted); cursor: pointer; font-size: 0.875rem; padding: 0.6rem 1.1rem; transition: color .2s, border-color .2s; }
.tab:hover { color: var(--text-primary); }
.tab--active { color: var(--gold); border-bottom-color: var(--gold); }

.piq-table-wrap { border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; }
.piq-table { border-collapse: collapse; font-size: 0.875rem; width: 100%; }
.piq-table th { background: var(--bg-card); border-bottom: 1px solid var(--border); color: var(--text-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: 0.05em; padding: 0.65rem 0.9rem; text-align: left; text-transform: uppercase; }
.piq-table td { border-bottom: 1px solid var(--border); padding: 0.7rem 0.9rem; vertical-align: top; }
.piq-table tr:last-child td { border-bottom: none; }
.piq-table tr:hover td { background: rgba(255,255,255,.02); }

.filename    { color: var(--text-primary); font-size: 0.85rem; font-weight: 500; word-break: break-all; }
.route-pill  { border-radius: 4px; font-size: 0.72rem; font-weight: 600; padding: 0.2rem 0.5rem; text-transform: uppercase; }
.status-pill { border-radius: 4px; font-size: 0.72rem; font-weight: 600; padding: 0.2rem 0.5rem; white-space: nowrap; background: rgba(113,128,150,.2); color: #a0aec0; }
.status-pill--processed      { background: rgba(72,187,120,.15); color: #48bb78; }
.status-pill--text_extracted { background: rgba(74,124,247,.15); color: #4a7cf7; }
.status-pill--error          { background: rgba(252,129,129,.15); color: #fc8181; }

.dup-group { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 1rem; overflow: hidden; }
.dup-group__header { background: rgba(252,129,129,.08); border-bottom: 1px solid var(--border); color: var(--text-muted); font-size: 0.78rem; padding: 0.65rem 1rem; }
.dup-row { align-items: center; border-bottom: 1px solid var(--border); display: flex; font-size: 0.85rem; gap: 1.5rem; padding: 0.6rem 1rem; }
.dup-row:last-child { border-bottom: none; }

.dim    { color: var(--text-muted); }
.mono   { font-family: var(--font-mono); }
.nowrap { white-space: nowrap; }
.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
</style>
