<script setup>
import '@/assets/module-shared.css'
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'
import DiscoveryUpload from '@/components/DiscoveryUpload.vue'


const items        = ref([])
const stats        = ref(null)
const loading      = ref(true)
const showForm     = ref(false)
const saving       = ref(false)
const formErr      = ref(null)
const search       = ref('')
const filterStatus = ref('')
const filterCase   = ref('')

const form = ref({
  case_number:'', title:'', motion_type:'', filed_date:'',
  hearing_date:'', status:'draft', notes:''
})

// ── Upload state ───────────────────────────────────────────────────────────
const showPicker       = ref(false)
const showUpload       = ref(false)
const uploadMatterId   = ref(0)
const uploadMatterName = ref('')
const uploadCaseNum    = ref('')
const matters          = ref([])
const mattersLoading   = ref(false)
const mattersError     = ref('')

// ── Data fetching ──────────────────────────────────────────────────────────
async function fetchAll() {
  loading.value = true
  try {
    const [iRes, sRes] = await Promise.all([
      client.get('/motions/'),
      client.get('/motions/stats'),
    ])
    items.value = iRes.data.motions || []
    stats.value = sRes.data
  } catch { items.value = [] }
  finally { loading.value = false }
}

async function save() {
  formErr.value = null
  saving.value  = true
  try {
    await client.post('/motions/', form.value)
    showForm.value = false
    form.value = { case_number:'', title:'', motion_type:'', filed_date:'', hearing_date:'', status:'draft', notes:'' }
    await fetchAll()
  } catch(e) {
    formErr.value = e.response?.data?.detail || 'Failed to save'
  } finally {
    saving.value = false
  }
}

async function remove(id) {
  if (!confirm('Delete this record?')) return
  await client.delete(`/motions/${id}`)
  await fetchAll()
}

// ── Upload flow ────────────────────────────────────────────────────────────
async function fetchMatters() {
  mattersLoading.value = true
  mattersError.value   = ''
  try {
    const { data } = await client.get(`/cases/search?q=&firm_id=${firmId()}`)
    matters.value = data.cases || []
  } catch {
    mattersError.value = 'Could not load matters.'
    matters.value = []
  } finally {
    mattersLoading.value = false
  }
}

function openPicker() {
  showPicker.value = true
  fetchMatters()
}

function selectMatter(m) {
  uploadMatterId.value   = m.id
  uploadMatterName.value = m.client_name || `Matter #${m.id}`
  uploadCaseNum.value    = m.case_number || ''
  showPicker.value       = false
  showUpload.value       = true
}

async function uploadForMotion(item) {
  try {
    const { data } = await client.get(
      `/cases/search?q=${encodeURIComponent(item.case_number)}&firm_id=${firmId()}`
    )
    const m = (data.cases || [])[0]
    uploadMatterId.value   = m?.id || 0
    uploadMatterName.value = m?.client_name || item.title
    uploadCaseNum.value    = m?.case_number || item.case_number
  } catch {
    uploadMatterId.value   = 0
    uploadMatterName.value = item.title
    uploadCaseNum.value    = item.case_number
  }
  showUpload.value = true
}

function onUploaded() {
  setTimeout(fetchAll, 1500)
}

// ── Computed ───────────────────────────────────────────────────────────────
const filtered = computed(() => items.value.filter(i => {
  const q      = search.value.toLowerCase()
  const matchQ = !q || JSON.stringify(i).toLowerCase().includes(q)
  const matchS = !filterStatus.value || i.status === filterStatus.value
  const matchC = !filterCase.value   || i.case_number === filterCase.value
  return matchQ && matchS && matchC
}))

const cases = computed(() => [...new Set(items.value.map(i => i.case_number))])

// ── Helpers ────────────────────────────────────────────────────────────────
function statusColor(s) {
  return {
    draft:'#718096', filed:'#9f7aea', pending:'#ecc94b',
    granted:'#48bb78', denied:'#fc8181', cancelled:'#fc8181'
  }[s] || '#a0aec0'
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' })
}

onMounted(fetchAll)
</script>

