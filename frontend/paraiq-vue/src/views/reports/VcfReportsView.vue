<template>
  <div class="reports-view">
    <h1>VCF Reports</h1>

    <div class="report-grid">
      <div class="report-card">
        <h3>Claims by Stage</h3>
        <div v-if="stageLoading" class="state-msg">Loading…</div>
        <table v-else class="report-table">
          <thead><tr><th>Stage</th><th>Count</th></tr></thead>
          <tbody>
            <tr v-for="row in stages" :key="row.claim_stage">
              <td>{{ row.claim_stage.replace(/_/g, ' ') }}</td>
              <td>{{ row.cnt }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="report-card">
        <h3>Upcoming Deadlines</h3>
        <div v-if="deadlineLoading" class="state-msg">Loading…</div>
        <table v-else class="report-table">
          <thead><tr><th>Claim</th><th>Type</th><th>Due</th></tr></thead>
          <tbody>
            <tr v-for="d in deadlines" :key="d.id">
              <td>{{ d.case_number }}</td>
              <td>{{ d.deadline_type }}</td>
              <td>{{ fmtDate(d.due_date) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="report-card report-card--wide">
        <h3>Disbursements</h3>
        <button class="btn-gold sm" @click="downloadCsv">↓ Download CSV</button>
        <div v-if="disbLoading" class="state-msg">Loading…</div>
        <table v-else class="report-table">
          <thead>
            <tr>
              <th>Claim</th><th>Client</th><th>Gross</th><th>Fee</th>
              <th>Medicare</th><th>Medicaid</th><th>Net</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in disbursements" :key="d.id">
              <td>{{ d.case_number }}</td>
              <td>{{ d.client_name }}</td>
              <td>{{ fmtMoney(d.gross_award) }}</td>
              <td>{{ fmtMoney(d.attorney_fee_amount) }}</td>
              <td>{{ fmtMoney(d.medicare_lien) }}</td>
              <td>{{ fmtMoney(d.medicaid_lien) }}</td>
              <td>{{ fmtMoney(d.net_to_claimant) }}</td>
              <td>{{ d.status }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const stages = ref([])
const deadlines = ref([])
const disbursements = ref([])
const stageLoading = ref(true)
const deadlineLoading = ref(true)
const disbLoading = ref(true)

const authHdr = () => ({ Authorization: 'Bearer ' + localStorage.getItem('paraiq_token') })

function fmtMoney(v) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(v || 0)
}

function fmtDate(d) {
  return d ? new Date(d).toLocaleDateString() : '—'
}

async function loadStages() {
  try {
    const { data } = await axios.get('/reports/claims-by-stage', { headers: authHdr() })
    stages.value = data.data || []
  } finally { stageLoading.value = false }
}

async function loadDeadlines() {
  try {
    const { data } = await axios.get('/reports/overdue-deadlines?days_ahead=30', { headers: authHdr() })
    deadlines.value = data.deadlines || []
  } finally { deadlineLoading.value = false }
}

async function loadDisbursements() {
  try {
    const { data } = await axios.get('/reports/disbursements', { headers: authHdr() })
    disbursements.value = data.disbursements || []
  } finally { disbLoading.value = false }
}

function downloadCsv() {
  const token = localStorage.getItem('paraiq_token')
  window.open('/reports/disbursements?format=csv', '_blank')
}

onMounted(() => {
  loadStages()
  loadDeadlines()
  loadDisbursements()
})
</script>

<style scoped>
.reports-view { padding: 24px; }
h1 { margin: 0 0 20px; }
.report-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }
.report-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 20px; }
.report-card--wide { grid-column: 1 / -1; }
.report-card h3 { margin: 0 0 16px; display: flex; justify-content: space-between; align-items: center; }
.report-table { width: 100%; border-collapse: collapse; }
.report-table th, .report-table td { text-align: left; padding: 10px; border-bottom: 1px solid var(--border); }
.report-table th { color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; }
.state-msg { padding: 20px; text-align: center; color: var(--text-muted); }
.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-weight: 600; padding: 6px 14px; }
</style>
