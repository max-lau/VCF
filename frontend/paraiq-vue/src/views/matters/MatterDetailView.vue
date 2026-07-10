<script setup>
import { ref, computed, onMounted, watch, onUnmounted} from "vue"
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import DiscoveryUpload from '@/components/DiscoveryUpload.vue'
import CaseKanban from '@/components/CaseKanban.vue'
import DraftingAssistant from '@/components/DraftingAssistant.vue'

const route  = useRoute()
const router = useRouter()
const caseId = computed(() => route.params.id)

const token   = () => localStorage.getItem('paraiq_token')
const authHdr = () => ({ Authorization: 'Bearer ' + token() })
const firmId  = () => localStorage.getItem('paraiq_firm_id') || 'default'

const matter      = ref(null)
const docs        = ref([])
const notes       = ref([])
const discoveryQ  = ref([])
const loading     = ref(true)
const loadingDisc = ref(false)
const activeTab   = ref('documents')
const showUpload     = ref(false)
const contacts       = ref([])
const correspondence = ref([])
const contracts      = ref([])
const motions        = ref([])
const calendarEvents = ref([])
const binderItems    = ref([])
const binderLoading  = ref(false)
const binderFilter   = ref('')
const loadingMod     = ref(false)
const timeline       = ref([])
const intelligence   = ref({ signals: [] })
const loadingTL      = ref(false)
const loadingIntel   = ref(false)
const modModal       = ref(false)
const modForm        = ref({})
const newNote     = ref('')
const savingNote  = ref(false)

const TABS = [
  { key: 'kanban', label: 'Kanban', icon: '⚖️' },
  { key: 'drafting', label: 'Drafting', icon: '✍️' },
  { key: 'documents',    label: 'Documents',    icon: '📄' },
  { key: 'discovery',    label: 'Discovery',    icon: '🔍' },
  { key: 'notes',        label: 'Notes',        icon: '📝' },
  { key: 'intelligence', label: 'Intelligence', icon: '🧠' },
  { key: 'timeline',       label: 'Timeline',       icon: '📅' },
  { key: 'contacts',       label: 'Contacts',       icon: '👤' },
  { key: 'correspondence', label: 'Correspondence', icon: '✉️'  },
  { key: 'contracts',      label: 'Contracts',      icon: '📋' },
  { key: 'motions',        label: 'Motions',        icon: '⚖️'  },
  { key: 'calendar',       label: 'Calendar',       icon: '🗓'  },
  { key: 'binder',         label: 'Binder',         icon: '🗂️'  },
  { key: 'docketing',      label: 'Docketing',      icon: '⚖️'  },
  { key: 'billing',        label: 'Billing',        icon: '💳'  },
]

const PIPELINE_COLORS = {
  pending:        '#718096',
  text_extracted: '#4a7cf7',
  ocr_complete:   '#9f7aea',
  processed:      '#48bb78',
  error:          '#fc8181',
}

async function fetchMatter() {
  loading.value = true
  try {
    const [cRes, dRes, nRes] = await Promise.all([
      axios.get(`/cases/${caseId.value}`,           { headers: authHdr() }),
      axios.get(`/cases/${caseId.value}/documents`, { headers: authHdr() }),
      axios.get(`/cases/${caseId.value}/notes`,     { headers: authHdr() }),
    ])
    matter.value = cRes.data
    docs.value   = dRes.data.documents || dRes.data.docs || []
    notes.value  = nRes.data.notes || []
  } catch {
    matter.value = null
  } finally {
    loading.value = false
  }
}

async function fetchDiscovery() {
  if (!matter.value?.case_number) return
  loadingDisc.value = true
  try {
    const { data } = await axios.get(
      `/discovery/queue?case_number=${encodeURIComponent(matter.value.case_number)}&limit=200`,
      { headers: authHdr() }
    )
    discoveryQ.value = data.files || []
  } catch { discoveryQ.value = [] }
  finally { loadingDisc.value = false }
}

const MOD_KEYS = ['contacts','correspondence','contracts','motions','calendar']

function switchTab(key) {
  activeTab.value = key
  modModal.value  = false
  if (key === 'discovery'    && !discoveryQ.value.length)          fetchDiscovery()
  if (key === 'timeline'     && !timeline.value.length)            fetchTimeline()
  if (key === 'intelligence' && !intelligence.value.signals?.length) fetchIntelligence()
  if (key === 'binder')                                            fetchBinder()
  if (MOD_KEYS.includes(key)) fetchModule(key)
}
async function fetchBinder() {
  binderLoading.value = true
  try {
    const { data } = await axios.get(`/cases/${caseId.value}/binder`, { headers: authHdr() })
    binderItems.value = data.items || []
  } catch { binderItems.value = [] }
  finally { binderLoading.value = false }
}
function binderTypeLabel(type) {
  return { email: '📧 Email', upload: '📄 Upload', ai_draft: '🤖 AI Draft', research: '🔬 Research' }[type] || type
}
const filteredBinderItems = computed(() =>
  binderFilter.value
    ? binderItems.value.filter(i => i.binder_type === binderFilter.value)
    : binderItems.value
)

async function fetchModule(key) {
  loadingMod.value = true
  try {
    const id = caseId.value
    const h  = { headers: authHdr() }
    let data = []
    if (key === 'contacts')       { const r = await axios.get(`/contacts/matter/${id}`, h);      data = Array.isArray(r.data) ? r.data : (r.data.contacts  || r.data.items || []) }
    if (key === 'correspondence') { const r = await axios.get(`/correspondence/${id}`, h);        data = Array.isArray(r.data) ? r.data : (r.data.items      || r.data.correspondence || []) }
    if (key === 'contracts')      { const r = await axios.get(`/contracts/?matter_id=${id}`, h);  data = Array.isArray(r.data) ? r.data : (r.data.contracts  || r.data.items || []) }
    if (key === 'motions')        { const r = await axios.get(`/motions/?matter_id=${id}`, h);    data = Array.isArray(r.data) ? r.data : (r.data.motions    || r.data.items || []) }
    if (key === 'calendar')       { const r = await axios.get(`/calendar/matter/${id}`, h);       data = Array.isArray(r.data) ? r.data : (r.data.events     || r.data.items || []) }
    if (key === 'contacts')       contacts.value       = data
    if (key === 'correspondence') correspondence.value = data
    if (key === 'contracts')      contracts.value      = data
    if (key === 'motions')        motions.value        = data
    if (key === 'calendar')       calendarEvents.value = data
  } catch(e) { console.error('fetchModule', key, e) } finally { loadingMod.value = false }
}

async function deleteModItem(key, id) {
  if (!confirm('Delete this item?')) return
  const urlMap = {
    contacts:       `/contacts/${id}`,
    correspondence: `/correspondence/${id}`,
    contracts:      `/contracts/${id}`,
    motions:        `/motions/${id}`,
    calendar:       `/calendar/${id}`,
  }
  try { await axios.delete(urlMap[key], { headers: authHdr() }) } catch(e) { console.error(e) }
  fetchModule(key)
}

function openAdd(defaults = {}) { modForm.value = { ...defaults }; modModal.value = true }

async function submitMod() {
  const key = activeTab.value
  const urlMap = {
    contacts:       '/contacts/',
    correspondence: '/correspondence/',
    contracts:      '/contracts/',
    motions:        '/motions/',
    calendar:       '/calendar/',
  }
  const payload = {
    ...modForm.value,
    matter_id: caseId.value,
    firm_id:   firmId(),
  }
  try {
    await axios.post(urlMap[key], payload, { headers: authHdr() })
    modModal.value = false
    fetchModule(key)
  } catch (e) { alert('Save failed: ' + (e?.response?.data?.detail || e.message)) }
}

async function addNote() {
  if (!newNote.value.trim() || savingNote.value) return
  savingNote.value = true
  try {
    await axios.post(
      `/cases/${caseId.value}/notes`,
      { content: newNote.value },
      { headers: authHdr() }
    )
    newNote.value = ''
    const { data } = await axios.get(`/cases/${caseId.value}/notes`, { headers: authHdr() })
    notes.value = data.notes || []
  } catch {} finally { savingNote.value = false }
}

function onUpload() { fetchMatter(); if (activeTab.value === 'discovery') fetchDiscovery() }

function riskColor(r)   { return { low:'#48bb78', medium:'#ecc94b', high:'#fc8181', unknown:'#718096' }[r] || '#718096' }
function statusColor(s) { return { open:'#4a7cf7', closed:'#718096', pending:'#ecc94b' }[s] || '#718096' }
function routeColor(r)  { return { digital:'#4a7cf7', ocr:'#48bb78', audio:'#c9a84c', zip:'#a0aec0', image:'#9f7aea' }[r] || '#718096' }

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' })
}
function fmtDateTime(d) {
  if (!d) return '—'
  return new Date(d).toLocaleString('en-US', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })
}
function fmtSize(b) {
  if (!b) return '—'
  return b < 1_048_576 ? (b/1024).toFixed(1)+' KB' : (b/1_048_576).toFixed(1)+' MB'
}

async function fetchTimeline() {
  loadingTL.value = true
  try {
    const { data } = await axios.get(`/cases/${caseId.value}/timeline`, { headers: authHdr() })
    timeline.value = data.timeline || []
  } catch { timeline.value = [] }
  finally { loadingTL.value = false }
}

async function fetchIntelligence() {
  loadingIntel.value = true
  try {
    const { data } = await axios.get(`/cases/${caseId.value}/intelligence`, { headers: authHdr() })
    intelligence.value = data
  } catch { intelligence.value = { signals: [] } }
  finally { loadingIntel.value = false }
}