<template>
  <div class="mod">

    <!-- Header -->
    <div class="mod__header">
      <div>
        <h1 class="mod__title">Motions</h1>
        <p class="mod__sub">Court filings, hearings, and rulings</p>
      </div>
      <div class="header-actions">
        <button class="btn-upload" @click="openPicker">↑ Upload Filing</button>
        <button class="piq-btn-gold" @click="showForm = !showForm">+ New Motion</button>
      </div>
    </div>

    <!-- Stats -->
    <div v-if="stats" class="stats-bar">
      <div class="stat-card">
        <div class="stat-card__val">{{ stats.total }}</div>
        <div class="stat-card__label">Total</div>
      </div>
      <div v-for="(count, status) in stats.by_status" :key="status" class="stat-card">
        <div class="stat-card__val" :style="{ color: statusColor(status) }">{{ count }}</div>
        <div class="stat-card__label">{{ status }}</div>
      </div>
    </div>

    <!-- New form -->
    <div v-if="showForm" class="form-card">
      <h3 class="form-card__title">New Motion</h3>
      <div class="form-grid">
        <label>Case Number<input v-model="form.case_number" class="piq-input" placeholder="2026-CV-00142"/></label>
        <label>Title<input v-model="form.title" class="piq-input" placeholder="Motion to Dismiss"/></label>
        <label>Motion Type
          <select v-model="form.motion_type" class="piq-input">
            <option value="">Select type</option>
            <option>Motion to Dismiss</option>
            <option>Motion for Summary Judgment</option>
            <option>Motion in Limine</option>
            <option>Motion to Compel</option>
            <option>Motion for Sanctions</option>
            <option>Motion to Strike</option>
            <option>Other</option>
          </select>
        </label>
        <label>Filed Date<input v-model="form.filed_date" class="piq-input" type="date"/></label>
        <label>Hearing Date<input v-model="form.hearing_date" class="piq-input" type="date"/></label>
        <label>Status
          <select v-model="form.status" class="piq-input">
            <option>draft</option><option>filed</option><option>pending</option>
            <option>granted</option><option>denied</option>
          </select>
        </label>
        <label style="grid-column:1/-1">Notes<input v-model="form.notes" class="piq-input" placeholder="Notes…"/></label>
      </div>
      <div v-if="formErr" class="form-err">{{ formErr }}</div>
      <div class="form-actions">
        <button class="action-btn" @click="showForm = false">Cancel</button>
        <button class="piq-btn-gold" :disabled="saving" @click="save">
          {{ saving ? 'Saving…' : 'Save Motion' }}
        </button>
      </div>
    </div>

    <!-- Filters -->
    <div class="filters">
      <input v-model="search" class="piq-input" placeholder="Search…" style="max-width:240px"/>
      <select v-model="filterCase" class="piq-input" style="max-width:180px">
        <option value="">All cases</option>
        <option v-for="c in cases" :key="c" :value="c">{{ c }}</option>
      </select>
      <select v-model="filterStatus" class="piq-input" style="max-width:150px">
        <option value="">All statuses</option>
        <option value="draft">Draft</option>
        <option value="filed">Filed</option>
        <option value="pending">Pending</option>
        <option value="granted">Granted</option>
        <option value="denied">Denied</option>
      </select>
    </div>

    <div v-if="loading" class="state-msg">Loading…</div>

    <div v-else-if="!filtered.length" class="empty-state">
      <div class="empty-state__icon">◈</div>
      <div class="empty-state__title">No motions yet</div>
      <div class="empty-state__sub">Click "+ New Motion" to add the first one.</div>
    </div>

    <div v-else class="piq-table-wrap">
      <table class="piq-table">
        <thead>
          <tr>
            <th>ID</th><th>Title</th><th>Case</th><th>Type</th>
            <th>Filed</th><th>Hearing</th><th>Status</th><th>Filing</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in filtered" :key="item.id">
            <td class="dim mono">{{ item.id }}</td>
            <td class="bold">{{ item.title }}</td>
            <td class="dim mono">{{ item.case_number }}</td>
            <td class="dim">{{ item.motion_type || '—' }}</td>
            <td class="dim nowrap">{{ fmtDate(item.filed_date) }}</td>
            <td class="dim nowrap">{{ fmtDate(item.hearing_date) }}</td>
            <td>
              <span class="status-pill"
                :style="{ background: statusColor(item.status)+'22', color: statusColor(item.status) }">
                {{ item.status }}
              </span>
            </td>
            <td>
              <button class="action-btn" @click="uploadForMotion(item)">↑ Upload</button>
            </td>
            <td>
              <button class="action-btn action-btn--del" @click="remove(item.id)">✕</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Matter Picker Modal -->
    <Teleport to="body">
      <div v-if="showPicker" class="modal-overlay" @click.self="showPicker = false">
        <div class="picker-modal">
          <div class="picker-header">
            <div>
              <h2 class="picker-title">Select Matter</h2>
              <p class="picker-sub">Upload filing for which matter?</p>
            </div>
            <button class="close-btn" @click="showPicker = false">✕</button>
          </div>
          <div v-if="mattersLoading" class="picker-state">Loading matters…</div>
          <div v-else-if="mattersError" class="picker-state err">{{ mattersError }}</div>
          <div v-else-if="!matters.length" class="picker-state dim">No matters found.</div>
          <div v-else class="matter-list">
            <button v-for="m in matters" :key="m.id" class="matter-row" @click="selectMatter(m)">
              <div class="matter-row__left">
                <div class="matter-row__name">{{ m.client_name || `Matter #${m.id}` }}</div>
                <div class="matter-row__meta dim mono">{{ m.case_number }}</div>
              </div>
              <span class="matter-row__arrow">→</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Discovery Upload Modal -->
    <DiscoveryUpload
      :show="showUpload"
      :matter-id="uploadMatterId"
      :matter-name="uploadMatterName"
      :case-number="uploadCaseNum"
      @close="showUpload = false"
      @uploaded="onUploaded"
    />

  </div>
</template>

<style scoped>
/* module-specific overrides only */
</style>
