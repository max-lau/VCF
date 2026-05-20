<script setup>
import { ref, onMounted } from 'vue'
import client from '@/api/client'

const entries  = ref([])
const loading  = ref(false)
const page     = ref(1)
const perPage  = 50
const total    = ref(0)
const filterAction = ref('')
const filterUser   = ref('')
const search       = ref('')

const ACTIONS = ['login','logout','create','update','delete','view','export','upload','download']

async function fetchAudit() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('limit', perPage)
    params.set('offset', (page.value - 1) * perPage)
    if (filterAction.value) params.set('action', filterAction.value)
    if (filterUser.value)   params.set('user_id', filterUser.value)
    if (search.value)       params.set('search', search.value)
    const { data } = await client.get(`/audit/logs?${params}`)
    entries.value = Array.isArray(data) ? data : (data.entries || data.logs || [])
    total.value   = data.total || entries.value.length
  } catch {
    entries.value = []
  } finally { loading.value = false }
}

let searchTimer = null
function onSearch() { clearTimeout(searchTimer); searchTimer = setTimeout(fetchAudit, 300) }

function prevPage() { if (page.value > 1) { page.value--; fetchAudit() } }
function nextPage() { if (entries.value.length === perPage) { page.value++; fetchAudit() } }

function actionColor(a) {
  return { login:'#48bb78', logout:'#718096', create:'#4a7cf7', update:'#ecc94b', delete:'#fc8181', view:'#718096', export:'#9f7aea', upload:'#4a7cf7', download:'#9f7aea' }[a] || '#718096'
}
function actionIcon(a) {
  return { login:'🔑', logout:'🚪', create:'✚', update:'✎', delete:'✕', view:'👁', export:'↓', upload:'↑', download:'↓' }[a] || '◎'
}
function fmtDate(d) {
  return d ? new Date(d).toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '—'
}

onMounted(fetchAudit)
</script>

<template>
  <div class="audit">
    <div class="audit__header">
      <div><h1 class="audit__title">Audit Log</h1><p class="audit__sub">User activity · data access · system events</p></div>
      <button class="btn-secondary" @click="fetchAudit">↻ Refresh</button>
    </div>

    <div class="filter-bar">
      <input class="search-input" v-model="search" @input="onSearch" placeholder="Search user, resource, details…" />
      <select class="bar-select sm" v-model="filterAction" @change="page=1; fetchAudit()">
        <option value="">All actions</option>
        <option v-for="a in ACTIONS" :key="a" :value="a">{{ a }}</option>
      </select>
    </div>

    <div v-if="loading" class="state-msg">Loading…</div>

    <div v-else-if="!entries.length" class="empty">
      <div class="empty__icon">📋</div>
      <div class="empty__title">No audit entries found</div>
      <div class="empty__sub">User activity is logged here as the platform is used.</div>
    </div>

    <div v-else>
      <div class="audit-table-wrap">
        <table class="audit-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>User</th>
              <th>Action</th>
              <th>Resource</th>
              <th>Details</th>
              <th>IP</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in entries" :key="e.id">
              <td class="dim nowrap">{{ fmtDate(e.created_at || e.timestamp) }}</td>
              <td class="user-cell">
                <span class="user-avatar">{{ (e.username || e.user || 'S').charAt(0).toUpperCase() }}</span>
                {{ e.username || e.user || 'System' }}
              </td>
              <td>
                <span class="action-pill" :style="{ background: actionColor(e.action)+'22', color: actionColor(e.action) }">
                  {{ actionIcon(e.action) }} {{ e.action }}
                </span>
              </td>
              <td class="dim">{{ e.resource_type || e.table_name || '—' }} {{ e.resource_id ? '#'+e.resource_id : '' }}</td>
              <td class="detail-cell dim">{{ e.details || e.description || e.message || '—' }}</td>
              <td class="dim mono sm">{{ e.ip_address || e.ip || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pagination">
        <button class="btn-secondary sm" @click="prevPage" :disabled="page === 1">← Prev</button>
        <span class="dim sm">Page {{ page }}</span>
        <button class="btn-secondary sm" @click="nextPage" :disabled="entries.length < perPage">Next →</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.audit { padding: 2rem; max-width: 1200px; }
.audit__header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.25rem; }
.audit__title  { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.audit__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.filter-bar    { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.25rem; flex-wrap: wrap; }
.search-input  { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; outline: none; padding: 0.4rem 0.75rem; flex: 1; max-width: 340px; }
.search-input:focus { border-color: var(--gold); }
.bar-select.sm { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; padding: 0.4rem 0.75rem; max-width: 160px; }
.audit-table-wrap { border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; }
.audit-table { border-collapse: collapse; font-size: 0.85rem; width: 100%; }
.audit-table th { background: var(--bg-card); border-bottom: 1px solid var(--border); color: var(--text-muted); font-size: 0.7rem; font-weight: 600; letter-spacing: .05em; padding: 0.65rem 0.9rem; text-align: left; text-transform: uppercase; white-space: nowrap; }
.audit-table td { border-bottom: 1px solid var(--border); padding: 0.65rem 0.9rem; vertical-align: middle; }
.audit-table tr:last-child td { border-bottom: none; }
.audit-table tr:hover td { background: rgba(255,255,255,.02); }
.user-cell  { display: flex; align-items: center; gap: 0.5rem; white-space: nowrap; }
.user-avatar { align-items: center; background: rgba(201,168,76,.2); border-radius: 50%; color: var(--gold); display: inline-flex; font-size: 0.65rem; font-weight: 700; height: 22px; justify-content: center; width: 22px; flex-shrink: 0; }
.action-pill { border-radius: 4px; font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.45rem; white-space: nowrap; }
.detail-cell { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pagination { display: flex; align-items: center; gap: 1rem; justify-content: center; margin-top: 1.25rem; }
.nowrap { white-space: nowrap; }
.empty { text-align: center; padding: 4rem 2rem; }
.empty__icon  { font-size: 2.5rem; opacity: .3; margin-bottom: 1rem; }
.empty__title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; }
.empty__sub   { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.4rem; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; transition: all .15s; }
.btn-secondary:hover:not(:disabled) { background: var(--bg-raised); color: var(--text-primary); }
.btn-secondary:disabled { opacity: .4; cursor: not-allowed; }
.btn-secondary.sm { font-size: 0.78rem; padding: 0.35rem 0.75rem; }
.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
.mono { font-family: var(--font-mono); }
.sm  { font-size: 0.78rem; }
.dim { color: var(--text-muted); }
</style>
