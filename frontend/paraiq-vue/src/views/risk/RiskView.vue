<script setup>
import { ref } from 'vue'
import client from '@/api/client'

const text    = ref('')
const result  = ref(null)
const loading = ref(false)
const error   = ref(null)

async function score() {
  if (!text.value.trim()) return
  loading.value = true
  error.value   = null
  result.value  = null
  try {
    const { data } = await client.post('/risk/score', { text: text.value })
    result.value = data
  } catch(e) {
    error.value = e.response?.data?.detail || 'Scoring failed'
  } finally {
    loading.value = false
  }
}

function riskColor(score) {
  if (score >= 75) return '#fc8181'
  if (score >= 45) return '#ecc94b'
  return '#48bb78'
}

function riskLabel(score) {
  if (score >= 75) return 'High Risk'
  if (score >= 45) return 'Medium Risk'
  return 'Low Risk'
}
</script>

<template>
  <div class="mod">
    <div class="mod__header">
      <div>
        <h1 class="mod__title">Risk Scoring</h1>
        <p class="mod__sub">AI-powered legal risk analysis</p>
      </div>
    </div>

    <div class="input-card">
      <label class="field-label">Document text</label>
      <textarea v-model="text" class="piq-textarea" rows="8"
        placeholder="Paste contract, clause, or document text to analyse…"/>
      <div class="input-actions">
        <button class="piq-btn-gold" :disabled="loading || !text.trim()" @click="score">
          {{ loading ? 'Analysing…' : 'Score Risk' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="err-msg">{{ error }}</div>

    <div v-if="result" class="results">

      <!-- Score gauge -->
      <div class="score-card">
        <div class="score-card__label">Risk Score</div>
        <div class="score-card__val" :style="{ color: riskColor(result.risk_score) }">
          {{ result.risk_score }}
        </div>
        <div class="score-badge" :style="{ background: riskColor(result.risk_score)+'22', color: riskColor(result.risk_score) }">
          {{ riskLabel(result.risk_score) }}
        </div>
        <div class="score-bar-track">
          <div class="score-bar-fill"
            :style="{ width: result.risk_score + '%', background: riskColor(result.risk_score) }"/>
        </div>
      </div>

      <div class="results-grid">
        <!-- Category breakdown -->
        <div class="res-card" v-if="result.categories">
          <div class="res-card__title">Category Breakdown</div>
          <div v-for="(val, cat) in result.categories" :key="cat" class="cat-row">
            <span class="cat-row__name">{{ cat }}</span>
            <div class="cat-bar-track">
              <div class="cat-bar-fill" :style="{ width: val + '%', background: riskColor(val) }"/>
            </div>
            <span class="cat-row__val" :style="{ color: riskColor(val) }">{{ val }}</span>
          </div>
        </div>

        <!-- Signals -->
        <div class="res-card" v-if="result.risk_signals?.length">
          <div class="res-card__title">Top Risk Signals</div>
          <div v-for="s in result.risk_signals" :key="s" class="signal-row signal-row--risk">
            <span class="signal-dot" style="background:#fc8181"/>{{ s }}
          </div>
        </div>

        <!-- Mitigating factors -->
        <div class="res-card" v-if="result.mitigating_factors?.length">
          <div class="res-card__title">Mitigating Factors</div>
          <div v-for="s in result.mitigating_factors" :key="s" class="signal-row signal-row--ok">
            <span class="signal-dot" style="background:#48bb78"/>{{ s }}
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.mod { padding: 2rem; max-width: 900px; }
.mod__header { margin-bottom: 1.5rem; }
.mod__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.mod__sub   { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }

.input-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem; }
.field-label { font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; display: block; margin-bottom: 0.5rem; }
.piq-textarea { background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-family: inherit; font-size: 0.875rem; line-height: 1.6; padding: 0.75rem; resize: vertical; width: 100%; box-sizing: border-box; }
.piq-textarea:focus { border-color: var(--gold); outline: none; }
.input-actions { display: flex; justify-content: flex-end; margin-top: 0.75rem; }
.piq-btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #000; cursor: pointer; font-size: 0.875rem; font-weight: 600; padding: 0.55rem 1.4rem; transition: opacity .2s; }
.piq-btn-gold:hover:not(:disabled) { opacity: .85; }
.piq-btn-gold:disabled { cursor: not-allowed; opacity: .4; }

.err-msg { color: #fc8181; font-size: 0.875rem; margin-bottom: 1rem; }

.score-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; margin-bottom: 1.25rem; text-align: center; }
.score-card__label { font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: .5rem; }
.score-card__val   { font-size: 3.5rem; font-weight: 700; line-height: 1; margin-bottom: .5rem; }
.score-badge { display: inline-block; border-radius: 4px; font-size: 0.78rem; font-weight: 600; padding: .2rem .7rem; margin-bottom: 1rem; }
.score-bar-track { background: var(--border); border-radius: 99px; height: 8px; margin: 0 auto; max-width: 300px; overflow: hidden; }
.score-bar-fill  { border-radius: 99px; height: 100%; transition: width .6s ease; }

.results-grid { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fill, minmax(260px,1fr)); }
.res-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.1rem 1.25rem; }
.res-card__title { font-size: 0.72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .05em; margin-bottom: .85rem; text-transform: uppercase; }

.cat-row { align-items: center; display: flex; gap: .65rem; margin-bottom: .5rem; font-size: .8rem; }
.cat-row__name { color: var(--text-muted); min-width: 90px; text-transform: capitalize; }
.cat-bar-track { background: var(--border); border-radius: 99px; flex: 1; height: 5px; overflow: hidden; }
.cat-bar-fill  { border-radius: 99px; height: 100%; }
.cat-row__val  { font-size: .75rem; font-weight: 600; min-width: 24px; text-align: right; }

.signal-row { align-items: flex-start; display: flex; font-size: .82rem; gap: .5rem; margin-bottom: .45rem; color: var(--text-muted); }
.signal-dot { border-radius: 50%; flex-shrink: 0; height: 7px; margin-top: 5px; width: 7px; }
</style>
