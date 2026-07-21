<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const token   = () => localStorage.getItem('paraiq_token')
const authHdr = () => ({ Authorization: 'Bearer ' + token() })
const firmId  = () => { try { return JSON.parse(localStorage.getItem('paraiq_user') || '{}').firm_id || 'default' } catch { return 'default' } }

const router  = useRouter()
const cases   = ref([])
const stats   = ref(null)
const loading = ref(true)
const search  = ref('')

async function fetchStats() {
  try { const { data } = await axios.get('/cases/stats', { headers: authHdr() }); stats.value = data } catch {}
}
async function fetchCases() {
  loading.value = true
  try {
    const { data } = await axios.get('/cases/search?q=' + encodeURIComponent(search.value) + '&firm_id=' + firmId(), { headers: authHdr() })
    cases.value = data.cases || []
  } catch { cases.value = [] } finally { loading.value = false }
}

let t = null
function onSearch() { clearTimeout(t); t = setTimeout(fetchCases, 300) }

// VCF-specific color mappings
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

function fmtMoney(v) {
  return v ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0 }).format(v) : '—'
}

onMounted(() => Promise.all([fetchStats(), fetchCases()]))
</script>

<template>
  <div class="cases">
    <div class="cases__header">
      <div><h1 class="cases__title">VCF Claims</h1><p class="cases__sub">Active 9/11 Victim Compensation Fund claims</p></div>
      <button class="new-btn" @click="router.push('/matters/new')">+ New VCF Claim</button>
    </div>

    <div v-if="stats" class="stats-bar">
      <div class="stat-card"><div class="stat-val">{{ stats.total_cases }}</div><div class="stat-lbl">Total Claims</div></div>
      <div class="stat-card" v-for="(count, status) in stats.by_status" :key="status">
        <div class="stat-val" :style="{ color: vcfStatusColor(status) }">{{ count }}</div>
        <div class="stat-lbl">{{ status.charAt(0).toUpperCase() + status.slice(1) }}</div>
      </div>
      <div class="stat-card"><div class="stat-val">{{ stats.total_documents }}</div><div class="stat-lbl">Documents</div></div>
    </div>

    <div class="search-bar">
      <input v-model="search" class="piq-input" placeholder="Search claimants, claim numbers…" @input="onSearch" />
    </div>

    <div v-if="loading" class="state-msg">Loading claims…</div>
    <div v-else-if="!cases.length" class="empty-state">
      <div class="empty-state__icon">⬡</div>
      <div class="empty-state__title">No claims found</div>
      <div class="empty-state__sub">Create a new VCF claim to get started.</div>
    </div>

    <div v-else class="case-grid">
      <div v-for="c in cases" :key="c.id" class="case-card" @click="router.push('/matters/' + c.id)">
        <div class="case-card__top">
          <span class="mono dim">{{ c.case_number }}</span>
          <span class="status-pill" :style="{ background: vcfStatusColor(c.vcf_status)+'22', color: vcfStatusColor(c.vcf_status) }">{{ c.vcf_status || 'intake' }}</span>
        </div>
        <div class="case-card__client">{{ c.client_name }}</div>
        <div class="case-card__meta">
          <span class="dim">Presence: 
            <span :style="{ color: presenceColor(c.presence_proof_status) }">
              {{ c.presence_proof_status || 'missing' }}
            </span>
          </span>
          <span v-if="c.award_amount > 0" class="award-amt">{{ fmtMoney(c.award_amount) }}</span>
          <span class="dim">{{ c.doc_count || 0 }} doc{{ c.doc_count !== 1 ? 's' : '' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cases { padding: 2rem; max-width: 1400px; }
.cases__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: 1.5rem; }
.cases__title  { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.cases__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.new-btn { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1.1rem; white-space: nowrap; transition: opacity .15s; }
.new-btn:hover { opacity: .85; }
.stats-bar { display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 1.5rem; }
.stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; min-width: 110px; padding: 1rem 1.25rem; }
.stat-val  { color: var(--text-primary); font-size: 1.5rem; font-weight: 700; }
.stat-lbl  { color: var(--text-muted); font-size: 0.75rem; margin-top: 0.2rem; }
.search-bar { margin-bottom: 1.25rem; }
.piq-input  { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.875rem; outline: none; padding: 0.5rem 0.9rem; width: 100%; max-width: 400px; }
.piq-input:focus { border-color: var(--gold); }
.case-grid { display: grid; gap: 0.75rem; grid-template-columns: repeat(auto-fill, minmax(300px,1fr)); }
.case-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; cursor: pointer; padding: 1.1rem 1.25rem; transition: border-color .15s, transform .1s; }
.case-card:hover { border-color: var(--gold); transform: translateY(-1px); }
.case-card__top    { align-items: center; display: flex; justify-content: space-between; margin-bottom: 0.4rem; }
.case-card__client { color: var(--text-primary); font-size: 0.95rem; font-weight: 600; margin-bottom: 0.5rem; }
.case-card__meta   { align-items: center; display: flex; flex-wrap: wrap; gap: 0.75rem; font-size: 0.78rem; }
.status-pill { border-radius: 4px; font-size: 0.7rem; font-weight: 600; padding: 0.15rem 0.45rem; text-transform: capitalize; }
.award-amt { color: var(--green); font-weight: 700; }
.empty-state { padding: 4rem 2rem; text-align: center; }
.empty-state__icon  { color: var(--gold); font-size: 2.5rem; margin-bottom: 1rem; opacity: .4; }
.empty-state__title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; margin-bottom: 0.5rem; }
.empty-state__sub   { color: var(--text-muted); font-size: 0.875rem; }
.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
.dim  { color: var(--text-muted); }
.mono { font-family: var(--font-mono); }
</style>