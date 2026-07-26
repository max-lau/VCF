<script setup>
import { ref, computed, onMounted, watch } from "vue"
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'

const route  = useRoute()
const router = useRouter()
const caseId = computed(() => route.params.id)

const token   = () => localStorage.getItem('paraiq_token')
const authHdr = () => ({ Authorization: 'Bearer ' + token() })
const firmId  = () => localStorage.getItem('paraiq_firm_id') || 'default'

const matter      = ref(null)
const docs        = ref([])
const notes       = ref([])
const intakeScans = ref([])
const loading     = ref(true)
const activeTab   = ref('documents')
const contacts        = ref([])
const contactsLoading = ref(false)
const contactModal    = ref(false)
const contactForm     = ref({})
const newNote     = ref('')
const savingNote  = ref(false)

// VCF-specific state
const deadlines      = ref([])
const stageHistory   = ref([])
const checklist      = ref([])
const communications = ref([])
const accountPrep    = ref(null)
const loadingVcf     = ref(false)
const stageSelect    = ref('')

const TABS = [
  { key: 'overview',       label: 'Overview',       icon: '📋' },
  { key: 'documents',      label: 'Documents',      icon: '📄' },
  { key: 'intake-scans',   label: 'Intake Scans',   icon: '🔍' },
  { key: 'notes',          label: 'Notes',          icon: '📝' },
  { key: 'contacts',       label: 'Contacts',       icon: '👤' },
  { key: 'deadlines',      label: 'Deadlines',      icon: '⏰' },
  { key: 'communications', label: 'Communications', icon: '💬' },
  { key: 'disbursements',  label: 'Disbursements',  icon: '💵' },
  { key: 'account-prep',   label: 'VCF Account',    icon: '🔐' },
  { key: 'stage-history',  label: 'Stage History',  icon: '📈' },
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
    intakeScans.value = cRes.data.intake_scans || []
  } catch {
    matter.value = null
  } finally {
    loading.value = false
  }
}

function switchTab(key) {
  activeTab.value = key
  if (key === 'disbursements' && !disbursement.value)          fetchDisbursement()
  if (key === 'deadlines'     && !deadlines.value.length)      fetchDeadlines()
  if (key === 'communications' && !communications.value.length) fetchCommunications()
  if (key === 'stage-history' && !stageHistory.value.length)   fetchStageHistory()
  if (key === 'account-prep'  && !accountPrep.value)           fetchAccountPrep()
  if (key === 'contacts'      && !contacts.value.length)       fetchContacts()
}

async function fetchContacts() {
  contactsLoading.value = true
  try {
    const id = caseId.value
    const { data } = await axios.get(`/contacts/matter/${id}`, { headers: authHdr() })
    contacts.value = Array.isArray(data) ? data : (data.contacts || data.items || [])
  } catch(e) { console.error('fetchContacts', e) }
  finally { contactsLoading.value = false }
}

async function deleteContact(id) {
  if (!confirm('Delete this contact?')) return
  try { await axios.delete(`/contacts/${id}`, { headers: authHdr() }) } catch(e) { console.error(e) }
  fetchContacts()
}

function openAddContact(defaults = {}) { contactForm.value = { ...defaults }; contactModal.value = true }

async function submitContact() {
  const payload = {
    ...contactForm.value,
    matter_id: caseId.value,
    firm_id:   firmId(),
  }
  try {
    await axios.post('/contacts/', payload, { headers: authHdr() })
    contactModal.value = false
    fetchContacts()
  } catch (e) { alert('Save failed: ' + (e?.response?.data?.detail || e.message)) }
}

// ── VCF-specific fetchers ────────────────────────────────────────────────────

async function fetchDeadlines() {
  loadingVcf.value = true
  try {
    const { data } = await axios.get(`/vcf/cases/${caseId.value}/deadlines`, { headers: authHdr() })
    deadlines.value = data.deadlines || []
  } catch { deadlines.value = [] }
  finally { loadingVcf.value = false }
}

async function fetchCommunications() {
  loadingVcf.value = true
  try {
    const { data } = await axios.get(`/cases/${caseId.value}/communications`, { headers: authHdr() })
    communications.value = data.communications || []
  } catch { communications.value = [] }
  finally { loadingVcf.value = false }
}