onMounted(fetchMatter)

// ── Docketing ─────────────────────────────────────────────────────────────
const docketingChains      = ref([])
const docketingLoading     = ref(false)
const showServiceModal     = ref(false)
const docketingJurisdiction = ref('SDNY')
const docketingTriggerDate  = ref(new Date().toISOString().slice(0,10))
const selectedServiceMethod = ref('personal')
const docketingPreviews     = ref({})
const docketingDisclaimer   = ref('')
const docketingTriggering   = ref(false)

const SERVICE_METHODS = [
  { key: 'personal',    label: 'Personal Service',    warning: true  },
  { key: 'substituted', label: 'Substituted Service', warning: false },
  { key: 'mail',        label: 'Service by Mail',     warning: false },
  { key: 'waiver',      label: 'Waiver of Service',   warning: false },
]
const JURISDICTIONS = ['SDNY','EDNY','NYSCEF','NJ_SUPERIOR','MA_SUPERIOR']

async function fetchDocketing() {
  if (!matter.value?.id) return
  docketingLoading.value = true
  try {
    const res = await fetch(`/docketing/matter/${matter.value.id}`, {
      headers: authHdr()
    })
    if (!res.ok) throw new Error(res.status)
    const data = await res.json()
    docketingChains.value = data.chains || []
    docketingDisclaimer.value = data.disclaimer || ''
  } catch (e) {
    console.error('Docketing fetch failed:', e)
  } finally {
    docketingLoading.value = false
  }
}

async function openDocketingModal() {
  selectedServiceMethod.value = 'personal'
  docketingPreviews.value = {}
  await previewChain()
  showServiceModal.value = true
}

async function previewChain() {
  if (!docketingJurisdiction.value || !docketingTriggerDate.value) return
  try {
    const params = new URLSearchParams({
      matter_id: matter.value.id,
      jurisdiction: docketingJurisdiction.value,
      trigger_date: docketingTriggerDate.value,
      service_method: selectedServiceMethod.value,
    })
    const res = await fetch(`/docketing/preview?${params}`, {
      headers: authHdr()
    })
    if (!res.ok) throw new Error(res.status)
    const data = await res.json()
    docketingPreviews.value = data.previews || {}
    docketingDisclaimer.value = data.disclaimer || ''
  } catch (e) {
    console.error('Preview failed:', e)
  }
}

async function triggerDocketing() {
  if (!confirm('I confirm I have read and understood the disclaimer. Proceed to generate docketing chain?')) return
  docketingTriggering.value = true
  try {
    const res = await fetch('/docketing/trigger', {
      method: 'POST',
      headers: { ...authHdr(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        matter_id: matter.value.id,
        jurisdiction: docketingJurisdiction.value,
        trigger_event: 'complaint_filed',
        trigger_date: docketingTriggerDate.value,
        service_method: selectedServiceMethod.value,
      })
    })
    if (!res.ok) throw new Error(res.status)
    showServiceModal.value = false
    await fetchDocketing()
  } catch (e) {
    alert('Failed to generate chain: ' + e.message)
  } finally {
    docketingTriggering.value = false
  }
}

async function confirmDocketingEvent(eventId, confirmedDate, note) {
  const ack = confirm('I acknowledge: ' + docketingDisclaimer.value.slice(0, 120) + '... Confirm this deadline?')
  if (!ack) return
  try {
    const res = await fetch(`/docketing/events/${eventId}/confirm`, {
      method: 'POST',
      headers: { ...authHdr(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmed_date: confirmedDate || null, note: note || null, disclaimer_ack: true })
    })
    if (!res.ok) throw new Error(res.status)
    await fetchDocketing()
  } catch (e) {
    alert('Confirm failed: ' + e.message)
  }
}

function docketStatePill(state, postponed) {
  if (postponed) return { label: 'POSTPONED', cls: 'dock-pill--modified dock-pill--postponed' }
  const map = {
    pending:             { label: 'PENDING',   cls: 'dock-pill--pending' },
    confirmed:           { label: 'CONFIRMED', cls: 'dock-pill--confirmed' },
    modified:            { label: 'MODIFIED',  cls: 'dock-pill--modified' },
    overdue_unconfirmed: { label: 'OVERDUE!',  cls: 'dock-pill--overdue' },
  }
  return map[state] || { label: state, cls: '' }
}

function daysLapLabel(days) {
  if (!days || days < 1) return ''
  return `${days}d unconfirmed`
}

watch(() => activeTab.value, (tab) => {
  if (tab === 'docketing') fetchDocketing()
})


// ── Passive Time Capture — Heartbeat ─────────────────────────────────────
let _heartbeatInterval = null
let _currentActivityType = 'viewing'

function _sendHeartbeat() {
  if (!matter.value?.id) return
  fetch('/time/heartbeat', {
    method: 'POST',
    headers: { ...authHdr(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ matter_id: matter.value.id, activity_type: _currentActivityType })
  }).catch(() => {})
}

function _flushSessions() {
  if (!matter.value?.id) return
  fetch(`/time/flush/${matter.value.id}`, {
    method: 'POST',
    headers: authHdr()
  }).catch(() => {})
}

function _startHeartbeat() {
  _stopHeartbeat()
  _sendHeartbeat()
  _heartbeatInterval = setInterval(_sendHeartbeat, 30000)
}

function _stopHeartbeat() {
  if (_heartbeatInterval) {
    clearInterval(_heartbeatInterval)
    _heartbeatInterval = null
  }
}

// Update activity type based on active tab
watch(activeTab, (tab) => {
  const map = {
    drafting:       'drafting',
    documents:      'reviewing',
    discovery:      'research',
    research:       'research',
    correspondence: 'correspondence',
    binder:         'reviewing',
  }
  _currentActivityType = map[tab] || 'viewing'
})

onMounted(() => {
  _startHeartbeat()
})

onUnmounted(() => {
  _stopHeartbeat()
  _flushSessions()
})


// ── Billing Ledger ────────────────────────────────────────────────────────
const billingLedger  = ref(null)
const billingLoading = ref(false)

async function fetchBillingLedger() {
  if (!matter.value?.id) return
  billingLoading.value = true
  try {
    const res = await fetch(`/billing/matter/${matter.value.id}/ledger`, {
      headers: authHdr()
    })
    if (!res.ok) throw new Error(res.status)
    billingLedger.value = await res.json()
  } catch(e) {
    console.error('Billing ledger fetch failed:', e)
  } finally {
    billingLoading.value = false
  }
}

async function downloadInvoicePdf(invoiceId, invoiceNumber) {
  const res = await fetch(`/billing/invoices/${invoiceId}/pdf`, { headers: authHdr() })
  if (!res.ok) return alert('PDF generation failed')
  const blob = await res.blob()
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href = url; a.download = `invoice_${invoiceNumber}.pdf`; a.click()
  URL.revokeObjectURL(url)
}

async function previewInvoicePdf(invoiceId) {
  const res = await fetch(`/billing/invoices/${invoiceId}/pdf?inline=true`, { headers: authHdr() })
  if (!res.ok) return alert('PDF generation failed')
  const blob = await res.blob()
  const url  = URL.createObjectURL(blob)
  window.open(url, '_blank')
}

watch(() => activeTab.value, (tab) => {
  if (tab === 'billing') fetchBillingLedger()
})

</script>

