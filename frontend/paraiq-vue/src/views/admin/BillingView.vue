<template>
  <div class="piq-page">
    <div class="piq-page-header">
      <h2 class="piq-page-title">💳 Client Billing</h2>
      <p class="piq-page-subtitle">Invoices, payments, and billing rates</p>
    </div>

    <!-- Summary stats -->
    <div class="bl-stats">
      <div v-for="s in statusSummary" :key="s.label" class="bl-stat">
        <div class="bl-stat__value">{{ s.count }}</div>
        <div class="bl-stat__label">{{ s.label }}</div>
        <div class="bl-stat__amount">${{ s.total.toFixed(2) }}</div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="bl-tabs">
      <button v-for="t in tabs" :key="t.key"
        :class="['bl-tab', { 'bl-tab--active': activeTab === t.key }]"
        @click="activeTab = t.key">
        {{ t.label }}
      </button>
    </div>

    <!-- Invoices Tab -->
    <div v-if="activeTab === 'invoices'">
      <div class="bl-toolbar">
        <select v-model="filterStatus" class="piq-input bl-filter">
          <option value="">All statuses</option>
          <option v-for="s in STATUSES" :key="s" :value="s">{{ fmtStatus(s) }}</option>
        </select>
        <button class="piq-btn piq-btn--primary piq-btn--sm" @click="showCreateModal = true">
          + New Invoice
        </button>
      </div>

      <div v-if="invoicesLoading" class="piq-loading">Loading…</div>
      <div v-else-if="!filteredInvoices.length" class="piq-empty-state">
        <span style="font-size:28px">📄</span>
        <p>No invoices yet. Click "New Invoice" to generate one from certified time entries.</p>
      </div>
      <div v-else class="table-wrap">
        <table class="piq-table">
          <thead>
            <tr>
              <th>Invoice #</th>
              <th>Client / Matter</th>
              <th>Issue Date</th>
              <th>Due Date</th>
              <th>Total</th>
              <th>Balance</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="inv in filteredInvoices" :key="inv.id">
              <td class="mono">{{ inv.invoice_number }}</td>
              <td>
                <div class="bl-matter">
                  <span class="bl-client">{{ inv.client_name }}</span>
                  <span class="bl-case">{{ inv.case_number }}</span>
                </div>
              </td>
              <td class="dim nowrap">{{ inv.issue_date?.slice(0,10) }}</td>
              <td class="nowrap" :class="isOverdue(inv) ? 'bl-overdue' : ''">
                {{ inv.due_date?.slice(0,10) }}
                <span v-if="isOverdue(inv)" class="bl-overdue-tag">OVERDUE</span>
              </td>
              <td class="dim">${{ parseFloat(inv.total || 0).toFixed(2) }}</td>
              <td :class="parseFloat(inv.balance_due) <= 0 ? 'bl-paid' : 'bl-balance'">
                ${{ parseFloat(inv.balance_due || 0).toFixed(2) }}
              </td>
              <td>
                <span class="bl-status-pill" :class="`bl-status--${inv.status}`">
                  {{ fmtStatus(inv.status) }}
                </span>
              </td>
              <td>
                <div class="bl-actions">
                  <button class="bl-action-btn" title="Download PDF"
                    @click="downloadPdf(inv.id, inv.invoice_number)">⬇ PDF</button>
                  <button v-if="inv.status === 'draft'" class="bl-action-btn bl-action-btn--gold"
                    @click="advanceStatus(inv.id, 'pending_certification')">Certify →</button>
                  <button v-if="inv.status === 'pending_certification'" class="bl-action-btn bl-action-btn--gold"
                    @click="advanceStatus(inv.id, 'certified')">✓ Certify</button>
                  <button v-if="inv.status === 'certified'" class="bl-action-btn bl-action-btn--blue"
                    @click="advanceStatus(inv.id, 'sent')">📤 Send</button>
                  <button v-if="['sent','viewed','partially_paid','overdue'].includes(inv.status)"
                    class="bl-action-btn bl-action-btn--green"
                    @click="openPayment(inv)">💰 Payment</button>
                  <button v-if="inv.status !== 'void' && inv.status !== 'paid'"
                    class="bl-action-btn bl-action-btn--red"
                    @click="advanceStatus(inv.id, 'void')">Void</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Billing Rates Tab -->
    <div v-if="activeTab === 'rates'">
      <div class="bl-toolbar">
        <span class="dim" style="font-size:13px">Attorney billing rates — used for time capture and invoice generation</span>
        <button class="piq-btn piq-btn--primary piq-btn--sm" @click="showRateModal = true">+ Set Rate</button>
      </div>
      <div v-if="!rates.length" class="piq-empty-state">
        <p>No billing rates set. Click "Set Rate" to configure.</p>
      </div>
      <div v-else class="table-wrap">
        <table class="piq-table">
          <thead>
            <tr><th>User</th><th>Role</th><th>Rate</th><th>Currency</th><th>Effective From</th><th>Notes</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in rates" :key="r.id">
              <td class="bl-client">{{ r.username }}</td>
              <td><span class="type-pill">{{ r.role_type }}</span></td>
              <td class="bl-rate">${{ parseFloat(r.hourly_rate).toFixed(2) }}/hr</td>
              <td class="dim">{{ r.currency }}</td>
              <td class="dim">{{ r.effective_from?.slice(0,10) }}</td>
              <td class="dim">{{ r.notes || "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Create Invoice Modal -->
    <div v-if="showCreateModal" class="bl-modal-overlay">
      <div class="bl-modal">
        <div class="bl-modal__header">
          <span class="bl-modal__title">📄 New Invoice</span>
          <button class="bl-modal__close" @click="showCreateModal = false">✕</button>
        </div>
        <div class="bl-modal__body">
          <label class="bl-label">Matter / Case</label>
          <select v-model.number="newInv.matter_id" class="piq-input">
            <option value="">Select a matter…</option>
            <option v-for="m in matters" :key="m.id" :value="m.id">
              {{ m.case_number }} — {{ m.client_name }}
            </option>
          </select>
          <label class="bl-label">Billing Period Start</label>
          <input v-model="newInv.billing_period_start" type="date" class="piq-input" />
          <label class="bl-label">Billing Period End</label>
          <input v-model="newInv.billing_period_end" type="date" class="piq-input" />
          <label class="bl-label">Due Date</label>
          <input v-model="newInv.due_date" type="date" class="piq-input" />
          <label class="bl-label">Tax Rate (%)</label>
          <input v-model.number="newInv.tax_rate_pct" type="number" min="0" max="100" step="0.1" class="piq-input" placeholder="0" />
          <label class="bl-label">Payment Terms</label>
          <select v-model="newInv.payment_terms" class="piq-input">
            <option>Net 15</option><option>Net 30</option><option>Net 45</option><option>Due on Receipt</option>
          </select>
          <label class="bl-label">Notes</label>
          <textarea v-model="newInv.notes" class="piq-input" rows="2" placeholder="Optional notes…" />
        </div>
        <div class="bl-modal__footer">
          <button class="piq-btn piq-btn--ghost" @click="showCreateModal = false">Cancel</button>
          <button class="piq-btn piq-btn--primary" @click="createInvoice" :disabled="creating">
            {{ creating ? "Creating…" : "Generate Invoice" }}
          </button>
        </div>
      </div>
    </div>

    <!-- Record Payment Modal -->
    <div v-if="showPaymentModal" class="bl-modal-overlay">
      <div class="bl-modal">
        <div class="bl-modal__header">
          <span class="bl-modal__title">💰 Record Payment — {{ paymentInv?.invoice_number }}</span>
          <button class="bl-modal__close" @click="showPaymentModal = false">✕</button>
        </div>
        <div class="bl-modal__body">
          <div class="bl-payment-due">Balance due: <strong>${{ parseFloat(paymentInv?.balance_due || 0).toFixed(2) }}</strong></div>
          <label class="bl-label">Amount</label>
          <input v-model.number="payment.amount" type="number" min="0" step="0.01" class="piq-input" />
          <label class="bl-label">Payment Date</label>
          <input v-model="payment.payment_date" type="date" class="piq-input" />
          <label class="bl-label">Method</label>
          <select v-model="payment.method" class="piq-input">
            <option>check</option><option>wire</option><option>ach</option><option>credit_card</option><option>cash</option><option>other</option>
          </select>
          <label class="bl-label">Reference #</label>
          <input v-model="payment.reference" class="piq-input" placeholder="Check number, wire ref, etc." />
          <label class="bl-label">Notes</label>
          <textarea v-model="payment.notes" class="piq-input" rows="2" />
        </div>
        <div class="bl-modal__footer">
          <button class="piq-btn piq-btn--ghost" @click="showPaymentModal = false">Cancel</button>
          <button class="piq-btn piq-btn--success" @click="recordPayment" :disabled="paying">
            {{ paying ? "Recording…" : "Record Payment" }}
          </button>
        </div>
      </div>
    </div>

    <!-- Set Rate Modal -->
    <div v-if="showRateModal" class="bl-modal-overlay">
      <div class="bl-modal">
        <div class="bl-modal__header">
          <span class="bl-modal__title">⚙️ Set Billing Rate</span>
          <button class="bl-modal__close" @click="showRateModal = false">✕</button>
        </div>
        <div class="bl-modal__body">
          <label class="bl-label">User ID</label>
          <input v-model.number="newRate.user_id" type="number" class="piq-input" />
          <label class="bl-label">Username</label>
          <input v-model="newRate.username" class="piq-input" />
          <label class="bl-label">Role Type</label>
          <select v-model="newRate.role_type" class="piq-input">
            <option>attorney</option><option>paralegal</option>
          </select>
          <label class="bl-label">Hourly Rate ($)</label>
          <input v-model.number="newRate.hourly_rate" type="number" min="0" step="0.01" class="piq-input" />
          <label class="bl-label">Effective From</label>
          <input v-model="newRate.effective_from" type="date" class="piq-input" />
          <label class="bl-label">Notes</label>
          <input v-model="newRate.notes" class="piq-input" placeholder="Optional" />
        </div>
        <div class="bl-modal__footer">
          <button class="piq-btn piq-btn--ghost" @click="showRateModal = false">Cancel</button>
          <button class="piq-btn piq-btn--primary" @click="saveRate" :disabled="savingRate">
            {{ savingRate ? "Saving…" : "Save Rate" }}
          </button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue"

const token   = () => localStorage.getItem("paraiq_token")
const authHdr = () => ({ Authorization: "Bearer " + token() })

const activeTab       = ref("invoices")
const invoicesLoading = ref(true)
const invoices        = ref([])
const rates           = ref([])
const filterStatus    = ref("")
const showCreateModal = ref(false)
const showPaymentModal = ref(false)
const showRateModal   = ref(false)
const creating        = ref(false)
const paying          = ref(false)
const savingRate      = ref(false)
const matters         = ref([])
const paymentInv      = ref(null)

const STATUSES = ["draft","pending_certification","certified","sent","viewed","partially_paid","paid","overdue","disputed","void"]

const tabs = [
  { key: "invoices", label: "📄 Invoices" },
  { key: "rates",    label: "⚙️ Billing Rates" },
]

const newInv = ref({ matter_id: null, billing_period_start: "", billing_period_end: "", due_date: "", tax_rate_pct: 0, payment_terms: "Net 30", notes: "" })
const payment = ref({ amount: 0, payment_date: new Date().toISOString().slice(0,10), method: "check", reference: "", notes: "" })
const newRate = ref({ user_id: null, username: "", role_type: "attorney", hourly_rate: 850, effective_from: new Date().toISOString().slice(0,10), notes: "" })

const filteredInvoices = computed(() =>
  filterStatus.value ? invoices.value.filter(i => i.status === filterStatus.value) : invoices.value
)

const statusSummary = computed(() => {
  const groups = {}
  for (const inv of invoices.value) {
    if (!groups[inv.status]) groups[inv.status] = { count: 0, total: 0, outstanding: 0 }
    groups[inv.status].count++
    groups[inv.status].total += parseFloat(inv.total || 0)
    groups[inv.status].outstanding += parseFloat(inv.balance_due || 0)
  }
  return Object.entries(groups).map(([status, d]) => ({
    label: fmtStatus(status), ...d
  }))
})

async function fetchAll() {
  invoicesLoading.value = true
  try {
    const [invRes, dashRes, matRes] = await Promise.all([
      fetch("/billing/invoices", { headers: authHdr() }).then(r => r.json()),
      fetch("/billing/dashboard", { headers: authHdr() }).then(r => r.json()),
      fetch("/cases/search?limit=100", { headers: authHdr() }).then(r => r.json()).catch(() => ({ cases: [] })),
    ])
    invoices.value = invRes.invoices || []
    rates.value    = dashRes.billing_rates || []
    matters.value  = matRes.cases || []
  } catch(e) { console.error(e) }
  finally { invoicesLoading.value = false }
}

async function createInvoice() {
  if (!newInv.value.matter_id) return alert("Matter ID is required")
  creating.value = true
  try {
    const body = {
      matter_id:            newInv.value.matter_id,
      billing_period_start: newInv.value.billing_period_start || null,
      billing_period_end:   newInv.value.billing_period_end || null,
      due_date:             newInv.value.due_date || null,
      tax_rate:             (newInv.value.tax_rate_pct || 0) / 100,
      payment_terms:        newInv.value.payment_terms,
      notes:                newInv.value.notes || null,
    }
    const res = await fetch("/billing/invoices", {
      method: "POST",
      headers: { ...authHdr(), "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
    if (!res.ok) throw new Error(await res.text())
    showCreateModal.value = false
    newInv.value = { matter_id: null, billing_period_start: "", billing_period_end: "", due_date: "", tax_rate_pct: 0, payment_terms: "Net 30", notes: "" }
    await fetchAll()
  } catch(e) { alert("Failed: " + e.message) }
  finally { creating.value = false }
}

async function advanceStatus(id, status) {
  const labels = { pending_certification: "submit for certification", certified: "certify", sent: "mark as sent", void: "void" }
  if (!confirm(`Are you sure you want to ${labels[status] || status} this invoice?`)) return
  await fetch(`/billing/invoices/${id}/status`, {
    method: "PATCH",
    headers: { ...authHdr(), "Content-Type": "application/json" },
    body: JSON.stringify({ status })
  })
  await fetchAll()
}

async function downloadPdf(id, number) {
  const res = await fetch(`/billing/invoices/${id}/pdf`, { headers: authHdr() })
  if (!res.ok) return alert("PDF generation failed")
  const blob = await res.blob()
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement("a")
  a.href = url; a.download = `invoice_${number}.pdf`; a.click()
  URL.revokeObjectURL(url)
}

function openPayment(inv) {
  paymentInv.value = inv
  payment.value = { amount: parseFloat(inv.balance_due || 0), payment_date: new Date().toISOString().slice(0,10), method: "check", reference: "", notes: "" }
  showPaymentModal.value = true
}

async function recordPayment() {
  paying.value = true
  try {
    const res = await fetch(`/billing/invoices/${paymentInv.value.id}/payments`, {
      method: "POST",
      headers: { ...authHdr(), "Content-Type": "application/json" },
      body: JSON.stringify(payment.value)
    })
    if (!res.ok) throw new Error(await res.text())
    showPaymentModal.value = false
    await fetchAll()
  } catch(e) { alert("Failed: " + e.message) }
  finally { paying.value = false }
}

async function saveRate() {
  savingRate.value = true
  try {
    const res = await fetch("/billing/rates", {
      method: "POST",
      headers: { ...authHdr(), "Content-Type": "application/json" },
      body: JSON.stringify(newRate.value)
    })
    if (!res.ok) throw new Error(await res.text())
    showRateModal.value = false
    await fetchAll()
  } catch(e) { alert("Failed: " + e.message) }
  finally { savingRate.value = false }
}

function fmtStatus(s) {
  return s.replace(/_/g, " ").replace(/\w/g, c => c.toUpperCase())
}

function isOverdue(inv) {
  return inv.status === "overdue" ||
    (["sent","viewed","partially_paid"].includes(inv.status) && new Date(inv.due_date) < new Date())
}

onMounted(fetchAll)
</script>

<style scoped>
.bl-stats         { display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-bottom:20px; }
.bl-stat          { background:var(--surface-card);border:1px solid var(--border);border-radius:10px;padding:14px; }
.bl-stat__value   { font-size:22px;font-weight:700;color:var(--text-primary); }
.bl-stat__label   { font-size:11px;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em;margin:2px 0; }
.bl-stat__amount  { font-size:13px;color:#34d399;font-weight:600; }
.bl-tabs          { display:flex;gap:4px;border-bottom:1px solid var(--border);margin-bottom:16px; }
.bl-tab           { padding:8px 16px;font-size:13px;color:var(--text-secondary);border:none;background:none;cursor:pointer;border-bottom:2px solid transparent;transition:all .15s; }
.bl-tab--active   { color:var(--text-primary);border-bottom-color:var(--accent);font-weight:600; }
.bl-toolbar       { display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px; }
.bl-filter        { width:180px;padding:6px 10px;font-size:12px; }
.bl-matter        { display:flex;flex-direction:column;gap:2px; }
.bl-client        { font-size:13px;font-weight:600;color:var(--text-primary); }
.bl-case          { font-size:11px;color:var(--text-tertiary); }
.bl-rate          { font-size:13px;font-weight:700;color:#34d399; }
.bl-balance       { font-weight:700;color:#fbbf24; }
.bl-paid          { color:#34d399;font-weight:700; }
.bl-overdue       { color:#f87171; }
.bl-overdue-tag   { font-size:10px;font-weight:700;background:rgba(239,68,68,.15);color:#f87171;padding:1px 5px;border-radius:4px;margin-left:4px; }
.bl-actions       { display:flex;gap:4px;flex-wrap:wrap; }
.bl-action-btn    { padding:3px 8px;font-size:11px;border-radius:5px;border:1px solid var(--border);background:var(--surface);color:var(--text-secondary);cursor:pointer;white-space:nowrap; }
.bl-action-btn:hover       { background:var(--surface-hover); }
.bl-action-btn--gold       { border-color:rgba(201,168,76,.4);color:#C9A84C; }
.bl-action-btn--blue       { border-color:rgba(99,102,241,.4);color:#818cf8; }
.bl-action-btn--green      { border-color:rgba(16,185,129,.4);color:#34d399; }
.bl-action-btn--red        { border-color:rgba(239,68,68,.3);color:#f87171; }
.bl-status-pill   { display:inline-block;padding:2px 8px;border-radius:8px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em; }
.bl-status--draft              { background:rgba(107,114,128,.15);color:#9ca3af; }
.bl-status--pending_certification { background:rgba(245,158,11,.15);color:#fbbf24; }
.bl-status--certified          { background:rgba(99,102,241,.15);color:#818cf8; }
.bl-status--sent               { background:rgba(59,130,246,.15);color:#60a5fa; }
.bl-status--viewed             { background:rgba(139,92,246,.15);color:#a78bfa; }
.bl-status--partially_paid     { background:rgba(16,185,129,.1);color:#34d399; }
.bl-status--paid               { background:rgba(16,185,129,.2);color:#34d399;border:1px solid rgba(16,185,129,.4); }
.bl-status--overdue            { background:rgba(239,68,68,.15);color:#f87171; }
.bl-status--disputed           { background:rgba(245,158,11,.15);color:#fbbf24; }
.bl-status--void               { background:rgba(107,114,128,.1);color:#6b7280;text-decoration:line-through; }
.bl-modal-overlay { position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:1000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px); }
.bl-modal         { background:var(--surface-card);border:1px solid var(--border);border-radius:12px;padding:24px;width:480px;max-width:95vw;max-height:90vh;overflow-y:auto; }
.bl-modal__header { display:flex;align-items:center;justify-content:space-between;margin-bottom:16px; }
.bl-modal__title  { font-size:15px;font-weight:700;color:var(--text-primary); }
.bl-modal__close  { background:none;border:none;color:var(--text-tertiary);cursor:pointer;font-size:16px; }
.bl-modal__body   { display:flex;flex-direction:column;gap:8px; }
.bl-modal__footer { display:flex;justify-content:flex-end;gap:10px;margin-top:16px;padding-top:12px;border-top:1px solid var(--border); }
.bl-label         { font-size:12px;color:var(--text-tertiary);margin-bottom:2px; }
.bl-payment-due   { font-size:13px;color:var(--text-secondary);margin-bottom:8px;padding:8px;background:var(--surface);border-radius:6px; }
.piq-btn--success { background:rgba(16,185,129,.15);color:#34d399;border:1px solid rgba(16,185,129,.3); }
.piq-btn--success:hover { background:rgba(16,185,129,.25); }
</style>