async function fetchStageHistory() {
  loadingVcf.value = true
  try {
    const { data } = await axios.get(`/vcf/cases/${caseId.value}/stages`, { headers: authHdr() })
    stageHistory.value = data.history || []
  } catch { stageHistory.value = [] }
  finally { loadingVcf.value = false }
}

async function fetchAccountPrep() {
  loadingVcf.value = true
  try {
    const { data } = await axios.get(`/vcf/prep?case_id=${caseId.value}`, { headers: authHdr() })
    accountPrep.value = data.preps?.[0] || null
  } catch { accountPrep.value = null }
  finally { loadingVcf.value = false }
}

async function transitionStage(toStage) {
  try {
    await axios.post(`/vcf/cases/${caseId.value}/stage`, { to_stage: toStage }, { headers: authHdr() })
    await fetchMatter()
    if (activeTab.value === 'stage-history') await fetchStageHistory()
  } catch (e) {
    alert('Stage transition failed: ' + (e?.response?.data?.detail || e.message))
  }
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

onMounted(fetchMatter)

const disbursementForm = ref({ gross_award: 0, attorney_fee_pct: 10, medicare_lien: 0, medicaid_lien: 0, other_liens: 0 })
const calculateFee = computed(() => (parseFloat(disbursementForm.value.gross_award || 0) * (parseFloat(disbursementForm.value.attorney_fee_pct || 0) / 100)))
const calculateLiens = computed(() => (parseFloat(disbursementForm.value.medicare_lien || 0) + parseFloat(disbursementForm.value.medicaid_lien || 0) + parseFloat(disbursementForm.value.other_liens || 0)))
const calculateNet = computed(() => (parseFloat(disbursementForm.value.gross_award || 0) - calculateFee.value - calculateLiens.value))

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

// ── VCF Specific Helpers ───────────────────────────────────────────────────
function vcfStatusColor(s) { 
  return { 
    intake: '#4a7cf7', 
    eligibility: '#9f7aea', 
    review: '#ecc94b', 
    award: '#48bb78', 
    disbursement: '#38b2ac', 
    closed: '#718096' 
  }[s] || '#718096' 
}
function presenceColor(p) { 
  return { 
    missing: '#fc8181', 
    pending: '#ecc94b', 
    verified: '#48bb78' 
  }[p] || '#718096' 
}

// ── Disbursements Module ───────────────────────────────────────────────────
const disbursement = ref(null)
const disbLoading = ref(false)
const disbSaving = ref(false)

async function fetchDisbursement() {
  console.log("fetchDisbursement triggered! Case ID:", caseId.value, "Matter:", matter.value)
  if (!matter.value?.id) return
  disbLoading.value = true
  try {
    const { data } = await axios.get(`/vcf/cases/${caseId.value}/disbursement`, { headers: authHdr() })
    disbursement.value = data.disbursement
  } catch (e) {
    console.error('Disbursement fetch failed', e)
    disbursement.value = null
  } finally {
    disbLoading.value = false
  }
}

async function saveDisbursement() {
  if (!disbursement.value) return
  disbSaving.value = true
  try {
    // Send the whole object, backend will recalculate net and fees
    const payload = { ...disbursement.value }
    const { data } = await axios.put(`/vcf/cases/${caseId.value}/disbursement`, payload, { headers: authHdr() })
    disbursement.value = data.disbursement
    // Also update the award amount on the main matter object just in case
    matter.value.award_amount = data.disbursement.gross_award
  } catch (e) {
    alert('Failed to save disbursement data.')
    console.error(e)
  } finally {
    disbSaving.value = false
  }
}

function fmtMoney(v) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(v || 0)
}

</script>

