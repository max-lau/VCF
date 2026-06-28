<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import client from '@/api/client'

const router = useRouter()

const query       = ref('')
const results     = ref([])
const loading     = ref(false)
const error       = ref(null)
const hasSearched = ref(false)
const caseFilter  = ref(null)
const minScore    = ref(0.3)
const topK        = ref(10)

const indexStatus = ref(null)
const indexing     = ref(false)

async function search() {
  if (!query.value.trim()) return
  loading.value = true
  error.value = null
  results.value = []
  hasSearched.value = true

  try {
    const body = {
      query: query.value,
      top_k: topK.value,
      min_score: minScore.value,
    }
    if (caseFilter.value) body.case_id = caseFilter.value

    const { data } = await client.post('/search/semantic', body)
    results.value = data.results || []
  } catch (e) {
    error.value = e.response?.data?.detail || 'Search failed. Is the document index built?'
  } finally {
    loading.value = false
  }
}

async function fetchIndexStatus() {
  try {
    const { data } = await client.get('/search/status')
    indexStatus.value = data
  } catch { indexStatus.value = null }
}

async function indexCurrentCase() {
  if (!caseFilter.value) return
  indexing.value = true
  try {
    const { data } = await client.post('/search/index', { case_id: caseFilter.value, force: true })
    indexStatus.value = { ...indexStatus.value, indexed: data.chunks_created }
    await search()
  } catch (e) {
    error.value = e.response?.data?.detail || 'Indexing failed'
  } finally {
    indexing.value = false
  }
}

function scoreColor(score) {
  if (score >= 0.75) return '#48bb78'
  if (score >= 0.5)  return '#ecc94b'
  if (score >= 0.35) return '#ed8936'
  return '#718096'
}

function scoreLabel(score) {
  if (score >= 0.75) return 'Strong match'
  if (score >= 0.5)  return 'Good match'
  if (score >= 0.35) return 'Possible match'
  return 'Weak match'
}

function riskColor(r) {
  return { low: '#48bb78', medium: '#ecc94b', high: '#fc8181', unknown: '#718096' }[r] || '#718096'
}

function openCase(caseId) {
  if (caseId) router.push(`/matters/${caseId}`)
}

fetchIndexStatus()
</script>

