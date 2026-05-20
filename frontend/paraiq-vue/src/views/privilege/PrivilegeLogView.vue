<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const token   = () => localStorage.getItem('paraiq_token')
const authHdr = () => ({ Authorization: 'Bearer ' + token() })

// ── State ─────────────────────────────────────────────────────────────────────
const entries      = ref([])
const stats        = ref(null)
const loading      = ref(true)
const total        = ref(0)
const search       = ref('')
const filterType   = ref('')
const filterCase   = ref('')
const page         = ref(0)
const PAGE_SIZE    = 50

const PRIV_TYPES = [
  'Attorney-Client Privilege',
  'Work Product Doctrine',
  'Both',
  'Common Interest Privilege',
]

// ── Fetch ─────────────────────────────────────────────────────────────────────
async function fetchStats() {
  try {
    const { data } = await axios.get('/privilege/stats', { headers: authHdr() })
    stats.value = data
  } catch { stats.value = null }
}

async function fetchEntries() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      limit:  PAGE_SIZE,
      offset: page.value * PAGE_SIZE,
    })
    if (filterCase.value)  params.append('case_number',    filterCase.value)
    if (filterType.value)  params.append('privilege_type', filterType.value)
    const { data } = await axios.get('/privilege/log?' + params, { headers: authHdr() })
    entries.value = data.entries || []
    total.value   = data.total   || 0
  } catch {
    entries.value = []
  } finally {
    loading.value = false
  }
}

async function refresh() {
  page.value = 0
  await Promise.all([fetchStats(), fetchEntries()])
}

// ── Computed ──────────────────────────────────────────────────────────────────
const filteredEntries = computed(() => {
  if (!search.value) return entries.value
  const q = search.value.toLowerCase()
  return entries.value.filter(e =>
    e.filename?.toLowerCase().includes(q) ||
    e.case_number?.toLowerCase().includes(q) ||
    e.author?.toLowerCase().includes(q) ||
    e.basis?.toLowerCase().includes(q)
  )
})

const totalPages = computed(() => Math.ceil(total.value / PAGE_SIZE))

function prevPage() { if (page.value > 0) { page.value--; fetchEntries() } }
function nextPage() { if (page.value < totalPages.value - 1) { page.value++; fetchEntries() } }