<template>
  <div class="mdetail">

    <div class="breadcrumb">
      <button class="breadcrumb__back" @click="router.push('/matters')">← Claims</button>
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
            <span class="status-pill" :style="{ background: vcfStatusColor(matter.vcf_status)+'22', color: vcfStatusColor(matter.vcf_status) }">
              {{ matter.vcf_status || 'intake' }}
            </span>
            <span class="meta-chip" :style="{ background: presenceColor(matter.presence_proof_status)+'22', color: presenceColor(matter.presence_proof_status) }">
              Presence: {{ matter.presence_proof_status || 'missing' }}
            </span>
            <span v-if="matter.award_amount > 0" class="meta-chip" style="background: #48bb7822; color: #48bb78;">
              Award: {{ fmtMoney(matter.award_amount) }}
            </span>
          </div>
        </div>
        <div class="case-header__actions">
          <button class="btn-gold" @click="router.push('/intake')">↑ Upload</button>
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
          <span v-if="t.key==='documents' && docs.length" class="tab-count">{{ docs.length }}</span>
          <span v-if="t.key==='intake-scans' && intakeScans.length" class="tab-count">{{ intakeScans.length }}</span>
          <span v-if="t.key==='notes' && notes.length" class="tab-count">{{ notes.length }}</span>
          <span v-if="t.key==='contacts' && contacts.length" class="tab-count">{{ contacts.length }}</span>
          <span v-if="t.key==='deadlines' && deadlines.length" class="tab-count">{{ deadlines.length }}</span>
          <span v-if="t.key==='communications' && communications.length" class="tab-count">{{ communications.length }}</span>
        </button>
      </div>
      <!-- Overview -->
      <div v-if="activeTab === 'overview'" class="mod-pane">
        <div class="overview-grid">
          <div class="overview-card">
            <h3 class="overview-card__title">Claim Status</h3>
            <div class="overview-field"><label>Stage</label><span class="pill">{{ matter.claim_stage || '—' }}</span></div>
            <div class="overview-field"><label>VCF Status</label><span class="pill">{{ matter.vcf_status || '—' }}</span></div>
            <div class="overview-field"><label>Presence Proof</label><span class="pill">{{ matter.presence_proof_status || '—' }}</span></div>
            <div class="overview-field"><label>Award Amount</label><span>{{ fmtMoney(matter.award_amount) }}</span></div>
          </div>
          <div class="overview-card">
            <h3 class="overview-card__title">Client</h3>
            <div class="overview-field"><label>Date of Birth</label><span>{{ matter.date_of_birth || '—' }}</span></div>
            <div class="overview-field"><label>SSN Last 4</label><span>{{ matter.ssn_last4 || '—' }}</span></div>
            <div class="overview-field"><label>Language</label><span>{{ matter.preferred_language || '—' }}</span></div>
            <div class="overview-field"><label>WTC Health Program</label><span>{{ matter.wtc_health_program ? 'Yes' : 'No' }}</span></div>
          </div>
          <div class="overview-card">
            <h3 class="overview-card__title">Exposure</h3>
            <div class="overview-field"><label>Location</label><span>{{ matter.exposure_location || '—' }}</span></div>
            <div class="overview-field"><label>Dates</label><span>{{ matter.presence_dates || '—' }}</span></div>
          </div>
        </div>
        <div class="overview-actions">
          <label>Transition stage:</label>
          <select v-model="stageSelect" @change="transitionStage(stageSelect)">
            <option value="">— Select —</option>
            <option value="intake">Intake</option>
            <option value="eligibility_review">Eligibility Review</option>
            <option value="document_gathering">Document Gathering</option>
            <option value="vcf_account_created">VCF Account Created</option>
            <option value="claim_submitted">Claim Submitted</option>
            <option value="under_review">Under Review</option>
            <option value="award_determination">Award Determination</option>
            <option value="disbursement">Disbursement</option>
            <option value="closed">Closed</option>
          </select>
        </div>
      </div>

      <!-- Disbursements -->
      <div v-else-if="activeTab === 'disbursements'" class="mod-pane">
        <div v-if="disbLoading" class="state-msg">Loading award data…</div>
        <div v-else-if="!disbursement" class="empty-tab">
          <div class="empty-tab__icon">💵</div>
          <div class="empty-tab__title">No Disbursement Data</div>
        </div>
        <div v-else class="disb-container">
          <div class="disb-grid">
            <!-- Left Column: Inputs -->
            <div class="disb-card">
              <h3 class="disb-card__title">Award & Fees</h3>
              <div class="disb-field">
                <label>Gross VCF Award</label>
                <input type="number" v-model.number="disbursement.gross_award" @change="saveDisbursement" class="piq-input w100" />
              </div>
              <div class="disb-field">
                <label>Attorney Fee (%)</label>
                <input type="number" v-model.number="disbursement.attorney_fee_pct" @change="saveDisbursement" class="piq-input w100" />
              </div>
              <div class="disb-field">
                <label>Attorney Fee Amount</label>
                <input type="number" v-model.number="disbursement.attorney_fee_amount" disabled class="piq-input w100 disb-disabled" />
              </div>
            </div>

            <!-- Right Column: Liens -->
            <div class="disb-card">
              <h3 class="disb-card__title">Liens & Offsets</h3>
              <div class="disb-field">
                <label>Medicare Lien</label>
                <input type="number" v-model.number="disbursement.medicare_lien" @change="saveDisbursement" class="piq-input w100" />
              </div>
              <div class="disb-field">
                <label>Medicaid Lien</label>
                <input type="number" v-model.number="disbursement.medicaid_lien" @change="saveDisbursement" class="piq-input w100" />
              </div>
              <div class="disb-field">
                <label>Workers' Comp Lien</label>
                <input type="number" v-model.number="disbursement.workers_comp_lien" @change="saveDisbursement" class="piq-input w100" />
              </div>
              <div class="disb-field">
                <label>Other Liens</label>
                <input type="number" v-model.number="disbursement.other_lien" @change="saveDisbursement" class="piq-input w100" />
              </div>
            </div>
          </div>

          <!-- Bottom: Net Summary -->
          <div class="disb-summary">
            <div class="disb-summary__row">
              <span>Gross Award:</span>
              <span>{{ fmtMoney(disbursement.gross_award) }}</span>
            </div>
            <div class="disb-summary__row">
              <span>Less Attorney Fee:</span>
              <span>- {{ fmtMoney(disbursement.attorney_fee_amount) }}</span>
            </div>
            <div class="disb-summary__row">
              <span>Less Total Liens:</span>
              <span>- {{ fmtMoney(disbursement.medicare_lien + disbursement.medicaid_lien + disbursement.workers_comp_lien + disbursement.other_lien) }}</span>
            </div>
            <div class="disb-summary__row disb-summary__row--net">
              <span>Net to Claimant:</span>
              <span>{{ fmtMoney(disbursement.net_to_claimant) }}</span>
            </div>
            
            <div class="disb-status">
              <label>Status:</label>
              <select v-model="disbursement.status" @change="saveDisbursement" class="piq-input" style="width: 200px; margin-left: 10px;">
                <option value="pending">Pending</option>
                <option value="approved">Approved</option>
                <option value="disbursed">Disbursed</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <!-- VCF Deadlines -->
      <div v-else-if="activeTab === 'deadlines'" class="mod-pane">
        <div v-if="loadingVcf" class="state-msg">Loading deadlines…</div>
        <div v-else-if="!deadlines.length" class="empty-tab"><div class="empty-tab__icon">⏰</div><div class="empty-tab__title">No deadlines yet</div></div>
        <div v-else class="table-wrap">
          <table class="piq-table">
            <thead><tr><th>Type</th><th>Due Date</th><th>Status</th></tr></thead>
            <tbody>
              <tr v-for="d in deadlines" :key="d.id">
                <td class="doc-name">{{ d.deadline_type }}</td>
                <td class="dim nowrap">{{ fmtDate(d.due_date) }}</td>
                <td><span class="status-chip" :class="'s-' + d.status">{{ d.status }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Communications Log -->
      <div v-else-if="activeTab === 'communications'" class="mod-pane">
        <div v-if="loadingVcf" class="state-msg">Loading communications…</div>
        <div v-else-if="!communications.length" class="empty-tab"><div class="empty-tab__icon">💬</div><div class="empty-tab__title">No communications logged yet</div></div>
        <div v-else class="table-wrap">
          <table class="piq-table">
            <thead><tr><th>Date</th><th>Direction</th><th>Channel</th><th>Party</th><th>Subject</th></tr></thead>
            <tbody>
              <tr v-for="c in communications" :key="c.id">
                <td class="dim nowrap">{{ fmtDate(c.sent_at) }}</td>
                <td><span class="type-pill" :class="c.direction==='inbound'?'pill-in':'pill-out'">{{ c.direction }}</span></td>
                <td class="dim">{{ c.channel }}</td>
                <td class="dim">{{ c.party_type }}{{ c.party_name ? ' / ' + c.party_name : '' }}</td>
                <td class="doc-name">{{ c.subject || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- VCF Account Prep -->
      <div v-else-if="activeTab === 'account-prep'" class="mod-pane">
        <div v-if="loadingVcf" class="state-msg">Loading account prep…</div>
        <div v-else-if="!accountPrep" class="empty-tab">
          <div class="empty-tab__icon">🔐</div>
          <div class="empty-tab__title">No VCF account prep sheet</div>
          <router-link :to="'/vcf-account-prep?case_id=' + caseId" class="btn-gold sm">Create Prep Sheet</router-link>
        </div>
        <div v-else>
          <p class="dim sm">Prep sheet created {{ fmtDate(accountPrep.created_at) }} — status: {{ accountPrep.status }}</p>
        </div>
      </div>

      <!-- Stage History -->
      <div v-else-if="activeTab === 'stage-history'" class="mod-pane">
        <div v-if="loadingVcf" class="state-msg">Loading stage history…</div>
        <div v-else-if="!stageHistory.length" class="empty-tab"><div class="empty-tab__icon">📈</div><div class="empty-tab__title">No stage transitions yet</div></div>
        <div v-else class="table-wrap">
          <table class="piq-table">
            <thead><tr><th>Date</th><th>From</th><th>To</th><th>By</th><th>Note</th></tr></thead>
            <tbody>
              <tr v-for="h in stageHistory" :key="h.id">
                <td class="dim nowrap">{{ fmtDate(h.created_at) }}</td>
                <td>{{ h.from_stage || '—' }}</td>
                <td>{{ h.to_stage }}</td>
                <td class="dim">{{ h.changed_by }}</td>
                <td class="doc-name">{{ h.note || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Documents -->
      <div v-else-if="activeTab === 'documents'">
        <div v-if="!docs.length" class="empty-tab">
          <div class="empty-tab__icon">📄</div>
          <div class="empty-tab__title">No documents yet</div>
          <button class="btn-gold sm" @click="router.push('/intake')">Upload Documents</button>
        </div>
        <div v-else>
          <div class="tab-toolbar">
            <span class="dim sm">{{ docs.length }} document{{ docs.length !== 1 ? 's' : '' }}</span>
            <button class="btn-gold sm" @click="router.push('/intake')">↑ Upload More</button>
          </div>
          <div class="table-wrap">
            <table class="piq-table">
              <thead>
                <tr><th>Filename</th><th>Type</th><th>Source</th><th>Uploaded</th><th></th></tr>
              </thead>
              <tbody>
                <tr v-for="d in docs" :key="d.id">
                  <td class="doc-name">
                    <span>{{ d.document_name || d.original_filename || d.filename }}</span>
                  </td>
                  <td><span class="type-pill">{{ d.doc_type || d.document_type || '—' }}</span></td>
                  <td class="dim">{{ d.source || '—' }}</td>
                  <td class="dim nowrap">{{ fmtDate(d.upload_date || d.created_at) }}</td>
                  <td>
                    <a v-if="d.file_url" :href="`/intake/file/${d.file_url}?token=${token()}`" target="_blank" class="binder-link">View</a>
                    <span v-else class="dim">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Intake Scans -->
      <div v-else-if="activeTab === 'intake-scans'">
        <div v-if="!intakeScans.length" class="empty-tab">
          <div class="empty-tab__icon">🔍</div>
          <div class="empty-tab__title">No intake scans yet</div>
          <button class="btn-gold sm" @click="router.push('/intake')">Scan Documents</button>
        </div>
        <div v-else>
          <div class="tab-toolbar">
            <span class="dim sm">{{ intakeScans.length }} scan{{ intakeScans.length !== 1 ? 's' : '' }}</span>
            <button class="btn-gold sm" @click="router.push('/intake')">+ Scan More</button>
          </div>
          <div class="table-wrap">
            <table class="piq-table">
              <thead>
                <tr><th>Filename</th><th>Type</th><th>Engine</th><th>Words</th><th>Confidence</th><th>Scanned</th><th></th></tr>
              </thead>
              <tbody>
                <tr v-for="s in intakeScans" :key="s.id">
                  <td class="doc-name">{{ s.filename || 'Scan #' + s.id }}</td>
                  <td>
                    <span class="type-pill">{{ (s.form_fields && s.form_fields.doc_type) || s.status || 'scan' }}</span>
                  </td>
                  <td class="dim">{{ s.ocr_engine || '—' }}</td>
                  <td class="dim">{{ s.word_count || '—' }}</td>
                  <td class="dim">{{ s.confidence ? s.confidence + '%' : '—' }}</td>
                  <td class="dim nowrap">{{ fmtDate(s.created_at) }}</td>
                  <td>
                    <a v-if="s.file_url" :href="`/intake/file/${s.file_url}?token=${token()}`" target="_blank" class="binder-link">View</a>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Notes -->
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

      <!-- Contacts -->
      <div v-else-if="activeTab === 'contacts'" class="mod-pane">
        <div class="tab-toolbar">
          <span class="dim sm">{{ contacts.length }} contact{{ contacts.length !== 1 ? 's' : '' }}</span>
          <button class="btn-gold sm" @click="openAddContact({role:'VCF Claimant'})">+ Add Contact</button>
        </div>
        <div v-if="contactsLoading" class="state-msg">Loading…</div>
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
                <td><button class="del-btn" @click="deleteContact(c.id)">✕</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

    </template>

    <!-- ── Add Contact Modal ── -->
    <Teleport to="body">
      <div v-if="contactModal" class="mod-overlay" @click.self="contactModal=false">
        <div class="mod-modal">
          <div class="mod-modal__header">
            <span>Add Contact</span>
            <button class="mod-modal__close" @click="contactModal=false">✕</button>
          </div>
          <div class="mod-modal__body">
            <div class="field"><label class="field__label">Name *</label><input v-model="contactForm.name" class="piq-input w100" placeholder="Jane Smith" /></div>
            <div class="field"><label class="field__label">Role</label><input v-model="contactForm.role" class="piq-input w100" placeholder="VCF Claimant" /></div>
            <div class="field"><label class="field__label">Organization</label><input v-model="contactForm.organization" class="piq-input w100" /></div>
            <div class="field"><label class="field__label">Email</label><input v-model="contactForm.email" class="piq-input w100" type="email" /></div>
            <div class="field"><label class="field__label">Phone</label><input v-model="contactForm.phone" class="piq-input w100" /></div>
          </div>
          <div class="mod-modal__footer">
            <button class="btn-secondary" @click="contactModal=false">Cancel</button>
            <button class="btn-gold" @click="submitContact">Save</button>
          </div>
        </div>
      </div>
    </Teleport>

  </div>
</template>

<style scoped>
.mdetail { padding: 2rem; max-width: 1100px; }

.overview-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
.overview-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.25rem; }
.overview-card__title { color: var(--gold); font-size: 0.8rem; font-weight: 700; letter-spacing: 0.06em; margin: 0 0 0.75rem; text-transform: uppercase; }
.overview-field { display: flex; justify-content: space-between; align-items: center; padding: 0.4rem 0; border-bottom: 1px solid var(--border); }
.overview-field:last-child { border-bottom: none; }
.overview-field label { color: var(--text-muted); font-size: 0.75rem; }
.overview-field span { color: var(--text-primary); font-size: 0.9rem; font-weight: 500; }
.overview-actions { display: flex; align-items: center; gap: 0.75rem; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }
.overview-actions label { color: var(--text-muted); font-size: 0.8rem; }
.overview-actions select { background: var(--input-bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); padding: 0.4rem 0.6rem; }

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

/* Disbursements */
.disb-container { display: flex; flex-direction: column; gap: 1.5rem; }
.disb-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
@media (max-width: 768px) { .disb-grid { grid-template-columns: 1fr; } }
.disb-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; }
.disb-card__title { color: var(--text-primary); font-size: 1rem; font-weight: 600; margin: 0 0 1rem 0; }
.disb-field { display: flex; flex-direction: column; gap: 0.3rem; margin-bottom: 1rem; }
.disb-field label { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
.disb-disabled { opacity: 0.6; cursor: not-allowed; }
.disb-summary { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; }
.disb-summary__row { display: flex; justify-content: space-between; padding: 0.5rem 0; font-size: 0.9rem; color: var(--text-secondary); border-bottom: 1px solid var(--border); }
.disb-summary__row--net { font-size: 1.25rem; font-weight: 700; color: var(--green); border-bottom: none; padding-top: 1rem; }
.disb-status { display: flex; align-items: center; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--border); }

</style>