<template>
  <div class="search-page">
    <!-- Header -->
    <div class="search-header">
      <div>
        <h1 class="search-title">Semantic Search</h1>
        <p class="search-sub">Find documents by meaning across all case matter — not just keyword matching</p>
      </div>
      <div v-if="indexStatus" class="index-badge">
        <span class="index-badge__dot" :class="{ 'index-badge__dot--active': indexStatus.index_total > 0 }"></span>
        {{ indexStatus.index_total || 0 }} chunks indexed · {{ indexStatus.firm_documents || 0 }} documents available
      </div>
    </div>

    <!-- Search Bar -->
    <div class="search-card">
      <div class="search-input-row">
        <input
          v-model="query"
          class="search-input"
          placeholder="Search by meaning — e.g. 'merger agreement termination clauses' or 'emails about the Q3 deadline'"
          @keydown.enter="search"
        />
        <button class="search-btn" :disabled="loading || !query.trim()" @click="search">
          {{ loading ? 'Searching…' : 'Search' }}
        </button>
      </div>

      <div class="search-filters">
        <div class="filter-group">
          <label class="filter-label">Case filter</label>
          <input v-model="caseFilter" type="number" class="filter-input" placeholder="Case ID (optional)" />
        </div>
        <div class="filter-group">
          <label class="filter-label">Min relevance: {{ Math.round(minScore * 100) }}%</label>
          <input v-model.number="minScore" type="range" min="0.2" max="0.9" step="0.05" class="filter-range" />
        </div>
        <div class="filter-group">
          <label class="filter-label">Max results</label>
          <select v-model.number="topK" class="filter-select">
            <option :value="5">5</option>
            <option :value="10">10</option>
            <option :value="20">20</option>
            <option :value="50">50</option>
          </select>
        </div>
        <button v-if="caseFilter" class="index-btn" :disabled="indexing" @click="indexCurrentCase">
          {{ indexing ? 'Indexing…' : 'Re-index Case' }}
        </button>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="error-banner">
      <span class="error-icon">⚠</span>
      {{ error }}
    </div>

    <!-- Loading -->
    <div v-if="loading" class="state-msg">
      <div class="spinner"></div>
      Searching documents…
    </div>

    <!-- Empty State -->
    <div v-else-if="hasSearched && results.length === 0" class="empty-state">
      <div class="empty-icon">🔍</div>
      <div class="empty-title">No results found</div>
      <div class="empty-sub">
        Try lowering the minimum relevance threshold, or index your case documents first.
      </div>
      <button v-if="caseFilter" class="index-btn" :disabled="indexing" @click="indexCurrentCase">
        {{ indexing ? 'Indexing…' : 'Index This Case' }}
      </button>
    </div>

    <!-- Results -->
    <div v-else-if="results.length > 0" class="results-section">
      <div class="results-meta">{{ results.length }} document{{ results.length !== 1 ? 's' : '' }} found</div>

      <div
        v-for="r in results"
        :key="r.doc_id"
        class="result-card"
        @click="openCase(r.case_id)"
      >
        <div class="result-card__header">
          <div class="result-card__title-group">
            <span class="result-card__doc">{{ r.document_name }}</span>
            <span class="result-card__case">{{ r.case_number }} · {{ r.client_name }}</span>
          </div>
          <div class="result-card__score">
            <div class="score-bar">
              <div class="score-bar__fill" :style="{ width: Math.round(r.score * 100) + '%', background: scoreColor(r.score) }"></div>
            </div>
            <span class="score-label" :style="{ color: scoreColor(r.score) }">{{ Math.round(r.score * 100) }}% · {{ scoreLabel(r.score) }}</span>
          </div>
        </div>

        <div class="result-card__snippet">{{ r.snippet }}</div>

        <div class="result-card__meta">
          <span v-if="r.court" class="meta-tag">⚖ {{ r.court }}</span>
          <span class="meta-tag" :style="{ color: riskColor(r.risk_level) }">● {{ r.risk_level || 'unknown' }} risk</span>
          <span v-if="r.source" class="meta-tag">📂 {{ r.source }}</span>
          <span class="meta-tag meta-tag--click">View case →</span>
        </div>
      </div>
    </div>

    <!-- Initial state -->
    <div v-else class="initial-state">
      <div class="initial-icon">🧠</div>
      <div class="initial-title">Search by meaning, not keywords</div>
      <div class="initial-sub">
        Semantic search understands context — try phrases like "contractual obligations after termination"
        or "communications about the acquisition deadline" instead of exact keyword matches.
      </div>
      <div class="examples">
        <div class="example-label">Try searching for:</div>
        <button class="example-chip" @click="query = 'non-compete agreement restrictions'; search()">Non-compete agreement restrictions</button>
        <button class="example-chip" @click="query = 'emails about the filing deadline'; search()">Emails about the filing deadline</button>
        <button class="example-chip" @click="query = 'financial discrepancies in Q3 report'; search()">Financial discrepancies in Q3 report</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.search-page { padding: 2rem; max-width: 1100px; margin: 0 auto; }

.search-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem; }
.search-title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.search-sub { color: var(--text-muted); font-size: .85rem; margin: .25rem 0 0; }

