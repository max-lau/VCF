<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'

const docs        = ref([])
const loading     = ref(true)
const cases       = ref([])
const assigning   = ref({})
const showAssign  = ref(null)
const caseQuery   = ref('')

async function fetchInbox() {
  loading.value = true
  try {
    const { data } = await client.get('/intake/inbox', { _silent: true })
    docs.value = data.documents || []
  } catch { docs.value = [] }
  finally { loading.value = false }
}

async function fetchCases() {
  try {
    const { data } = await client.get('/cases/search?limit=100', { _silent: true })
    cases.value = data.results || data.cases || []
  } catch { cases.value = [] }
}

const filteredCases = computed(() => {
  const q = caseQuery.value.toLowerCase()
  if (!q) return cases.value.slice(0, 20)
  return cases.value.filter(c =>
    (c.client_name || '').toLowerCase().includes(q) ||
    (c.case_number || '').toLowerCase().includes(q)
  ).slice(0, 20)
})

function openAssign(doc) {
  showAssign.value = doc.id
  caseQuery.value = (doc.identity_signals?.name || '')
  fetchCases()
}

function cancelAssign() {
  showAssign.value = null
  caseQuery.value = ''
}

async function assignDoc(doc, c) {
  assigning.value[doc.id] = true
  try {
    await client.post(`/intake/inbox/${doc.id}/assign`, { case_id: c.id })
    await fetchInbox()
    showAssign.value = null
  } catch (e) {
    alert('Assign failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    assigning.value[doc.id] = false
  }
}

async function autoAssign(doc) {
  assigning.value[doc.id] = true
  try {
    const { data } = await client.post(`/intake/inbox/${doc.id}/auto-assign`)
    if (data.success) await fetchInbox()
    else alert('Auto-assign failed')
  } catch (e) {
    alert('Auto-assign failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    assigning.value[doc.id] = false
  }
}

function reasonLabel(reason) {
  const map = {
    'name+dob': 'Name + DOB',
    'name+ssn': 'Name + SSN',
    'name_unique': 'Unique name match',
  }
  return map[reason] || (reason || 'Suggested match')
}

function docName(doc) {
  return doc.document_name || doc.filename || `Doc #${doc.id}`
}

function signalSummary(doc) {
  const s = doc.identity_signals || {}
  const parts = []
  if (s.name) parts.push(s.name)
  if (s.dob) parts.push(s.dob)
  if (s.ssn_last4) parts.push(`SSN ••••${s.ssn_last4}`)
  if (s.phone) parts.push(s.phone)
  return parts.length ? parts.join(' · ') : 'No identity signals extracted'
}

function fileLink(doc) {
  if (!doc.file_url) return null
  return `/intake/file/${doc.file_url}?token=${localStorage.getItem('paraiq_token') || ''}`
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

onMounted(() => {
  fetchInbox()
  fetchCases()
})
</script>

<template>
  <div class="inbox">
    <div class="inbox__header">
      <div>
        <h1 class="inbox__title">Document Inbox</h1>
        <p class="inbox__sub">Unmatched or ambiguous documents waiting for case assignment</p>
      </div>
      <button class="btn-gold" @click="fetchInbox" :disabled="loading">
        {{ loading ? 'Loading…' : '↻ Refresh' }}
      </button>
    </div>

    <div v-if="loading" class="state-msg">Loading inbox…</div>
    <div v-else-if="!docs.length" class="empty-tab">
      <div class="empty-tab__icon">📥</div>
      <div class="empty-tab__title">Inbox is empty</div>
      <div class="empty-tab__sub dim">All uploaded documents are matched to a case.</div>
    </div>

    <div v-else class="table-wrap">
      <table class="piq-table">
        <thead>
          <tr>
            <th>Document</th>
            <th>Type</th>
            <th>Identity Signals</th>
            <th>Received</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="doc in docs" :key="doc.id">
            <td class="doc-name">
              <span>{{ docName(doc) }}</span>
              <div v-if="doc.summary" class="doc-summary dim">{{ doc.summary.slice(0, 120) }}</div>
              <div v-if="doc.suggested_cases?.length" class="suggestions">
                <div class="suggestions__title">Suggested cases</div>
                <div v-for="s in doc.suggested_cases.slice(0, 3)" :key="s.case_id" class="suggestion">
                  <span class="suggestion__name">{{ s.client_name }}</span>
                  <span class="suggestion__num">{{ s.case_number }}</span>
                  <span class="suggestion__reason">{{ reasonLabel(s.reason) }}</span>
                  <button
                    class="btn-gold sm suggestion__accept"
                    :disabled="assigning[doc.id]"
                    @click.stop="autoAssign(doc)"
                  >Accept</button>
                </div>
              </div>
            </td>
            <td><span class="type-pill">{{ doc.doc_type || '—' }}</span></td>
            <td class="dim">{{ signalSummary(doc) }}</td>
            <td class="dim nowrap">{{ fmtDate(doc.created_at) }}</td>
            <td style="text-align:right">
              <a v-if="fileLink(doc)" :href="fileLink(doc)" target="_blank" class="binder-link sm">View</a>
              <button class="btn-gold sm" @click="openAssign(doc)">Assign</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Assign modal -->
    <Teleport to="body">
      <div v-if="showAssign" class="mod-overlay" @click.self="cancelAssign">
        <div class="mod-modal">
          <div class="mod-modal__header">
            <span>Assign document to case</span>
            <button class="mod-modal__close" @click="cancelAssign">✕</button>
          </div>
          <div class="mod-modal__body">
            <input v-model="caseQuery" class="piq-input w100" placeholder="Search by client name or case number…" />
            <div class="case-list">
              <div v-if="!filteredCases.length" class="dim sm">No cases found.</div>
              <button v-for="c in filteredCases" :key="c.id"
                      class="case-row"
                      :disabled="assigning[showAssign]"
                      @click="assignDoc(docs.find(d => d.id === showAssign), c)">
                <span class="case-row__name">{{ c.client_name }}</span>
                <span class="case-row__num">{{ c.case_number }}</span>
              </button>
            </div>
          </div>
          <div class="mod-modal__footer">
            <button class="btn-secondary" @click="cancelAssign">Cancel</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.inbox { padding: 2rem; max-width: 1100px; }
.inbox__header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem; }
.inbox__title  { font-family: var(--font-display); font-size: 1.5rem; margin: 0 0 0.25rem; }
.inbox__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0; }
.doc-summary   { font-size: 0.75rem; margin-top: 0.25rem; }
.case-list     { display: flex; flex-direction: column; gap: 0.4rem; max-height: 300px; overflow-y: auto; margin-top: 0.75rem; }
.case-row      { display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; padding: 0.6rem 0.8rem; cursor: pointer; text-align: left; }
.case-row:hover { border-color: var(--gold); }
.case-row:disabled { opacity: 0.5; cursor: not-allowed; }
.case-row__name { color: var(--text-primary); font-weight: 500; }
.case-row__num  { color: var(--text-muted); font-size: 0.8rem; font-family: var(--font-mono); }
.sm { font-size: 0.75rem; padding: 0.3rem 0.6rem; }
.suggestions { margin-top: 0.6rem; padding: 0.5rem 0.6rem; background: var(--bg-overlay, rgba(255,255,255,.03)); border: 1px solid var(--border-subtle); border-radius: 6px; }
.suggestions__title { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-tertiary); margin-bottom: 0.35rem; }
.suggestion { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; font-size: 0.8rem; padding: 0.25rem 0; }
.suggestion__name { color: var(--text-primary); font-weight: 500; }
.suggestion__num { color: var(--gold); font-family: var(--font-mono); }
.suggestion__reason { color: var(--text-tertiary); font-size: 0.7rem; }
.suggestion__accept { margin-left: auto; }
</style>