function typeColor(t) {
  if (t === 'Attorney-Client Privilege') return '#4a7cf7'
  if (t === 'Work Product Doctrine')     return '#48bb78'
  if (t === 'Both')                      return '#c9a84c'
  return '#a0aec0'
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

onMounted(refresh)
</script>

<template>
  <div class="priv">

    <!-- Header -->
    <div class="priv__header">
      <div>
        <h1 class="priv__title">Privilege Log</h1>
        <p class="priv__sub">Attorney-client and work product protected documents</p>
      </div>
    </div>

    <!-- Stats bar -->
    <div v-if="stats" class="stats-bar">
      <div class="stat-card">
        <div class="stat-card__val">{{ stats.total }}</div>
        <div class="stat-card__label">Total Entries</div>
      </div>
      <div v-for="t in stats.by_type" :key="t.privilege_type" class="stat-card">
        <div class="stat-card__val" :style="{ color: typeColor(t.privilege_type) }">{{ t.count }}</div>
        <div class="stat-card__label">{{ t.privilege_type }}</div>
      </div>
    </div>

    <!-- Filters -->
    <div class="filters">
      <input v-model="search"      class="piq-input" placeholder="Search filename, author, basis…" style="max-width:300px" />
      <input v-model="filterCase"  class="piq-input" placeholder="Filter by case #" style="max-width:160px"
             @change="refresh" />
      <select v-model="filterType" class="piq-input" style="max-width:220px" @change="refresh">
        <option value="">All privilege types</option>
        <option v-for="t in PRIV_TYPES" :key="t" :value="t">{{ t }}</option>
      </select>
      <button class="action-btn" @click="refresh">Refresh</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="state-msg">Loading privilege log…</div>

    <!-- Empty state -->
    <div v-else-if="!filteredEntries.length" class="empty-state">
      <div class="empty-state__icon">◈</div>
      <div class="empty-state__title">No privilege log entries yet</div>
      <div class="empty-state__sub">
        Upload documents through Discovery Intake and run privilege detection to populate this log.
      </div>
    </div>

    <!-- Table -->
    <template v-else>
      <div class="piq-table-wrap">
        <table class="piq-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Document</th>
              <th>Case</th>
              <th>Date</th>
              <th>Author</th>
              <th>Recipients</th>
              <th>Privilege Type</th>
              <th>Basis</th>
              <th>Withheld</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in filteredEntries" :key="e.id">
              <td class="dim mono">{{ e.id }}</td>
              <td>
                <span class="filename">{{ e.filename }}</span>
              </td>
              <td class="dim mono">{{ e.case_number }}</td>
              <td class="dim nowrap">{{ formatDate(e.doc_date) }}</td>
              <td class="dim">{{ e.author || '—' }}</td>
              <td class="dim">{{ e.recipients || '—' }}</td>
              <td>
                <span class="type-pill" :style="{ background: typeColor(e.privilege_type) + '22', color: typeColor(e.privilege_type) }">
                  {{ e.privilege_type }}
                </span>
              </td>
              <td class="basis-cell dim">{{ e.basis }}</td>
              <td class="dim nowrap">{{ formatDate(e.withheld_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="pagination">
        <button class="action-btn" :disabled="page === 0" @click="prevPage">← Prev</button>
        <span class="dim">Page {{ page + 1 }} of {{ totalPages }} · {{ total }} entries</span>
        <button class="action-btn" :disabled="page >= totalPages - 1" @click="nextPage">Next →</button>
      </div>
    </template>

  </div>
</template>

<style scoped>
.priv            { padding: 2rem; max-width: 1400px; }
.priv__header    { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem; }
.priv__title     { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.priv__sub       { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }

/* Stats bar */
.stats-bar { display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.25rem; min-width: 120px; }
.stat-card__val   { font-size: 1.5rem; font-weight: 700; color: var(--text-primary); }
.stat-card__label { color: var(--text-muted); font-size: 0.75rem; margin-top: 0.2rem; }

/* Filters */
.filters { display: flex; gap: 0.75rem; margin-bottom: 1rem; flex-wrap: wrap; align-items: center; }

/* Table */
.piq-table-wrap { border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; }
.piq-table      { border-collapse: collapse; font-size: 0.85rem; width: 100%; }
.piq-table th   {
  background: var(--bg-card); border-bottom: 1px solid var(--border);
  color: var(--text-muted); font-size: 0.72rem; font-weight: 600;
  letter-spacing: 0.05em; padding: 0.65rem 0.9rem; text-align: left; text-transform: uppercase;
}
.piq-table td          { border-bottom: 1px solid var(--border); padding: 0.75rem 0.9rem; vertical-align: top; }
.piq-table tr:last-child td { border-bottom: none; }
.piq-table tr:hover td { background: rgba(255,255,255,.02); }

.filename   { color: var(--text-primary); font-weight: 500; font-size: 0.82rem; }
.type-pill  { border-radius: 4px; font-size: 0.72rem; font-weight: 600; padding: 0.2rem 0.5rem; white-space: nowrap; }
.basis-cell { font-size: 0.78rem; max-width: 280px; line-height: 1.4; }

/* Pagination */
.pagination { align-items: center; display: flex; gap: 1rem; justify-content: center; margin-top: 1.25rem; }

/* Empty state */
.empty-state       { padding: 4rem 2rem; text-align: center; }
.empty-state__icon { color: var(--gold); font-size: 2.5rem; margin-bottom: 1rem; opacity: 0.4; }
.empty-state__title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; margin-bottom: 0.5rem; }
.empty-state__sub  { color: var(--text-muted); font-size: 0.875rem; max-width: 400px; margin: 0 auto; line-height: 1.5; }

/* Action button */
.action-btn {
  background: none; border: 1px solid var(--border); border-radius: 4px;
  color: var(--text-muted); cursor: pointer; font-size: 0.78rem; padding: 0.4rem 0.8rem; transition: all .2s;
}
.action-btn:hover:not(:disabled) { border-color: var(--gold); color: var(--gold); }
.action-btn:disabled { cursor: not-allowed; opacity: 0.3; }

/* Utils */
.dim    { color: var(--text-muted); }
.mono   { font-family: var(--font-mono); }
.nowrap { white-space: nowrap; }
.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
</style>
