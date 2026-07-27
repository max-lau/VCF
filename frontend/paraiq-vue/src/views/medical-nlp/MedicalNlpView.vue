<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const inputText = ref('')
const result    = ref(null)
const history   = ref([])
const analyzing = ref(false)
const error     = ref('')

function authHdr() {
  return { Authorization: `Bearer ${localStorage.getItem('paraiq_token')}` }
}

async function analyze() {
  if (!inputText.value.trim()) return
  analyzing.value = true
  result.value = null
  error.value = ''
  try {
    const { data } = await axios.post('/medical-nlp/analyze',
      { text: inputText.value },
      { headers: authHdr() }
    )
    result.value = data
    history.value.unshift({ text: inputText.value.slice(0, 120), ...data, at: new Date() })
    if (history.value.length > 10) history.value.pop()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || 'Analysis failed'
  } finally {
    analyzing.value = false
  }
}

function pct(v) { return Math.round((v || 0) * 100) }

function relevanceColor(score) {
  if (score >= 0.8) return '#48bb78'
  if (score >= 0.5) return '#f6ad55'
  return '#fc8181'
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

onMounted(() => {
  // optional: load history from localStorage
  try {
    const saved = localStorage.getItem('vcf_medical_nlp_history')
    if (saved) history.value = JSON.parse(saved)
  } catch {}
})
</script>

<template>
  <div class="mnlp">
    <div class="mnlp__header">
      <div>
        <h1 class="mnlp__title">Medical NLP Assistant</h1>
        <p class="mnlp__sub">
          Analyze medical records and questionnaires to surface WTC-related conditions
          and possible additional illnesses for VCF claims.
        </p>
      </div>
    </div>

    <div class="analyzer-panel">
      <div class="field">
        <label class="field-label">Medical text or questionnaire excerpt</label>
        <textarea
          v-model="inputText" rows="10" class="field-textarea"
          placeholder="Paste medical record text, diagnosis, symptoms, or claimant questionnaire excerpt…"
        ></textarea>
        <div class="char-count dim">{{ inputText.length }} characters</div>
      </div>

      <div v-if="error" class="error-banner">{{ error }}</div>

      <div class="analyze-actions">
        <button class="btn-gold" @click="analyze" :disabled="analyzing || !inputText.trim()">
          {{ analyzing ? 'Analyzing…' : '▶ Analyze Conditions' }}
        </button>
        <button class="btn-secondary" @click="inputText = ''; result = null; error = ''">Clear</button>
      </div>

      <div v-if="result" class="result-panel">
        <div class="result-header">
          <div class="result-badge" :style="{ background: relevanceColor(result.claim_relevance)+'22', color: relevanceColor(result.claim_relevance) }">
            Claim relevance {{ pct(result.claim_relevance) }}%
          </div>
          <div class="result-source dim sm">via {{ result.source }}</div>
        </div>

        <div v-if="result.conditions?.length" class="conditions-list">
          <div v-for="(c, i) in result.conditions" :key="i" class="condition-card">
            <div class="condition-top">
              <span class="condition-name">{{ c.name }}</span>
              <span class="condition-score" :style="{ color: relevanceColor(c.relevance) }">{{ pct(c.relevance) }}%</span>
            </div>
            <div class="condition-tags">
              <span v-if="c.wtc_related" class="tag tag--wtc">WTC-related</span>
              <span v-if="c.certified" class="tag tag--cert">VCF certified</span>
              <span v-if="c.actionable" class="tag tag--action">Consider claim</span>
            </div>
            <div class="condition-note dim sm">{{ c.note || 'No additional notes.' }}</div>
          </div>
        </div>

        <div v-if="result.follow_up?.length" class="follow-up">
          <div class="section-title">Suggested follow-up</div>
          <ul>
            <li v-for="(f, i) in result.follow_up" :key="i">{{ f }}</li>
          </ul>
        </div>
      </div>
    </div>

    <div v-if="history.length" class="history-section">
      <div class="section-title">Recent analyses</div>
      <div v-for="(h, i) in history" :key="i" class="history-row">
        <span class="dim sm flex-1">{{ h.text }}{{ h.text.length >= 120 ? '…' : '' }}</span>
        <span class="history-badge" :style="{ background: relevanceColor(h.claim_relevance)+'22', color: relevanceColor(h.claim_relevance) }">
          {{ pct(h.claim_relevance) }}%
        </span>
        <span class="dim sm">{{ fmtDate(h.at) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mnlp { padding: 2rem; max-width: 900px; }
.mnlp__header { margin-bottom: 1.25rem; }
.mnlp__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.mnlp__sub   { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; max-width: 700px; line-height: 1.5; }
.analyzer-panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem; }
.field { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1rem; }
.field-label { color: var(--text-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; }
.field-textarea { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 8px; color: var(--text-primary); font-family: inherit; font-size: 0.875rem; line-height: 1.6; outline: none; padding: 0.75rem 1rem; resize: vertical; }
.field-textarea:focus { border-color: var(--gold); }
.char-count { font-size: 0.72rem; text-align: right; }
.error-banner { background: rgba(252,129,129,0.12); border: 1px solid rgba(252,129,129,0.3); color: #fc8181; border-radius: 6px; padding: 0.6rem 0.9rem; margin-bottom: 1rem; font-size: 0.85rem; }
.analyze-actions { display: flex; gap: 0.75rem; }
.result-panel { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 8px; margin-top: 1.25rem; padding: 1.25rem; }
.result-header { align-items: center; display: flex; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; }
.result-badge  { border-radius: 6px; font-size: 0.85rem; font-weight: 700; padding: 0.3rem 0.75rem; }
.result-source { margin-left: auto; }
.conditions-list { display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1rem; }
.condition-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }
.condition-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
.condition-name { font-weight: 600; color: var(--text-primary); }
.condition-score { font-weight: 700; font-size: 0.9rem; }
.condition-tags { display: flex; gap: 0.4rem; margin-bottom: 0.5rem; }
.tag { font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.5rem; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.03em; }
.tag--wtc   { background: rgba(72,187,120,0.15); color: #48bb78; }
.tag--cert  { background: rgba(159,122,234,0.15); color: #9f7aea; }
.tag--action{ background: rgba(246,173,85,0.15); color: #f6ad55; }
.condition-note { line-height: 1.5; }
.follow-up ul { margin: 0.5rem 0 0 1.2rem; padding: 0; color: var(--text-secondary); font-size: 0.85rem; line-height: 1.6; }
.section-title { color: var(--text-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: .08em; margin-bottom: 0.75rem; text-transform: uppercase; }
.history-section { }
.history-row { align-items: center; border-bottom: 1px solid var(--border); display: flex; gap: 0.75rem; padding: 0.6rem 0; }
.history-badge { border-radius: 4px; font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.4rem; white-space: nowrap; flex-shrink: 0; }
.flex-1 { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.85rem; font-weight: 700; padding: 0.55rem 1.25rem; transition: opacity .15s; }
.btn-gold:hover:not(:disabled) { opacity: .85; }
.btn-gold:disabled { opacity: .45; cursor: not-allowed; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; transition: all .15s; }
.btn-secondary:hover { background: var(--bg-raised); color: var(--text-primary); }
.sm  { font-size: 0.78rem; }
.dim { color: var(--text-muted); }
</style>