<template>
  <div class="mdetail">

    <div class="breadcrumb">
      <button class="breadcrumb__back" @click="router.push('/matters')">← Matters</button>
      <span class="dim">/</span>
      <span class="dim sm">{{ matter?.client_name || '…' }}</span>
    </div>

    <div v-if="loading" class="state-msg">Loading matter…</div>
    <div v-else-if="!matter" class="state-msg">Matter not found.</div>

    <template v-else>

      <!-- Header card -->
      <div class="case-header">
        <div class="case-header__left">
          <div class="mono dim sm">{{ matter.case_number }}</div>
          <h1 class="case-header__title">{{ matter.client_name }}</h1>
          <div class="case-header__pills">
            <span class="risk-pill" :style="{ background: riskColor(matter.risk_level)+'22', color: riskColor(matter.risk_level) }">
              {{ matter.risk_level }} risk
            </span>
            <span class="status-pill" :style="{ background: statusColor(matter.status)+'22', color: statusColor(matter.status) }">
              {{ matter.status }}
            </span>
            <span v-if="matter.court"       class="meta-chip">⚖ {{ matter.court }}</span>
            <span v-if="matter.filing_date" class="meta-chip">Filed {{ fmtDate(matter.filing_date) }}</span>
          </div>
        </div>
        <div class="case-header__actions">
          <button class="btn-secondary" @click="router.push('/intelligence')">🧠 AI Analysis</button>
          <button class="btn-gold" @click="showUpload = true">↑ Upload</button>
        </div>
      </div>

      <!-- Meta grid -->
      <div class="meta-grid">
        <div class="meta-item" v-if="matter.matter_number">
          <div class="meta-item__label">Matter #</div>
          <div class="meta-item__val mono">{{ matter.matter_number }}</div>
        </div>
        <div class="meta-item">
          <div class="meta-item__label">Created</div>
          <div class="meta-item__val">{{ fmtDate(matter.created_at) }}</div>
        </div>
        <div class="meta-item">
          <div class="meta-item__label">Documents</div>
          <div class="meta-item__val">{{ docs.length }}</div>
        </div>
        <div class="meta-item">
          <div class="meta-item__label">Discovery</div>
          <div class="meta-item__val">{{ discoveryQ.length || '—' }}</div>
        </div>
        <div class="meta-item meta-item--wide" v-if="matter.description">
          <div class="meta-item__label">Description</div>
          <div class="meta-item__val">{{ matter.description }}</div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="tabs">
        <button v-for="t in TABS" :key="t.key"
          :class="['tab', { 'tab--active': activeTab === t.key }]"
          @click="switchTab(t.key)">
          {{ t.icon }} {{ t.label }}
          <span v-if="t.key==='documents' && docs.length"    class="tab-count">{{ docs.length }}</span>
          <span v-if="t.key==='notes'    && notes.length"    class="tab-count">{{ notes.length }}</span>
          <span v-if="t.key==='discovery'       && discoveryQ.length"    class="tab-count">{{ discoveryQ.length }}</span>
          <span v-if="t.key==='contacts'       && contacts.length"       class="tab-count">{{ contacts.length }}</span>
          <span v-if="t.key==='correspondence' && correspondence.length" class="tab-count">{{ correspondence.length }}</span>
          <span v-if="t.key==='contracts'      && contracts.length"      class="tab-count">{{ contracts.length }}</span>
          <span v-if="t.key==='motions'        && motions.length"        class="tab-count">{{ motions.length }}</span>
          <span v-if="t.key==='calendar'       && calendarEvents.length" class="tab-count">{{ calendarEvents.length }}</span>
          <span v-if="t.key==='binder'         && binderItems.length"   class="tab-count">{{ binderItems.length }}</span>
        </button>
      </div>
      <!-- Kanban -->
      <div v-if="activeTab === 'kanban'">
        <CaseKanban :case-id="caseId" />
      </div>

      <!-- Drafting -->
      <div v-if="activeTab === 'drafting'">
        <DraftingAssistant :case-id="caseId" />
      </div>



      <div v-if="activeTab === 'documents'">
        <div v-if="!docs.length" class="empty-tab">
          <div class="empty-tab__icon">📄</div>
          <div class="empty-tab__title">No documents yet</div>
          <button class="btn-gold sm" @click="showUpload = true">Upload Documents</button>
        </div>
        <div v-else>
          <div class="tab-toolbar">
            <span class="dim sm">{{ docs.length }} document{{ docs.length !== 1 ? 's' : '' }}</span>
            <button class="btn-gold sm" @click="showUpload = true">↑ Upload More</button>
          </div>
          <div class="table-wrap">
            <table class="piq-table">
              <thead>
                <tr><th>Filename</th><th>Type</th><th>Size</th><th>Uploaded</th><th>Status</th></tr>
              </thead>
              <tbody>
                <tr v-for="d in docs" :key="d.id">
                  <td class="doc-name">
                  <!-- WAW DEMO — TEMPORARY: linkify only the known WaW demo filenames.
                       Remove this v-if/v-else pair and restore the single line above
                       after the prospect demo — see WAW_DEMO_ROLLBACK.md -->
                  <a v-if="(d.document_name || '').match(/^(chen_weiming|krystyna_nowak)_/)"
                     :href="`/demo-files/${d.document_name}`"
                     target="_blank" rel="noopener">{{ d.document_name || d.original_filename || d.filename }}</a>
                  <span v-else>{{ d.document_name || d.original_filename || d.filename }}</span>
                </td>
                  <td><span class="type-pill">{{ d.doc_type || d.document_type || '—' }}</span></td>
                  <td class="dim">{{ fmtSize(d.file_size) }}</td>
                  <td class="dim nowrap">{{ fmtDate(d.upload_date || d.created_at) }}</td>
                  <td>
                    <span class="status-chip" :class="'s-'+(d.status||'processed')">
                      {{ d.status || 'processed' }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ── Discovery ── -->
      <div v-else-if="activeTab === 'discovery'">
        <div v-if="loadingDisc" class="state-msg">Loading discovery files…</div>
        <div v-else-if="!discoveryQ.length" class="empty-tab">
          <div class="empty-tab__icon">🔍</div>
          <div class="empty-tab__title">No discovery files for {{ matter.case_number }}</div>
          <div class="empty-tab__sub dim sm">
            Upload documents and they will appear here once processed.
          </div>
          <button class="btn-gold sm" @click="showUpload = true">↑ Upload Documents</button>
        </div>
        <div v-else>
          <!-- Pipeline summary -->
          <div class="pipeline-summary">
            <div v-for="(color, status) in PIPELINE_COLORS" :key="status" class="pipeline-chip">
              <span class="pipeline-chip__dot" :style="{ background: color }"></span>
              <span class="pipeline-chip__label dim sm">{{ status.replace('_',' ') }}</span>
              <span class="pipeline-chip__count" :style="{ color }">
                {{ discoveryQ.filter(f => f.status === status).length }}
              </span>
            </div>
          </div>
          <div class="tab-toolbar">
            <span class="dim sm">{{ discoveryQ.length }} file{{ discoveryQ.length !== 1 ? 's' : '' }}</span>
            <button class="btn-gold sm" @click="showUpload = true">↑ Upload More</button>
          </div>
          <div class="table-wrap">
            <table class="piq-table">
              <thead>
                <tr><th>Filename</th><th>Route</th><th>Status</th><th>Size</th><th>Ingested</th></tr>
              </thead>
              <tbody>
                <tr v-for="f in discoveryQ" :key="f.id">
                  <td class="doc-name">{{ f.original_name }}</td>
                  <td>
                    <span class="route-pill"
                      :style="{ background: routeColor(f.route)+'22', color: routeColor(f.route) }">
                      {{ f.route }}
                    </span>
                  </td>
                  <td>
                    <span class="status-chip" :class="'s-'+f.status">
                      {{ f.status?.replace(/_/g,' ') }}
                    </span>
                  </td>
                  <td class="dim">{{ fmtSize(f.file_size) }}</td>
                  <td class="dim nowrap">{{ fmtDateTime(f.created_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ── Notes ── -->
      <div v-else-if="activeTab === 'notes'" class="notes-pane">
        <div class="note-composer">
          <textarea v-model="newNote" class="note-input" placeholder="Add a case note…" rows="3"></textarea>
          <div style="display:flex;justify-content:flex-end">
            <button class="btn-gold sm" @click="addNote" :disabled="savingNote || !newNote.trim()">
              {{ savingNote ? 'Saving…' : '+ Add Note' }}
            </button>
          </div>
        </div>
        <div v-if="!notes.length" class="empty-tab" style="padding:2rem">
          <div class="empty-tab__icon">📝</div>
          <div class="empty-tab__title">No notes yet</div>
        </div>
        <div v-for="n in notes" :key="n.id" class="note-card">
          <div class="note-card__text">{{ n.content || n.note }}</div>
          <div class="note-card__meta dim sm">{{ n.author || n.username || 'You' }} · {{ fmtDate(n.created_at) }}</div>
        </div>
      </div>

      <!-- ── Intelligence ── -->
      <div v-else-if="activeTab === 'intelligence'" class="intel-pane">
        <div v-if="loadingIntel" class="state-msg">Loading intelligence…</div>
        <template v-else>
          <div class="tab-toolbar">
            <span class="dim sm">{{ intelligence.signals?.length || 0 }} signal{{ intelligence.signals?.length !== 1 ? 's' : '' }}</span>
            <button class="btn-gold sm" @click="fetchIntelligence">↻ Refresh</button>
          </div>
          <div v-if="!intelligence.signals?.length" class="empty-tab">
            <div class="empty-tab__icon">🧠</div>
            <div class="empty-tab__title">No signals yet</div>
            <div class="empty-tab__sub dim sm">Upload and extract documents to generate AI insights.</div>
          </div>
          <div v-else class="signal-list">
            <div v-for="(sig, i) in intelligence.signals" :key="i"
                 class="signal-card" :class="'signal-card--' + sig.severity">
              <div class="signal-card__header">
                <span class="sev-badge" :class="'sev-badge--' + sig.severity">{{ sig.severity }}</span>
                <span v-if="sig.ai" class="ai-badge">✦ AI</span>
                <span class="signal-card__title">{{ sig.title }}</span>
              </div>
              <div class="signal-card__desc">{{ sig.description }}</div>
            </div>
          </div>
        </template>
      </div>

      <!-- ── Timeline ── -->
      <div v-else-if="activeTab === 'timeline'" class="tl-pane">
        <div v-if="loadingTL" class="state-msg">Loading timeline…</div>
        <template v-else>
          <div class="tab-toolbar">
            <span class="dim sm">{{ timeline.length }} event{{ timeline.length !== 1 ? 's' : '' }}</span>
            <button class="btn-gold sm" @click="fetchTimeline">↻ Refresh</button>
          </div>
          <div v-if="!timeline.length" class="empty-tab">
            <div class="empty-tab__icon">📅</div>
            <div class="empty-tab__title">No timeline events yet</div>
            <div class="empty-tab__sub dim sm">Extract text from documents to populate the timeline.</div>
          </div>
          <div v-else class="tl-list">
            <div v-for="(ev, i) in timeline" :key="i" class="tl-item">
              <div class="tl-item__spine">
                <div class="tl-item__dot" :class="'dot-' + (ev.significance || 'low')"></div>
                <div v-if="i < timeline.length - 1" class="tl-item__line"></div>
              </div>
              <div class="tl-item__body">
                <div class="tl-item__date dim sm">{{ ev.date }}</div>
                <div class="tl-item__event">{{ ev.event || ev.context }}</div>
                <div class="tl-item__meta">
                  <span v-if="ev.source_doc" class="dim sm">📄 {{ ev.source_doc }}</span>
                  <span v-if="ev.parties?.length" class="dim sm"> · {{ ev.parties.join(', ') }}</span>
                  <span v-if="ev.significance" class="sig-chip" :class="'sig-chip--' + ev.significance">{{ ev.significance }}</span>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- ── Contacts ── -->
      <div v-else-if="activeTab === 'contacts'" class="mod-pane">
        <div class="tab-toolbar">
          <span class="dim sm">{{ contacts.length }} contact{{ contacts.length !== 1 ? 's' : '' }}</span>
          <button class="btn-gold sm" @click="openAdd({role:'Opposing Counsel'})">+ Add Contact</button>
        </div>
        <div v-if="loadingMod" class="state-msg">Loading…</div>
        <div v-else-if="!contacts.length" class="empty-tab"><div class="empty-tab__icon">👤</div><div class="empty-tab__title">No contacts yet</div></div>
        <div v-else class="table-wrap">
          <table class="piq-table">
            <thead><tr><th>Name</th><th>Role</th><th>Organization</th><th>Email</th><th>Phone</th><th></th></tr></thead>
            <tbody>
              <tr v-for="c in contacts" :key="c.id">
                <td class="doc-name">{{ c.name }}</td>
                <td><span class="type-pill">{{ c.role || '—' }}</span></td>
                <td class="dim">{{ c.organization || '—' }}</td>
                <td class="dim">{{ c.email || '—' }}</td>
                <td class="dim">{{ c.phone || '—' }}</td>
                <td><button class="del-btn" @click="deleteModItem('contacts', c.id)">✕</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── Correspondence ── -->
      <div v-else-if="activeTab === 'correspondence'" class="mod-pane">
        <div class="tab-toolbar">
          <span class="dim sm">{{ correspondence.length }} item{{ correspondence.length !== 1 ? 's' : '' }}</span>
          <button class="btn-gold sm" @click="openAdd({direction:'outbound'})">+ Add</button>
        </div>
        <div v-if="loadingMod" class="state-msg">Loading…</div>
        <div v-else-if="!correspondence.length" class="empty-tab"><div class="empty-tab__icon">✉️</div><div class="empty-tab__title">No correspondence yet</div></div>
        <div v-else class="table-wrap">
          <table class="piq-table">
            <thead><tr><th>Subject</th><th>Direction</th><th>Counterparty</th><th>Date</th><th></th></tr></thead>
            <tbody>
              <tr v-for="c in correspondence" :key="c.id">
                <td class="doc-name">{{ c.subject || '—' }}</td>
                <td><span class="type-pill" :class="c.direction==='inbound'?'pill-in':'pill-out'">{{ c.direction }}</span></td>
                <td class="dim">{{ c.counterparty || '—' }}</td>
                <td class="dim nowrap">{{ c.date ? fmtDate(c.date) : '—' }}</td>
                <td><button class="del-btn" @click="deleteModItem('correspondence', c.id)">✕</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── Contracts ── -->
      <div v-else-if="activeTab === 'contracts'" class="mod-pane">
        <div class="tab-toolbar">
          <span class="dim sm">{{ contracts.length }} contract{{ contracts.length !== 1 ? 's' : '' }}</span>
          <button class="btn-gold sm" @click="openAdd({status:'draft'})">+ Add Contract</button>
        </div>
        <div v-if="loadingMod" class="state-msg">Loading…</div>
        <div v-else-if="!contracts.length" class="empty-tab"><div class="empty-tab__icon">📋</div><div class="empty-tab__title">No contracts yet</div></div>
        <div v-else class="table-wrap">
          <table class="piq-table">
            <thead><tr><th>Title</th><th>Status</th><th>Executed</th><th>Expiry</th><th></th></tr></thead>
            <tbody>
              <tr v-for="c in contracts" :key="c.id">
                <td class="doc-name">{{ c.title }}</td>
                <td><span class="status-chip" :class="'s-'+c.status">{{ c.status }}</span></td>
                <td class="dim nowrap">{{ c.executed_at ? fmtDate(c.executed_at * 1000) : '—' }}</td>
                <td class="dim nowrap">{{ c.expiry_at   ? fmtDate(c.expiry_at   * 1000) : '—' }}</td>
                <td><button class="del-btn" @click="deleteModItem('contracts', c.id)">✕</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── Motions ── -->
      <div v-else-if="activeTab === 'motions'" class="mod-pane">
        <div class="tab-toolbar">
          <span class="dim sm">{{ motions.length }} motion{{ motions.length !== 1 ? 's' : '' }}</span>
          <button class="btn-gold sm" @click="openAdd({status:'draft'})">+ Add Motion</button>
        </div>
        <div v-if="loadingMod" class="state-msg">Loading…</div>
        <div v-else-if="!motions.length" class="empty-tab"><div class="empty-tab__icon">⚖️</div><div class="empty-tab__title">No motions yet</div></div>
        <div v-else class="table-wrap">
          <table class="piq-table">
            <thead><tr><th>Title</th><th>Status</th><th>Filed</th><th>Hearing</th><th>Ruling</th><th></th></tr></thead>
            <tbody>
              <tr v-for="m in motions" :key="m.id">
                <td class="doc-name">{{ m.title }}</td>
                <td><span class="status-chip" :class="'s-'+m.status">{{ m.status }}</span></td>
                <td class="dim nowrap">{{ m.filed_at   ? fmtDate(m.filed_at   * 1000) : '—' }}</td>
                <td class="dim nowrap">{{ m.hearing_at ? fmtDate(m.hearing_at * 1000) : '—' }}</td>
                <td class="dim">{{ m.ruling || '—' }}</td>
                <td><button class="del-btn" @click="deleteModItem('motions', m.id)">✕</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── Calendar ── -->
      <div v-else-if="activeTab === 'calendar'" class="mod-pane">
        <div class="tab-toolbar">
          <span class="dim sm">{{ calendarEvents.length }} event{{ calendarEvents.length !== 1 ? 's' : '' }}</span>
          <button class="btn-gold sm" @click="openAdd({event_type:'deadline', due_date: new Date().toISOString().slice(0,10)})">+ Add Event</button>
        </div>
        <div v-if="loadingMod" class="state-msg">Loading…</div>
        <div v-else-if="!calendarEvents.length" class="empty-tab"><div class="empty-tab__icon">🗓</div><div class="empty-tab__title">No events yet</div></div>
        <div v-else class="table-wrap">
          <table class="piq-table">
            <thead><tr><th>Title</th><th>Type</th><th>Date</th><th>Location</th><th></th></tr></thead>
            <tbody>
              <tr v-for="e in calendarEvents" :key="e.id">
                <td class="doc-name">{{ e.title }}</td>
                <td><span class="type-pill">{{ e.event_type }}</span></td>
                <td class="dim nowrap">{{ fmtDate(e.due_date) }}</td>
                <td class="dim">{{ e.location || '—' }}</td>
                <td><button class="del-btn" @click="deleteModItem('calendar', e.id)">✕</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── Docketing ── -->
      <div v-else-if="activeTab === 'docketing'" class="mod-pane">

        <!-- Service Method Modal -->
        <div v-if="showServiceModal" class="dock-modal-overlay">
          <div class="dock-modal">
            <div class="dock-modal__header">
              <span class="dock-modal__title">⚖️ Start Docketing Chain</span>
              <button class="dock-modal__close" @click="showServiceModal=false">✕</button>
            </div>

            <div class="dock-modal__row">
              <label class="dock-modal__label">Jurisdiction</label>
              <select v-model="docketingJurisdiction" class="piq-input" @change="previewChain">
                <option v-for="j in JURISDICTIONS" :key="j" :value="j">{{ j.replace('_',' ') }}</option>
              </select>
            </div>

            <div class="dock-modal__row">
              <label class="dock-modal__label">Complaint Filed / Trigger Date</label>
              <input type="date" v-model="docketingTriggerDate" class="piq-input" @change="previewChain" />
            </div>

            <div class="dock-modal__service-title">How was the complaint served?</div>
            <div class="dock-modal__service-subtitle">Select service method to calculate answer deadline</div>

            <div class="dock-modal__methods">
              <div v-for="m in SERVICE_METHODS" :key="m.key"
                class="dock-method-row"
                :class="{ 'dock-method-row--shortest': m.warning, 'dock-method-row--selected': selectedServiceMethod === m.key }"
                @click="selectedServiceMethod = m.key">
                <div class="dock-method-row__check">
                  <input type="radio" :value="m.key" v-model="selectedServiceMethod"
                    :class="m.warning ? 'dock-radio--large' : 'dock-radio--normal'" />
                </div>
                <div class="dock-method-row__body">
                  <span class="dock-method-row__label" :class="{ 'dock-method-row__label--bold': m.warning }">
                    {{ m.label }}
                    <span v-if="m.warning" class="dock-shortest-tag">SHORTEST DEADLINE</span>
                  </span>
                  <span class="dock-method-row__date">
                    Answer due: <strong>{{ docketingPreviews[m.key]?.[0]?.calculated_date || '…' }}</strong>
                    <span v-if="docketingPreviews[m.key]?.[0]?.is_business_day_adj" class="dock-rolled-note">*rolled</span>
                  </span>
                </div>
              </div>
            </div>

            <div v-if="selectedServiceMethod !== 'personal'" class="dock-non-shortest-warn">
              ⚠ You are selecting a longer deadline. Confirm you have independently verified the service method.
            </div>

            <div class="dock-disclaimer">
              ⚠ {{ docketingDisclaimer }}
            </div>

            <div class="dock-modal__footer">
              <button class="piq-btn piq-btn--ghost" @click="showServiceModal=false">Cancel</button>
              <button class="piq-btn piq-btn--primary" @click="triggerDocketing" :disabled="docketingTriggering">
                {{ docketingTriggering ? 'Generating…' : 'Confirm & Generate Chain' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Chain view -->
        <div class="tab-toolbar">
          <span class="dim sm">{{ docketingChains.length }} chain{{ docketingChains.length !== 1 ? 's' : '' }}</span>
          <button class="btn-gold sm" @click="openDocketingModal">+ Start Docketing Chain</button>
        </div>

        <div v-if="docketingLoading" class="state-msg">Loading…</div>
        <div v-else-if="!docketingChains.length" class="empty-tab">
          <div class="empty-tab__icon">⚖️</div>
          <div class="empty-tab__title">No docketing chains yet</div>
          <div class="empty-tab__sub">Click "Start Docketing Chain" to auto-generate deadlines from court rules.</div>
        </div>

        <div v-else>
          <div v-for="chain in docketingChains" :key="chain.id" class="dock-chain">
            <div class="dock-chain__header">
              <span class="dock-chain__juris">{{ chain.jurisdiction.replace('_',' ') }}</span>
              <span class="dock-chain__trigger">{{ chain.trigger_event }} · {{ chain.trigger_date?.slice(0,10) }}</span>
              <span class="dock-chain__service">Service: {{ chain.service_method }}</span>
            </div>

            <div class="dock-events">
              <div v-for="ev in chain.events" :key="ev.id" class="dock-event"
                :class="{ 'dock-event--court': ev.is_court_date }">
                <div class="dock-event__left">
                  <span class="dock-date-pill"
                    :class="[
                      ev.confirmation_state === 'pending'   ? 'dock-date-pill--pending' :
                      ev.confirmation_state === 'confirmed' ? 'dock-date-pill--confirmed' :
                      ev.confirmation_state === 'modified'  ? (ev.postponed ? 'dock-date-pill--postponed' : 'dock-date-pill--modified') :
                      'dock-date-pill--overdue'
                    ]">
                    {{ (ev.confirmed_date || ev.calculated_date)?.slice(0,10) }}
                  </span>
                  <div class="dock-event__info">
                    <span class="dock-event__title">{{ ev.title }}</span>
                    <span v-if="ev.rule_reference" class="dock-event__rule">{{ ev.rule_reference }}</span>
                    <span v-if="ev.is_business_day_adj" class="dock-rolled-note">{{ ev.business_day_note }}</span>
                    <span v-if="ev.postponement_note" class="dock-postpone-note">📌 {{ ev.postponement_note }}</span>
                  </div>
                </div>
                <div class="dock-event__right">
                  <span class="dock-state-pill" :class="docketStatePill(ev.confirmation_state, ev.postponed).cls">
                    {{ docketStatePill(ev.confirmation_state, ev.postponed).label }}
                  </span>
                  <span v-if="ev.confirmation_state === 'pending' && ev.days_unconfirmed > 0"
                    class="dock-lap-counter">
                    {{ daysLapLabel(ev.days_unconfirmed) }}
                  </span>
                  <button v-if="ev.confirmation_state === 'pending'"
                    class="piq-btn piq-btn--success piq-btn--sm"
                    @click="confirmDocketingEvent(ev.id, null, null)">
                    ✓ Confirm
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div class="dock-disclaimer dock-disclaimer--bottom">⚠ {{ docketingDisclaimer }}</div>
        </div>
      </div>

      <!-- ── Billing Ledger ── -->
      <div v-else-if="activeTab === 'billing'" class="mod-pane">
        <div v-if="billingLoading" class="state-msg">Loading billing ledger…</div>
        <div v-else-if="!billingLedger" class="empty-tab">
          <div class="empty-tab__icon">💳</div>
          <div class="empty-tab__title">No billing data yet</div>
        </div>
        <div v-else>

          <!-- Summary bar -->
          <div class="bl-ledger-summary">
            <div class="bl-ledger-stat">
              <span class="bl-ledger-stat__label">Total Billed</span>
              <span class="bl-ledger-stat__value">${{ billingLedger.total_billed?.toFixed(2) }}</span>
            </div>
            <div class="bl-ledger-stat">
              <span class="bl-ledger-stat__label">Total Paid</span>
              <span class="bl-ledger-stat__value bl-ledger-stat__value--paid">${{ billingLedger.total_paid?.toFixed(2) }}</span>
            </div>
            <div class="bl-ledger-stat">
              <span class="bl-ledger-stat__label">Balance Due</span>
              <span class="bl-ledger-stat__value" :class="billingLedger.balance_due > 0 ? 'bl-ledger-stat__value--due' : 'bl-ledger-stat__value--paid'">
                ${{ billingLedger.balance_due?.toFixed(2) }}
              </span>
            </div>
            <div v-if="billingLedger.unbilled_total > 0" class="bl-ledger-stat">
              <span class="bl-ledger-stat__label">Unbilled Time</span>
              <span class="bl-ledger-stat__value bl-ledger-stat__value--warn">${{ billingLedger.unbilled_total?.toFixed(2) }}</span>
            </div>
          </div>

          <!-- Unbilled entries warning -->
          <div v-if="billingLedger.unbilled_entries?.length" class="bl-unbilled-warn">
            ⚠ {{ billingLedger.unbilled_entries.length }} certified time
            {{ billingLedger.unbilled_entries.length === 1 ? 'entry' : 'entries' }}
            (${{ billingLedger.unbilled_total?.toFixed(2) }}) not yet invoiced.
            <a href="/client-billing" class="bl-link">Go to Client Billing →</a>
          </div>

          <!-- Invoice cards -->
          <div v-if="!billingLedger.invoices?.length" class="empty-tab" style="padding:16px 0">
            <div class="empty-tab__icon">📄</div>
            <div class="empty-tab__title">No invoices yet</div>
            <div class="empty-tab__sub">Generate invoices from the <a href="/client-billing" class="bl-link">Client Billing Dashboard</a></div>
          </div>

          <div v-for="inv in billingLedger.invoices" :key="inv.id" class="bl-invoice-card">
            <!-- Invoice header -->
            <div class="bl-invoice-card__header">
              <div class="bl-invoice-card__left">
                <span class="bl-inv-number">{{ inv.invoice_number }}</span>
                <span class="bl-inv-status" :class="`bl-inv-status--${inv.status}`">
                  {{ inv.status?.replace(/_/g,' ').toUpperCase() }}
                </span>
                <span v-if="inv.running_balance > 0" class="bl-inv-balance">
                  Balance: ${{ inv.running_balance?.toFixed(2) }}
                </span>
                <span v-else class="bl-inv-paid">✓ PAID</span>
              </div>
              <div class="bl-invoice-card__right">
                <span class="bl-inv-meta">Issued: {{ inv.issue_date?.slice(0,10) }}</span>
                <span class="bl-inv-meta">Due: {{ inv.due_date?.slice(0,10) }}</span>
                <button class="bl-pdf-btn" @click="previewInvoicePdf(inv.id)" title="Preview PDF">👁 Preview</button>
                <button class="bl-pdf-btn" @click="downloadInvoicePdf(inv.id, inv.invoice_number)" title="Download PDF">⬇ PDF</button>
              </div>
            </div>

            <!-- Line items -->
            <table class="piq-table bl-items-table">
              <thead>
                <tr><th>Date</th><th>Description</th><th>Activity</th><th>Hrs</th><th>Rate</th><th>Amount</th></tr>
              </thead>
              <tbody>
                <tr v-for="item in inv.items" :key="item.id">
                  <td class="dim nowrap">{{ item.date?.slice(0,10) }}</td>
                  <td>{{ item.description }}</td>
                  <td><span class="type-pill">{{ item.activity_type || '—' }}</span></td>
                  <td class="dim">{{ parseFloat(item.quantity || 0).toFixed(2) }}</td>
                  <td class="dim">${{ parseFloat(item.rate || 0).toFixed(2) }}/hr</td>
                  <td class="dim">${{ parseFloat(item.amount || 0).toFixed(2) }}</td>
                </tr>
              </tbody>
              <tfoot>
                <tr class="bl-totals-row">
                  <td colspan="4"></td>
                  <td class="dim">Subtotal</td>
                  <td>${{ parseFloat(inv.subtotal || 0).toFixed(2) }}</td>
                </tr>
                <tr v-if="parseFloat(inv.tax_amount) > 0" class="bl-totals-row">
                  <td colspan="4"></td>
                  <td class="dim">Tax</td>
                  <td>${{ parseFloat(inv.tax_amount || 0).toFixed(2) }}</td>
                </tr>
                <tr class="bl-totals-row bl-totals-row--total">
                  <td colspan="4"></td>
                  <td>Total</td>
                  <td>${{ parseFloat(inv.total || 0).toFixed(2) }}</td>
                </tr>
              </tfoot>
            </table>

            <!-- Payments -->
            <div v-if="inv.payments?.length" class="bl-payments">
              <div class="bl-payments__title">Payments Received</div>
              <div v-for="pay in inv.payments" :key="pay.id" class="bl-payment-row">
                <span class="dim">{{ pay.payment_date?.slice(0,10) }}</span>
                <span class="dim">{{ pay.method }}</span>
                <span class="dim">{{ pay.reference || '—' }}</span>
                <span class="bl-payment-amt">+${{ parseFloat(pay.amount || 0).toFixed(2) }}</span>
              </div>
            </div>
            <div v-else class="bl-no-payments">No payments recorded yet.</div>
          </div>
        </div>
      </div>

      <div v-else-if="activeTab === 'binder'" class="mod-pane">
        <div class="tab-toolbar">
          <span class="dim sm">{{ binderItems.length }} item{{ binderItems.length !== 1 ? 's' : '' }}</span>
          <select v-model="binderFilter" class="piq-input" style="width:140px;padding:4px 8px;">
            <option value="">All types</option>
            <option value="email">Emails</option>
            <option value="upload">Uploads</option>
            <option value="ai_draft">AI Drafts</option>
            <option value="research">Research</option>
          </select>
        </div>
        <div v-if="binderLoading" class="state-msg">Loading binder…</div>
        <div v-else-if="!binderItems.length" class="empty-tab">
          <div class="empty-tab__icon">🗂️</div>
          <div class="empty-tab__title">No binder items yet</div>
          <div class="empty-tab__sub">Emails, documents, drafts and research will appear here automatically.</div>
        </div>
        <div v-else class="table-wrap">
          <table class="piq-table">
            <thead>
              <tr><th>Type</th><th>Title</th><th>Source</th><th>Date</th><th>Score</th><th>Sentiment</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in filteredBinderItems" :key="item.id + item.binder_type">
                <td>
                  <span :class="['type-pill', 'binder-type--' + item.binder_type]">
                    {{ binderTypeLabel(item.binder_type) }}
                  </span>
                </td>
                <td class="doc-name">
                  <a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noopener" class="binder-link">{{ item.title }} ↗</a>
                  <span v-else>{{ item.title }}</span>
                </td>
                <td class="dim">{{ item.source || '—' }}</td>
                <td class="dim nowrap">{{ item.date ? fmtDate(item.date) : '—' }}</td>
                <td>
                  <span v-if="item.email_score" :class="['score-pill', item.email_score >= 70 ? 'score-pill--high' : 'score-pill--mid']">
                    {{ item.email_score }}
                  </span>
                  <span v-else class="dim">—</span>
                </td>
                <td>
                  <span v-if="item.sentiment" :class="['sentiment-pill', 'sentiment--' + item.sentiment]">{{ item.sentiment }}</span>
                  <span v-else class="dim">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- ── Add Modal (shared) ── -->
    <Teleport to="body">
      <div v-if="modModal" class="mod-overlay" @click.self="modModal=false">
        <div class="mod-modal">
          <div class="mod-modal__header">
            <span>Add {{ activeTab.charAt(0).toUpperCase() + activeTab.slice(1) }}</span>
            <button class="mod-modal__close" @click="modModal=false">✕</button>
          </div>
          <div class="mod-modal__body">

            <template v-if="activeTab==='contacts'">
              <div class="field"><label class="field__label">Name *</label><input v-model="modForm.name" class="piq-input w100" placeholder="Jane Smith" /></div>
              <div class="field"><label class="field__label">Role</label><input v-model="modForm.role" class="piq-input w100" placeholder="Opposing Counsel" /></div>
              <div class="field"><label class="field__label">Organization</label><input v-model="modForm.organization" class="piq-input w100" /></div>
              <div class="field"><label class="field__label">Email</label><input v-model="modForm.email" class="piq-input w100" type="email" /></div>
              <div class="field"><label class="field__label">Phone</label><input v-model="modForm.phone" class="piq-input w100" /></div>
            </template>

            <template v-else-if="activeTab==='correspondence'">
              <div class="field"><label class="field__label">Subject *</label><input v-model="modForm.subject" class="piq-input w100" /></div>
              <div class="field"><label class="field__label">Direction</label>
                <select v-model="modForm.direction" class="piq-input w100"><option value="outbound">Outbound</option><option value="inbound">Inbound</option></select>
              </div>
              <div class="field"><label class="field__label">Counterparty</label><input v-model="modForm.counterparty" class="piq-input w100" /></div>
              <div class="field"><label class="field__label">Body</label><textarea v-model="modForm.body" class="note-input w100" rows="3"></textarea></div>
            </template>

            <template v-else-if="activeTab==='contracts'">
              <div class="field"><label class="field__label">Title *</label><input v-model="modForm.title" class="piq-input w100" /></div>
              <div class="field"><label class="field__label">Status</label>
                <select v-model="modForm.status" class="piq-input w100"><option>draft</option><option>executed</option><option>expired</option><option>terminated</option></select>
              </div>
              <div class="field"><label class="field__label">Notes</label><textarea v-model="modForm.notes" class="note-input w100" rows="2"></textarea></div>
            </template>

            <template v-else-if="activeTab==='motions'">
              <div class="field"><label class="field__label">Title *</label><input v-model="modForm.title" class="piq-input w100" placeholder="Motion to Dismiss" /></div>
              <div class="field"><label class="field__label">Status</label>
                <select v-model="modForm.status" class="piq-input w100"><option>draft</option><option>filed</option><option>pending</option><option>granted</option><option>denied</option></select>
              </div>
              <div class="field"><label class="field__label">Ruling</label><input v-model="modForm.ruling" class="piq-input w100" /></div>
            </template>

            <template v-else-if="activeTab==='calendar'">
              <div class="field"><label class="field__label">Title *</label><input v-model="modForm.title" class="piq-input w100" placeholder="Deposition — Jane Smith" /></div>
              <div class="field"><label class="field__label">Type</label>
                <select v-model="modForm.event_type" class="piq-input w100"><option>deadline</option><option>hearing</option><option>deposition</option><option>meeting</option><option>trial</option></select>
              </div>
              <div class="field"><label class="field__label">Date</label>
                <input type="date" class="piq-input w100"
                  :value="modForm.due_date || ''"
                  @change="e => modForm.due_date = e.target.value" />
              </div>
              <div class="field"><label class="field__label">Location</label><input v-model="modForm.location" class="piq-input w100" /></div>
            </template>

          </div>
          <div class="mod-modal__footer">
            <button class="btn-secondary" @click="modModal=false">Cancel</button>
            <button class="btn-gold" @click="submitMod">Save</button>
          </div>
        </div>
      </div>
    </Teleport>


    <DiscoveryUpload
      v-if="matter"
      :show="showUpload"
      :matter-id="matter.id"
      :matter-name="matter.client_name"
      :case-number="matter.case_number"
      @close="showUpload = false"
      @uploaded="onUpload"
    />

  </div>
</template>

<style scoped>
.mdetail { padding: 2rem; max-width: 1100px; }

.breadcrumb { align-items: center; display: flex; gap: 0.5rem; margin-bottom: 1.5rem; }
.breadcrumb__back { background: none; border: none; color: var(--gold); cursor: pointer; font-size: 0.85rem; padding: 0; }
.breadcrumb__back:hover { text-decoration: underline; }

.case-header { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; display: flex; align-items: flex-start; gap: 1rem; justify-content: space-between; margin-bottom: 1rem; padding: 1.5rem; }
.case-header__title  { color: var(--text-primary); font-family: var(--font-display); font-size: 1.5rem; font-weight: 700; margin: 0.25rem 0 0.75rem; }
.case-header__pills  { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.case-header__actions { display: flex; flex-shrink: 0; gap: 0.5rem; }

.risk-pill   { border-radius: 4px; font-size: 0.72rem; font-weight: 700; padding: 0.2rem 0.55rem; text-transform: uppercase; }
.status-pill { border-radius: 4px; font-size: 0.72rem; font-weight: 700; padding: 0.2rem 0.55rem; }
.meta-chip   { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); font-size: 0.75rem; padding: 0.2rem 0.55rem; }

.meta-grid       { display: grid; gap: 0.75rem; grid-template-columns: repeat(auto-fill, minmax(150px,1fr)); margin-bottom: 1.5rem; }
.meta-item       { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 0.85rem 1rem; }
.meta-item--wide { grid-column: 1 / -1; }
.meta-item__label { color: var(--text-muted); font-size: 0.68rem; font-weight: 600; letter-spacing: .06em; margin-bottom: 0.35rem; text-transform: uppercase; }
.meta-item__val   { color: var(--text-primary); font-size: 0.9rem; font-weight: 600; }

.tabs { border-bottom: 1px solid var(--border); display: flex; gap: 0.25rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.tab  { align-items: center; background: none; border: none; border-bottom: 2px solid transparent; color: var(--text-muted); cursor: pointer; display: flex; font-size: 0.875rem; gap: 0.35rem; padding: 0.6rem 1.1rem; transition: color .15s, border-color .15s; }
.tab:hover   { color: var(--text-primary); }
.tab--active { border-bottom-color: var(--gold); color: var(--gold); }
.tab-count { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 10px; font-size: 0.65rem; padding: 0.05rem 0.4rem; }
.tab--active .tab-count { background: rgba(201,168,76,.15); border-color: var(--gold); color: var(--gold); }

.tab-toolbar { align-items: center; display: flex; justify-content: space-between; margin-bottom: 0.75rem; }

.pipeline-summary { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1rem; }
.pipeline-chip { align-items: center; background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; display: flex; gap: 0.4rem; padding: 0.4rem 0.75rem; }
.pipeline-chip__dot   { border-radius: 50%; flex-shrink: 0; height: 8px; width: 8px; }
.pipeline-chip__count { font-size: 0.85rem; font-weight: 700; }

.table-wrap { border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; }
.piq-table  { border-collapse: collapse; font-size: 0.875rem; width: 100%; }
.piq-table th { background: var(--bg-card); border-bottom: 1px solid var(--border); color: var(--text-muted); font-size: 0.7rem; font-weight: 600; letter-spacing: .05em; padding: 0.65rem 0.9rem; text-align: left; text-transform: uppercase; }
.piq-table td { border-bottom: 1px solid var(--border); padding: 0.7rem 0.9rem; vertical-align: middle; }
.piq-table tr:last-child td { border-bottom: none; }
.piq-table tr:hover td { background: rgba(255,255,255,.02); }

.doc-name  { color: var(--text-primary); font-size: 0.85rem; font-weight: 500; }
.type-pill { background: rgba(74,124,247,.12); border-radius: 4px; color: #4a7cf7; font-size: 0.7rem; font-weight: 600; padding: 0.15rem 0.45rem; text-transform: capitalize; }
.route-pill { border-radius: 4px; font-size: 0.7rem; font-weight: 600; padding: 0.15rem 0.45rem; text-transform: uppercase; }
.status-chip            { background: rgba(113,128,150,.15); border-radius: 4px; color: #718096; font-size: 0.7rem; font-weight: 600; padding: 0.15rem 0.45rem; }
.s-processed            { background: rgba(72,187,120,.15)  !important; color: #48bb78 !important; }
.s-text_extracted       { background: rgba(74,124,247,.15)  !important; color: #4a7cf7 !important; }
.s-ocr_complete         { background: rgba(159,122,234,.15) !important; color: #9f7aea !important; }
.s-error                { background: rgba(252,129,129,.15) !important; color: #fc8181 !important; }

.notes-pane { display: flex; flex-direction: column; gap: 1rem; }
.note-composer { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; display: flex; flex-direction: column; gap: 0.75rem; padding: 1rem; }
.note-input { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; box-sizing: border-box; color: var(--text-primary); font-family: inherit; font-size: 0.875rem; outline: none; padding: 0.75rem; resize: vertical; width: 100%; }
.note-input:focus { border-color: var(--gold); }
.note-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }
.note-card__text { color: var(--text-primary); font-size: 0.875rem; line-height: 1.6; margin-bottom: 0.5rem; white-space: pre-wrap; }

.stub-tab { align-items: center; display: flex; flex-direction: column; gap: 0.75rem; padding: 4rem 2rem; text-align: center; }
.stub-tab__icon  { font-size: 2.5rem; opacity: .35; }
.stub-tab__title { color: var(--text-primary); font-size: 1.05rem; font-weight: 600; }
.stub-tab__sub   { color: var(--text-muted); font-size: 0.875rem; line-height: 1.5; max-width: 380px; }

.empty-tab { align-items: center; display: flex; flex-direction: column; gap: 0.75rem; padding: 3rem 2rem; text-align: center; }
.empty-tab__icon  { font-size: 2rem; opacity: .3; }
.empty-tab__title { color: var(--text-muted); font-size: 0.95rem; font-weight: 500; }

.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1.1rem; transition: opacity .15s; }
.btn-gold:hover:not(:disabled) { opacity: .85; }
.btn-gold:disabled { cursor: not-allowed; opacity: .45; }
.btn-gold.sm { font-size: 0.78rem; padding: 0.4rem 0.9rem; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; transition: all .15s; }
.btn-secondary:hover { background: var(--bg-raised); color: var(--text-primary); }

.state-msg { color: var(--text-muted); padding: 4rem; text-align: center; }
.dim    { color: var(--text-muted); }
.sm     { font-size: 0.78rem; }
.mono   { font-family: var(--font-mono); }
.nowrap { white-space: nowrap; }

.mod-pane { }
.del-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.8rem; opacity: 0.4; padding: 0.2rem 0.4rem; transition: opacity .15s, color .15s; }
.del-btn:hover { color: #fc8181; opacity: 1; }
.pill-in  { background: rgba(72,187,120,.15) !important; color: #48bb78 !important; }
.pill-out { background: rgba(74,124,247,.15) !important; color: #4a7cf7 !important; }
.s-draft      { background: rgba(113,128,150,.15) !important; color: #718096 !important; }
.s-executed   { background: rgba(72,187,120,.15)  !important; color: #48bb78 !important; }
.s-filed      { background: rgba(74,124,247,.15)  !important; color: #4a7cf7 !important; }
.s-granted    { background: rgba(72,187,120,.15)  !important; color: #48bb78 !important; }
.s-denied     { background: rgba(252,129,129,.15) !important; color: #fc8181 !important; }
.s-pending    { background: rgba(236,201,75,.15)  !important; color: #ecc94b !important; }
.w100 { width: 100%; box-sizing: border-box; }
.mod-overlay { align-items: center; background: rgba(0,0,0,.65); bottom: 0; display: flex; justify-content: center; left: 0; position: fixed; right: 0; top: 0; z-index: 1000; }
.mod-modal { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 10px; box-shadow: 0 24px 80px rgba(0,0,0,.6); display: flex; flex-direction: column; max-height: 90vh; overflow: hidden; width: 480px; }
.mod-modal__header { align-items: center; border-bottom: 1px solid var(--border); color: var(--text-primary); display: flex; font-size: 0.95rem; font-weight: 600; justify-content: space-between; padding: 1rem 1.25rem; }
.mod-modal__close { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1rem; padding: 0.2rem; }
.mod-modal__close:hover { color: var(--text-primary); }
.mod-modal__body { display: flex; flex-direction: column; gap: 0.85rem; overflow-y: auto; padding: 1.25rem; }
.mod-modal__footer { border-top: 1px solid var(--border); display: flex; gap: 0.5rem; justify-content: flex-end; padding: 1rem 1.25rem; }
.field { display: flex; flex-direction: column; gap: 0.3rem; }


/* Intelligence signals */
.intel-pane { }
.signal-list { display: flex; flex-direction: column; gap: 0.75rem; }
.signal-card { border-radius: 8px; border: 1px solid var(--border); padding: 1rem 1.1rem; }
.signal-card--critical { border-left: 3px solid #fc8181; background: rgba(252,129,129,.04); }
.signal-card--warning  { border-left: 3px solid #ecc94b; background: rgba(236,201,75,.04); }
.signal-card--info     { border-left: 3px solid #4a7cf7; background: rgba(74,124,247,.04); }
.signal-card__header { align-items: center; display: flex; gap: 0.5rem; margin-bottom: 0.5rem; flex-wrap: wrap; }
.signal-card__title  { color: var(--text-primary); font-size: 0.875rem; font-weight: 600; flex: 1; }
.signal-card__desc   { color: var(--text-muted); font-size: 0.82rem; line-height: 1.6; }
.sev-badge { border-radius: 3px; font-size: 0.65rem; font-weight: 700; letter-spacing: .05em; padding: 0.15rem 0.45rem; text-transform: uppercase; }
.sev-badge--critical { background: rgba(252,129,129,.18); color: #fc8181; }
.sev-badge--warning  { background: rgba(236,201,75,.18);  color: #ecc94b; }
.sev-badge--info     { background: rgba(74,124,247,.18);  color: #4a7cf7; }
.ai-badge { background: rgba(159,122,234,.15); border-radius: 3px; color: #9f7aea; font-size: 0.65rem; font-weight: 700; padding: 0.15rem 0.4rem; }

/* Timeline */
.tl-pane { }
.tl-list { display: flex; flex-direction: column; }
.tl-item { display: flex; gap: 0.75rem; }
.tl-item__spine { align-items: center; display: flex; flex-direction: column; flex-shrink: 0; width: 16px; }
.tl-item__dot { border-radius: 50%; flex-shrink: 0; height: 12px; width: 12px; margin-top: 4px; }
.dot-high   { background: #fc8181; box-shadow: 0 0 0 3px rgba(252,129,129,.2); }
.dot-medium { background: #ecc94b; box-shadow: 0 0 0 3px rgba(236,201,75,.2); }
.dot-low    { background: #718096; }
.tl-item__line { background: var(--border); flex: 1; margin: 4px 0; width: 1px; min-height: 24px; }
.tl-item__body { padding-bottom: 1.25rem; flex: 1; min-width: 0; }
.tl-item__date  { margin-bottom: 0.2rem; }
.tl-item__event { color: var(--text-primary); font-size: 0.875rem; line-height: 1.55; margin-bottom: 0.35rem; }
.tl-item__meta  { align-items: center; display: flex; flex-wrap: wrap; gap: 0.4rem; }
.sig-chip { border-radius: 3px; font-size: 0.65rem; font-weight: 700; padding: 0.1rem 0.4rem; text-transform: uppercase; }
.sig-chip--high   { background: rgba(252,129,129,.15); color: #fc8181; }
.sig-chip--medium { background: rgba(236,201,75,.15);  color: #ecc94b; }
.sig-chip--low    { background: rgba(113,128,150,.15); color: #718096; }
.binder-type--email    { background: #1a3a5c; color: #7ec8e3; }
.binder-type--upload   { background: #2a2a1a; color: #c8b96e; }
.binder-link           { color: var(--gold, #c9a84c); text-decoration: none; font-weight: 500; }
.binder-link:hover     { text-decoration: underline; }
.binder-type--ai_draft { background: #1a2a1a; color: #7ec87e; }
.binder-type--research { background: #2a1a2a; color: #c87ec8; }
.score-pill            { padding: 2px 7px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.score-pill--high      { background: #1a3a1a; color: #7ec87e; }
.score-pill--mid       { background: #3a2a1a; color: #c8a06e; }
.empty-tab__sub        { font-size: 12px; color: var(--dim); margin-top: 4px; }

/* ── Docketing ─────────────────────────────────────────── */
.dock-modal-overlay    { position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:1000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px); }
.dock-modal            { background:var(--surface-card);border:1px solid var(--border);border-radius:12px;padding:24px;width:560px;max-width:95vw;max-height:90vh;overflow-y:auto; }
.dock-modal__header    { display:flex;align-items:center;justify-content:space-between;margin-bottom:16px; }
.dock-modal__title     { font-size:15px;font-weight:700;color:var(--text-primary); }
.dock-modal__close     { background:none;border:none;color:var(--text-tertiary);cursor:pointer;font-size:16px; }
.dock-modal__row       { display:flex;align-items:center;gap:12px;margin-bottom:12px; }
.dock-modal__label     { font-size:12px;color:var(--text-tertiary);width:160px;flex-shrink:0; }
.dock-modal__service-title   { font-size:13px;font-weight:600;color:var(--text-primary);margin:16px 0 4px; }
.dock-modal__service-subtitle { font-size:12px;color:var(--text-tertiary);margin-bottom:10px; }
.dock-modal__methods   { display:flex;flex-direction:column;gap:8px;margin-bottom:12px; }
.dock-modal__footer    { display:flex;justify-content:flex-end;gap:10px;margin-top:16px;padding-top:12px;border-top:1px solid var(--border); }
.dock-method-row       { display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:8px;border:1px solid var(--border);cursor:pointer;transition:background .15s; }
.dock-method-row:hover { background:var(--surface-hover); }
.dock-method-row--shortest  { background:rgba(16,185,129,.08);border-color:rgba(16,185,129,.3); }
.dock-method-row--selected  { border-color:var(--accent); }
.dock-method-row__check     { flex-shrink:0; }
.dock-radio--large     { width:20px;height:20px;accent-color:#34d399; }
.dock-radio--normal    { width:14px;height:14px; }
.dock-method-row__body      { display:flex;flex-direction:column;gap:2px;flex:1; }
.dock-method-row__label     { font-size:13px;color:var(--text-primary); }
.dock-method-row__label--bold { font-weight:700;font-size:14px; }
.dock-shortest-tag     { font-size:10px;font-weight:700;color:#f59e0b;margin-left:8px;letter-spacing:.04em; }
.dock-method-row__date { font-size:12px;color:var(--text-secondary); }
.dock-rolled-note      { font-size:11px;color:#f59e0b;margin-left:4px; }
.dock-non-shortest-warn { background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);border-radius:6px;padding:8px 12px;font-size:12px;color:#fbbf24;margin-bottom:10px; }
.dock-disclaimer       { background:rgba(239,68,68,.07);border:1px solid rgba(239,68,68,.2);border-radius:6px;padding:10px 12px;font-size:11px;color:#fca5a5;line-height:1.6; }
.dock-disclaimer--bottom { margin-top:16px; }
.dock-chain            { margin-bottom:20px;border:1px solid var(--border);border-radius:10px;overflow:hidden; }
.dock-chain__header    { display:flex;align-items:center;gap:12px;padding:10px 14px;background:var(--surface-hover);font-size:12px; }
.dock-chain__juris     { font-weight:700;color:var(--text-primary); }
.dock-chain__trigger   { color:var(--text-secondary); }
.dock-chain__service   { color:var(--text-tertiary);margin-left:auto; }
.dock-events           { display:flex;flex-direction:column; }
.dock-event            { display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:10px 14px;border-top:1px solid var(--border);font-size:13px; }
.dock-event--court     { background:rgba(99,102,241,.04); }
.dock-event:hover      { background:var(--surface-hover); }
.dock-event__left      { display:flex;align-items:flex-start;gap:10px;flex:1;min-width:0; }
.dock-event__right     { display:flex;align-items:center;gap:8px;flex-shrink:0; }
.dock-event__info      { display:flex;flex-direction:column;gap:2px; }
.dock-event__title     { color:var(--text-primary);font-weight:500; }
.dock-event__rule      { font-size:11px;color:var(--text-tertiary); }
.dock-postpone-note    { font-size:11px;color:#fbbf24; }
.dock-lap-counter      { font-size:11px;color:#f87171;font-weight:600; }
.dock-date-pill        { display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;white-space:nowrap;flex-shrink:0; }
.dock-date-pill--pending   { background:rgba(245,158,11,.15);color:#fbbf24;border:1px solid rgba(245,158,11,.3); }
.dock-date-pill--confirmed { background:rgba(16,185,129,.15);color:#34d399;border:1px solid rgba(16,185,129,.3); }
.dock-date-pill--modified  { background:rgba(16,185,129,.15);color:#34d399;border:2px solid #34d399; }
.dock-date-pill--postponed { background:rgba(16,185,129,.15);color:#34d399;border:2px solid #34d399;outline:2px solid rgba(16,185,129,.3);outline-offset:1px; }
.dock-date-pill--overdue   { background:rgba(239,68,68,.15);color:#f87171;border:1px solid rgba(239,68,68,.3);animation:pulse 1.5s infinite; }
.dock-state-pill       { display:inline-block;padding:2px 8px;border-radius:8px;font-size:10px;font-weight:700;letter-spacing:.04em; }
.dock-pill--pending    { background:rgba(245,158,11,.15);color:#fbbf24; }
.dock-pill--confirmed  { background:rgba(16,185,129,.15);color:#34d399; }
.dock-pill--modified   { background:rgba(16,185,129,.15);color:#34d399;border:2px solid #34d399; }
.dock-pill--postponed  { background:rgba(16,185,129,.15);color:#34d399;border:2px solid #34d399;outline:2px solid rgba(16,185,129,.3);outline-offset:1px; }
.dock-pill--overdue    { background:rgba(239,68,68,.15);color:#f87171; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }


/* ── Billing Ledger Tab ───────────────────────────── */
.bl-ledger-summary        { display:flex;gap:16px;flex-wrap:wrap;margin-bottom:14px;padding:12px 14px;background:var(--surface-hover);border-radius:8px; }
.bl-ledger-stat           { display:flex;flex-direction:column;gap:2px; }
.bl-ledger-stat__label    { font-size:11px;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em; }
.bl-ledger-stat__value    { font-size:18px;font-weight:700;color:var(--text-primary); }
.bl-ledger-stat__value--paid { color:#34d399; }
.bl-ledger-stat__value--due  { color:#fbbf24; }
.bl-ledger-stat__value--warn { color:#f59e0b; }
.bl-unbilled-warn         { background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);border-radius:6px;padding:8px 12px;font-size:12px;color:#fbbf24;margin-bottom:12px; }
.bl-link                  { color:var(--accent);text-decoration:none;margin-left:6px; }
.bl-invoice-card          { border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:14px; }
.bl-invoice-card__header  { display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;background:var(--surface-hover);flex-wrap:wrap; }
.bl-invoice-card__left    { display:flex;align-items:center;gap:10px;flex-wrap:wrap; }
.bl-invoice-card__right   { display:flex;align-items:center;gap:8px;flex-shrink:0; }
.bl-inv-number            { font-size:13px;font-weight:700;color:var(--text-primary);font-family:monospace; }
.bl-inv-status            { font-size:10px;font-weight:700;padding:2px 8px;border-radius:8px;text-transform:uppercase;letter-spacing:.04em; }
.bl-inv-status--draft              { background:rgba(107,114,128,.15);color:#9ca3af; }
.bl-inv-status--pending_certification { background:rgba(245,158,11,.15);color:#fbbf24; }
.bl-inv-status--certified          { background:rgba(99,102,241,.15);color:#818cf8; }
.bl-inv-status--sent               { background:rgba(59,130,246,.15);color:#60a5fa; }
.bl-inv-status--viewed             { background:rgba(139,92,246,.15);color:#a78bfa; }
.bl-inv-status--partially_paid     { background:rgba(16,185,129,.1);color:#34d399; }
.bl-inv-status--paid               { background:rgba(16,185,129,.2);color:#34d399; }
.bl-inv-status--overdue            { background:rgba(239,68,68,.15);color:#f87171; }
.bl-inv-status--void               { background:rgba(107,114,128,.1);color:#6b7280; }
.bl-inv-balance           { font-size:12px;color:#fbbf24;font-weight:600; }
.bl-inv-paid              { font-size:12px;color:#34d399;font-weight:700; }
.bl-inv-meta              { font-size:11px;color:var(--text-tertiary); }
.bl-pdf-btn               { padding:3px 8px;font-size:11px;border-radius:5px;border:1px solid var(--border);background:var(--surface);color:var(--text-secondary);cursor:pointer; }
.bl-pdf-btn:hover         { background:var(--surface-hover); }
.bl-items-table           { margin:0; }
.bl-totals-row td         { font-size:12px;color:var(--text-secondary); }
.bl-totals-row--total td  { font-weight:700;color:var(--text-primary);border-top:1px solid var(--border); }
.bl-payments              { padding:10px 14px;border-top:1px solid var(--border); }
.bl-payments__title       { font-size:11px;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px; }
.bl-payment-row           { display:flex;gap:16px;align-items:center;font-size:12px;padding:3px 0; }
.bl-payment-amt           { color:#34d399;font-weight:700;margin-left:auto; }
.bl-no-payments           { padding:8px 14px;font-size:12px;color:var(--text-tertiary);border-top:1px solid var(--border); }

</style>