.index-badge { display: flex; align-items: center; gap: .5rem; background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; padding: .4rem .75rem; font-size: .75rem; color: var(--text-muted); }
.index-badge__dot { width: 8px; height: 8px; border-radius: 50%; background: #718096; }
.index-badge__dot--active { background: #48bb78; }

.search-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; margin-bottom: 1.5rem; }
.search-input-row { display: flex; gap: .75rem; margin-bottom: 1rem; }
.search-input { flex: 1; background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 8px; color: var(--text-primary); font-size: .9rem; padding: .65rem .85rem; }
.search-input:focus { border-color: var(--gold); outline: none; }
.search-btn { background: var(--gold); border: none; border-radius: 8px; color: #000; cursor: pointer; font-size: .875rem; font-weight: 600; padding: .65rem 1.5rem; transition: opacity .2s; }
.search-btn:hover:not(:disabled) { opacity: .85; }
.search-btn:disabled { opacity: .4; cursor: not-allowed; }

.search-filters { display: flex; gap: 1rem; flex-wrap: wrap; align-items: flex-end; }
.filter-group { display: flex; flex-direction: column; gap: .25rem; }
.filter-label { font-size: .7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .04em; }
.filter-input, .filter-select { background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: .8rem; padding: .4rem .5rem; width: 130px; }
.filter-range { width: 130px; accent-color: var(--gold); }
.index-btn { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: .75rem; padding: .4rem .75rem; transition: border-color .2s; align-self: flex-end; }
.index-btn:hover:not(:disabled) { border-color: var(--gold); color: var(--gold); }

.error-banner { display: flex; align-items: center; gap: .5rem; background: rgba(252, 129, 129, .1); border: 1px solid rgba(252, 129, 129, .3); border-radius: 8px; padding: .75rem 1rem; color: #fc8181; font-size: .85rem; margin-bottom: 1.5rem; }

.state-msg { display: flex; align-items: center; gap: .75rem; color: var(--text-muted); font-size: .9rem; padding: 2rem; justify-content: center; }
.spinner { width: 18px; height: 18px; border: 2px solid var(--border); border-top-color: var(--gold); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.empty-state { text-align: center; padding: 3rem 1rem; }
.empty-icon { font-size: 2.5rem; margin-bottom: .75rem; }
.empty-title { font-size: 1.1rem; color: var(--text-primary); margin-bottom: .25rem; }
.empty-sub { color: var(--text-muted); font-size: .85rem; margin-bottom: 1rem; }

.results-section { display: flex; flex-direction: column; gap: .75rem; }
.results-meta { color: var(--text-muted); font-size: .78rem; margin-bottom: .25rem; }

.result-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.25rem; cursor: pointer; transition: border-color .15s, transform .15s; }
.result-card:hover { border-color: var(--gold); transform: translateY(-1px); }
.result-card__header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: .5rem; }
.result-card__title-group { display: flex; flex-direction: column; gap: .15rem; }
.result-card__doc { font-size: .9rem; font-weight: 600; color: var(--text-primary); }
.result-card__case { font-size: .75rem; color: var(--text-muted); }
.result-card__score { display: flex; flex-direction: column; align-items: flex-end; gap: .25rem; min-width: 120px; }
.score-bar { width: 100px; height: 4px; background: var(--bg-raised, #0d0d1a); border-radius: 2px; overflow: hidden; }
.score-bar__fill { height: 100%; border-radius: 2px; transition: width .3s; }
.score-label { font-size: .7rem; font-weight: 600; }
.result-card__snippet { color: var(--text-muted); font-size: .82rem; line-height: 1.5; margin-bottom: .5rem; }
.result-card__meta { display: flex; gap: .75rem; flex-wrap: wrap; }
.meta-tag { font-size: .7rem; color: var(--text-muted); }
.meta-tag--click { color: var(--gold); margin-left: auto; }

.initial-state { text-align: center; padding: 3rem 1rem; }
.initial-icon { font-size: 3rem; margin-bottom: .75rem; }
.initial-title { font-size: 1.15rem; color: var(--text-primary); margin-bottom: .5rem; }
.initial-sub { color: var(--text-muted); font-size: .85rem; max-width: 480px; margin: 0 auto 1.5rem; line-height: 1.5; }
.examples { display: flex; flex-direction: column; gap: .5rem; align-items: center; }
.example-label { font-size: .72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .04em; }
.example-chip { background: var(--bg-card); border: 1px solid var(--border); border-radius: 20px; color: var(--text-primary); cursor: pointer; font-size: .78rem; padding: .4rem .85rem; transition: border-color .2s, color .2s; }
.example-chip:hover { border-color: var(--gold); color: var(--gold); }
</style>
