<script setup>
import { ref, onMounted } from 'vue'
import client from '@/api/client'


const inputText  = ref('')
const result     = ref(null)
const history    = ref([])
const status     = ref(null)
const analyzing  = ref(false)

async function checkStatus() {
  try { const { data } = await client.get('/legal-bert/status'); status.value = data } catch {}
}

async function analyze() {
  if (!inputText.value.trim()) return
  analyzing.value = true; result.value = null
  try {
    const { data } = await client.post('/legal-bert/analyze',
      { text: inputText.value, analysis_type: 'classification' },
      { headers: authHdr() }
    )
    result.value = data
    history.value.unshift(data)
    if (history.value.length > 10) history.value.pop()
  } catch {} finally { analyzing.value = false }
}

function pct(v) { return Math.round((v || 0) * 100) }

function labelColor(l) {
  const m = { employment:'#4a7cf7', contract_dispute:'#ecc94b', tort:'#fc8181', IP:'#9f7aea', real_estate:'#48bb78', criminal:'#c9a84c', other:'#718096' }
  return m[l] || '#718096'
}

onMounted(checkStatus)
</script>

<template>
  <div class="bert">
    <div class="bert__header">
      <div>
        <h1 class="bert__title">Legal-BERT Analysis</h1>
        <p class="bert__sub">AI-powered legal text classification and analysis</p>
      </div>
    </div>

    <div v-if="status" class="status-bar" :class="status.mode === 'enclave' ? 'online' : 'heuristic'">
      <span>◉</span>
      {{ status.mode === 'enclave' ? 'Legal-BERT Enclave Online' : 'Heuristic Mode — Set ENCLAVE_LEGAL_BERT_URL to enable full model' }}
    </div>

    <div class="analyzer-panel">
      <div class="field">
        <label class="field-label">Text to Analyze</label>
        <textarea
          v-model="inputText" rows="8" class="field-textarea"
          placeholder="Paste case text, clause, or document excerpt for classification…"
        ></textarea>
        <div class="char-count dim">{{ inputText.length }} characters</div>
      </div>
      <div class="analyze-actions">
        <button class="btn-gold" @click="analyze" :disabled="analyzing || !inputText.trim()">
          {{ analyzing ? 'Analyzing…' : '▶ Analyze Text' }}
        </button>
        <button class="btn-secondary" @click="inputText = ''; result = null">Clear</button>
      </div>

      <div v-if="result" class="result-panel">
        <div class="result-header">
          <div class="result-label" :style="{ background: labelColor(result.result?.label)+'22', color: labelColor(result.result?.label) }">
            {{ result.result?.label?.replace(/_/g, ' ') || 'unknown' }}
          </div>
          <div class="result-conf">{{ pct(result.result?.confidence) }}% confidence</div>
          <div class="result-source dim sm">via {{ result.source }}</div>
        </div>
        <div v-if="result.result?.all_scores" class="score-bars">
          <div v-for="(score, cat) in result.result.all_scores" :key="cat" class="score-row">
            <div class="score-label dim sm">{{ cat.replace(/_/g,' ') }}</div>
            <div class="score-bar-wrap">
              <div class="score-bar-fill" :style="{ width: pct(score)+'%', background: labelColor(cat) }"></div>
            </div>
            <div class="score-pct dim sm">{{ pct(score) }}%</div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="history.length" class="history-section">
      <div class="section-title">Recent Analyses</div>
      <div v-for="(h, i) in history" :key="i" class="history-row">
        <span class="history-label" :style="{ background: labelColor(h.result?.label)+'22', color: labelColor(h.result?.label) }">
          {{ h.result?.label }}
        </span>
        <span class="dim sm flex-1">{{ h.text_snippet }}</span>
        <span class="dim sm">{{ pct(h.result?.confidence) }}%</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bert { padding: 2rem; max-width: 860px; }
.bert__header { margin-bottom: 1.25rem; }
.bert__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.bert__sub   { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.status-bar  { align-items: center; border-radius: 6px; display: flex; font-size: 0.78rem; gap: 0.5rem; margin-bottom: 1.25rem; padding: 0.5rem 0.9rem; }
.status-bar.online    { background: rgba(72,187,120,.1); border: 1px solid rgba(72,187,120,.3); color: #48bb78; }
.status-bar.heuristic { background: rgba(236,201,75,.1); border: 1px solid rgba(236,201,75,.3); color: #ecc94b; }
.analyzer-panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem; }
.field { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1rem; }
.field-label { color: var(--text-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; }
.field-textarea { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 8px; color: var(--text-primary); font-family: inherit; font-size: 0.875rem; line-height: 1.6; outline: none; padding: 0.75rem 1rem; resize: vertical; }
.field-textarea:focus { border-color: var(--gold); }
.char-count { font-size: 0.72rem; text-align: right; }
.analyze-actions { display: flex; gap: 0.75rem; }
.result-panel { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 8px; margin-top: 1.25rem; padding: 1.25rem; }
.result-header { align-items: center; display: flex; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; }
.result-label  { border-radius: 6px; font-size: 0.9rem; font-weight: 700; padding: 0.3rem 0.75rem; text-transform: capitalize; }
.result-conf   { color: var(--text-primary); font-size: 0.9rem; font-weight: 600; }
.score-bars { display: flex; flex-direction: column; gap: 0.5rem; }
.score-row  { align-items: center; display: flex; gap: 0.75rem; }
.score-label { min-width: 140px; text-transform: capitalize; }
.score-bar-wrap { background: rgba(255,255,255,.05); border-radius: 3px; flex: 1; height: 6px; overflow: hidden; }
.score-bar-fill { border-radius: 3px; height: 100%; transition: width .4s; }
.score-pct  { min-width: 36px; text-align: right; }
.history-section { }
.section-title { color: var(--text-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: .08em; margin-bottom: 0.75rem; text-transform: uppercase; }
.history-row { align-items: center; border-bottom: 1px solid var(--border); display: flex; gap: 0.75rem; padding: 0.6rem 0; }
.history-label { border-radius: 4px; font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.4rem; text-transform: capitalize; white-space: nowrap; flex-shrink: 0; }
.flex-1 { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.85rem; font-weight: 700; padding: 0.55rem 1.25rem; transition: opacity .15s; }
.btn-gold:hover:not(:disabled) { opacity: .85; }
.btn-gold:disabled { opacity: .45; cursor: not-allowed; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; transition: all .15s; }
.btn-secondary:hover { background: var(--bg-raised); color: var(--text-primary); }
.sm  { font-size: 0.78rem; }
.dim { color: var(--text-muted); }
</style>
