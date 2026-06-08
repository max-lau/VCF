<template>
  <div class="cpa-root">
    <!-- Loading -->
    <div v-if="loading" class="cpa-loading">
      <div class="cpa-loading__spinner">⟳</div>
      <div>Loading your matter portal…</div>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="cpa-error">
      <div class="cpa-error__icon">🔒</div>
      <div class="cpa-error__title">Access Unavailable</div>
      <div class="cpa-error__msg">{{ error }}</div>
    </div>

    <!-- Portal content -->
    <template v-else-if="data">
      <!-- Header -->
      <div class="cpa-header">
        <div class="cpa-brand">
          <span class="cpa-brand__logo">ParaIQ</span>
          <span class="cpa-brand__tag">Client Portal</span>
        </div>
        <div class="cpa-header__meta">
          <span class="cpa-access-badge">🔐 Secure Access</span>
          <span class="cpa-expires" v-if="data.access?.expires_at">
            Expires {{ fmtDate(data.access.expires_at) }}
          </span>
        </div>
      </div>

      <!-- Matter card -->
      <div class="cpa-matter">
        <div class="cpa-matter__label">Your Matter</div>
        <h1 class="cpa-matter__title">{{ data.matter?.client_name || 'Matter' }}</h1>
        <div class="cpa-matter__meta">
          <span class="cpa-chip">{{ data.matter?.case_number }}</span>
          <span class="cpa-chip" :class="`cpa-chip--${data.matter?.status}`">{{ data.matter?.status }}</span>
          <span class="cpa-chip dim">Opened {{ fmtDate(data.matter?.created_at) }}</span>
        </div>
        <div class="cpa-matter__greeting">
          Hello, <strong>{{ data.access?.client_name }}</strong>. Here is a read-only view of your matter.
        </div>
      </div>

      <!-- Tabs -->
      <div class="cpa-tabs">
        <button v-for="tab in availableTabs" :key="tab.key"
          :class="['cpa-tab', { active: activeTab === tab.key }]"
          @click="activeTab = tab.key">
          {{ tab.icon }} {{ tab.label }}
        </button>
      </div>

      <!-- Documents tab -->
      <div v-if="activeTab === 'documents'" class="cpa-section">
        <div v-if="!data.documents?.length" class="cpa-empty">No documents available yet.</div>
        <div v-else class="cpa-table-wrap">
          <table class="cpa-table">
            <thead>
              <tr><th>Document</th><th>Type</th><th>Uploaded</th></tr>
            </thead>
            <tbody>
              <tr v-for="d in data.documents" :key="d.id">
                <td>{{ d.document_name }}</td>
                <td><span class="cpa-chip">{{ d.source }}</span></td>
                <td class="dim">{{ fmtDate(d.upload_date) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Timeline tab -->
      <div v-if="activeTab === 'timeline'" class="cpa-section">
        <div v-if="!data.timeline?.length" class="cpa-empty">No timeline events yet.</div>
        <div v-else class="cpa-timeline">
          <div v-for="(ev, i) in data.timeline" :key="i" class="cpa-tl-item">
            <div class="cpa-tl-dot" :class="`dot-${ev.significance || 'low'}`"></div>
            <div class="cpa-tl-body">
              <div class="cpa-tl-date dim">{{ ev.date }}</div>
              <div class="cpa-tl-event">{{ ev.event }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Correspondence tab -->
      <div v-if="activeTab === 'correspondence'" class="cpa-section">
        <div v-if="!data.correspondence?.length" class="cpa-empty">No correspondence yet.</div>
        <div v-else class="cpa-table-wrap">
          <table class="cpa-table">
            <thead>
              <tr><th>Subject</th><th>Direction</th><th>Date</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in data.correspondence" :key="c.id">
                <td>{{ c.subject || '—' }}</td>
                <td><span class="cpa-chip" :class="`cpa-chip--${c.direction}`">{{ c.direction }}</span></td>
                <td class="dim">{{ fmtDate(c.date) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Footer -->
      <div class="cpa-footer">
        <div>This is a secure, read-only view of your matter. For questions, contact your attorney.</div>
        <div class="dim">Powered by ParaIQ Legal Intelligence</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'

const route   = useRoute()
const loading = ref(true)
const error   = ref(null)
const data    = ref(null)
const activeTab = ref('documents')

const TABS = [
  { key: 'documents',      label: 'Documents',      icon: '📄' },
  { key: 'timeline',       label: 'Timeline',       icon: '📅' },
  { key: 'correspondence', label: 'Correspondence', icon: '✉️' },
]

const availableTabs = computed(() => {
  if (!data.value?.access?.permissions) return TABS
  const perms = data.value.access.permissions.split(',')
  return TABS.filter(t => perms.includes(t.key))
})

async function loadPortal() {
  loading.value = true
  error.value   = null
  try {
    const { data: d } = await axios.get(`/api/client-portal/view/${route.params.token}`)
    data.value = d
    // Set first available tab
    if (availableTabs.value.length) {
      activeTab.value = availableTabs.value[0].key
    }
  } catch (e) {
    error.value = e?.response?.data?.detail || 'This portal link is invalid or has expired.'
  } finally {
    loading.value = false
  }
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
}

onMounted(loadPortal)
</script>

<style scoped>
.cpa-root {
  min-height: 100vh;
  background: #0a0a14;
  color: #e2e8f0;
  font-family: 'IBM Plex Sans', system-ui, sans-serif;
  padding: 0;
}

/* Loading / Error */
.cpa-loading, .cpa-error {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 1rem; min-height: 100vh;
  color: #64748b; font-size: 0.9rem;
}
.cpa-loading__spinner { font-size: 2rem; animation: spin 1s linear infinite; }
@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
.cpa-error__icon  { font-size: 3rem; }
.cpa-error__title { font-size: 1.25rem; font-weight: 600; color: #e2e8f0; }
.cpa-error__msg   { color: #64748b; max-width: 360px; text-align: center; }

/* Header */
.cpa-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 1rem 2rem;
  border-bottom: 1px solid #1e2530;
  background: #0d1117;
}
.cpa-brand__logo { font-family: 'Crimson Pro', Georgia, serif; font-size: 1.4rem; color: #c89b3c; letter-spacing: 0.06em; }
.cpa-brand__tag  { font-size: 0.7rem; color: #64748b; margin-left: 8px; text-transform: uppercase; letter-spacing: 0.08em; }
.cpa-header__meta { display: flex; align-items: center; gap: 1rem; font-size: 0.78rem; }
.cpa-access-badge { background: rgba(72,187,120,0.12); border: 1px solid rgba(72,187,120,0.3); border-radius: 4px; color: #48bb78; padding: 2px 8px; font-size: 0.72rem; }
.cpa-expires { color: #64748b; }

/* Matter card */
.cpa-matter {
  padding: 2rem;
  border-bottom: 1px solid #1e2530;
  background: linear-gradient(135deg, rgba(201,168,76,0.04) 0%, transparent 60%);
}
.cpa-matter__label { font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.5rem; }
.cpa-matter__title { font-family: 'Crimson Pro', Georgia, serif; font-size: 1.8rem; font-weight: 400; color: #c89b3c; margin: 0 0 0.75rem; }
.cpa-matter__meta  { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
.cpa-matter__greeting { font-size: 0.875rem; color: #94a3b8; line-height: 1.6; }

/* Chips */
.cpa-chip { background: rgba(255,255,255,0.06); border: 1px solid #1e2530; border-radius: 4px; font-size: 0.72rem; padding: 2px 8px; color: #94a3b8; }
.cpa-chip--open    { background: rgba(74,124,247,0.12); border-color: rgba(74,124,247,0.3); color: #4a7cf7; }
.cpa-chip--inbound { background: rgba(72,187,120,0.12); border-color: rgba(72,187,120,0.3); color: #48bb78; }
.cpa-chip--outbound{ background: rgba(74,124,247,0.12); border-color: rgba(74,124,247,0.3); color: #4a7cf7; }

/* Tabs */
.cpa-tabs { display: flex; gap: 0.25rem; padding: 0 2rem; border-bottom: 1px solid #1e2530; background: #0d1117; }
.cpa-tab  { background: none; border: none; border-bottom: 2px solid transparent; color: #64748b; cursor: pointer; font-family: inherit; font-size: 0.875rem; padding: 0.75rem 1rem; transition: all .15s; }
.cpa-tab:hover  { color: #e2e8f0; }
.cpa-tab.active { border-bottom-color: #c89b3c; color: #c89b3c; }

/* Sections */
.cpa-section { padding: 1.5rem 2rem; max-width: 860px; }
.cpa-empty { color: #64748b; font-size: 0.875rem; padding: 2rem 0; text-align: center; }

/* Table */
.cpa-table-wrap { border: 1px solid #1e2530; border-radius: 8px; overflow: hidden; }
.cpa-table { border-collapse: collapse; width: 100%; font-size: 0.875rem; }
.cpa-table th { background: #0d1117; border-bottom: 1px solid #1e2530; color: #64748b; font-size: 0.68rem; font-weight: 600; letter-spacing: 0.05em; padding: 0.65rem 1rem; text-align: left; text-transform: uppercase; }
.cpa-table td { border-bottom: 1px solid #1e2530; padding: 0.7rem 1rem; }
.cpa-table tr:last-child td { border-bottom: none; }
.cpa-table tr:hover td { background: rgba(255,255,255,0.02); }

/* Timeline */
.cpa-timeline { display: flex; flex-direction: column; gap: 0; }
.cpa-tl-item  { display: flex; gap: 1rem; }
.cpa-tl-dot   { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; }
.dot-high   { background: #fc8181; }
.dot-medium { background: #ecc94b; }
.dot-low    { background: #718096; }
.cpa-tl-body  { padding-bottom: 1.25rem; flex: 1; }
.cpa-tl-date  { font-size: 0.75rem; margin-bottom: 0.2rem; }
.cpa-tl-event { font-size: 0.875rem; color: #e2e8f0; line-height: 1.5; }

/* Footer */
.cpa-footer {
  padding: 1.5rem 2rem;
  border-top: 1px solid #1e2530;
  font-size: 0.75rem;
  color: #475569;
  display: flex; flex-direction: column; gap: 0.3rem;
  margin-top: 2rem;
}

.dim { color: #64748b; }

@media (max-width: 640px) {
  .cpa-header { padding: 0.75rem 1rem; }
  .cpa-matter { padding: 1.25rem 1rem; }
  .cpa-section { padding: 1rem; }
  .cpa-matter__title { font-size: 1.4rem; }
  .cpa-header__meta .cpa-expires { display: none; }
}
</style>
