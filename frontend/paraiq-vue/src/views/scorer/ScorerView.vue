<script setup>
import { ref } from 'vue'
import client from '@/api/client'

const mode    = ref('manual')
const source  = ref('')
const summary = ref('')
const result  = ref(null)
const loading = ref(false)
const error   = ref(null)

async function score() {
  loading.value = true; error.value = null; result.value = null
  try {
    if (mode.value === 'manual') {
      const { data } = await client.post('/summary/score', {
        text: JSON.stringify({ source: source.value, summary: summary.value })
      })
      result.value = data
    } else {
      const { data } = await client.post('/summary/score/auto', { text: source.value })
      result.value = data
    }
  } catch(e) { error.value = e.response?.data?.detail || 'Scoring failed' }
  finally { loading.value = false }
}

function pct(v) { return Math.round((v || 0) * 100) }
function barColor(v) {
  const p = pct(v)
  if (p >= 80) return '#48bb78'
  if (p >= 55) return '#ecc94b'
  return '#fc8181'
}
</script>

<template>
  <div class="mod">
    <div class="mod__header">
      <div>
        <h1 class="mod__title">Summarization Scorer</h1>
        <p class="mod__sub">Evaluate summary quality against source documents</p>
      </div>
    </div>

    <!-- Mode toggle -->
    <div class="mode-bar">
      <button class="mode-btn" :class="{ active: mode === 'manual' }" @click="mode = 'manual'">
        <span class="mode-btn__label">Manual</span>
        <span class="mode-btn__sub">Provide source + summary</span>
      </button>
      <button class="mode-btn" :class="{ active: mode === 'auto' }" @click="mode = 'auto'">
        <span class="mode-btn__label">Auto</span>
        <span class="mode-btn__sub">AI generates summary</span>
      </button>
    </div>

    <div class="input-grid" :class="{ 'single': mode === 'auto' }">
      <div class="field-block">
        <label class="field-label">Source document</label>
        <textarea v-model="source" class="piq-textarea" rows="10"
          placeholder="Paste the original source document…"/>
      </div>
      <div v-if="mode === 'manual'" class="field-block">
        <label class="field-label">Summary to evaluate</label>
        <textarea v-model="summary" class="piq-textarea" rows="10"
          placeholder="Paste the summary to score…"/>
      </div>
    </div>

    <div class="submit-row">
      <button class="piq-btn-gold"
        :disabled="loading || !source.trim() || (mode === 'manual' && !summary.trim())"
        @click="score">
        {{ loading ? 'Scoring…' : 'Score Summary' }}
      </button>
    </div>

    <div v-if="error" class="err-msg">{{ error }}</div>

    <div v-if="result" class="results">

      <!-- Primary metrics -->
      <div class="metrics-row">
        <div v-for="(key, label) in { Precision: 'precision', Recall: 'recall', 'F1 Score': 'f1' }"
          :key="key" class="metric-card">
          <div class="metric-card__label">{{ label }}</div>
          <div class="metric-card__val" :style="{ color: barColor(result[key]) }">
            {{ pct(result[key]) }}<span class="metric-card__pct">%</span>
          </div>
          <div class="metric-bar-track">
            <div class="metric-bar-fill"
              :style="{ width: pct(result[key]) + '%', background: barColor(result[key]) }"/>
          </div>
        </div>
      </div>

      <!-- Sub-scores -->
      <div v-if="result.scores" class="sub-card">
        <div class="sub-card__title">Detailed Scores</div>
        <div class="sub-grid">
          <div v-for="(val, key) in result.scores" :key="key" class="sub-row">
            <span class="sub-row__name">{{ key.replace(/_/g,' ') }}</span>
            <div class="sub-bar-track">
              <div class="sub-bar-fill" :style="{ width: pct(val) + '%', background: barColor(val) }"/>
            </div>
            <span class="sub-row__val" :style="{ color: barColor(val) }">{{ pct(val) }}%</span>
          </div>
        </div>
      </div>

      <!-- Auto-generated summary -->
      <div v-if="result.summary" class="summary-card">
        <div class="summary-card__title">Generated Summary</div>
        <p class="summary-text">{{ result.summary }}</p>
      </div>

      <!-- Coverage breakdown -->
      <div v-if="result.covered || result.missed" class="cov-grid">
        <div v-if="result.covered?.length" class="cov-card cov-card--ok">
          <div class="cov-card__title">Covered</div>
          <div v-for="t in result.covered" :key="t" class="cov-item">{{ t }}</div>
        </div>
        <div v-if="result.missed?.length" class="cov-card cov-card--warn">
          <div class="cov-card__title">Missed</div>
          <div v-for="t in result.missed" :key="t" class="cov-item">{{ t }}</div>
        </div>
        <div v-if="result.added?.length" class="cov-card cov-card--bad">
          <div class="cov-card__title">Added (hallucinated)</div>
          <div v-for="t in result.added" :key="t" class="cov-item">{{ t }}</div>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.mod { padding: 2rem; max-width: 1000px; }
.mod__header { margin-bottom: 1.5rem; }
.mod__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.mod__sub   { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }

.mode-bar { display: flex; gap: .75rem; margin-bottom: 1.25rem; }
.mode-btn { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; cursor: pointer; display: flex; flex-direction: column; padding: .65rem 1.25rem; text-align: left; transition: border-color .15s; }
.mode-btn.active { border-color: var(--gold); }
.mode-btn__label { color: var(--text-primary); font-size: .875rem; font-weight: 600; }
.mode-btn__sub   { color: var(--text-muted); font-size: .72rem; margin-top: .1rem; }

.input-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: .75rem; }
.input-grid.single { grid-template-columns: 1fr; }
.field-block { display: flex; flex-direction: column; gap: .4rem; }
.field-label { font-size: .72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .05em; text-transform: uppercase; }
.piq-textarea { background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; box-sizing: border-box; color: var(--text-primary); font-family: inherit; font-size: .875rem; line-height: 1.6; padding: .75rem; resize: vertical; width: 100%; }
.piq-textarea:focus { border-color: var(--gold); outline: none; }

.submit-row { display: flex; justify-content: flex-end; margin-bottom: 1.25rem; }
.piq-btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #000; cursor: pointer; font-size: .875rem; font-weight: 600; padding: .55rem 1.4rem; transition: opacity .2s; }
.piq-btn-gold:hover:not(:disabled) { opacity: .85; }
.piq-btn-gold:disabled { cursor: not-allowed; opacity: .4; }
.err-msg { color: #fc8181; font-size: .875rem; margin-bottom: 1rem; }

.metrics-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1rem; }
.metric-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; text-align: center; }
.metric-card__label { font-size: .72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .05em; text-transform: uppercase; margin-bottom: .5rem; }
.metric-card__val   { font-size: 2.8rem; font-weight: 700; line-height: 1; margin-bottom: .75rem; }
.metric-card__pct   { font-size: 1.2rem; }
.metric-bar-track   { background: var(--border); border-radius: 99px; height: 6px; overflow: hidden; }
.metric-bar-fill    { border-radius: 99px; height: 100%; transition: width .6s ease; }

.sub-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.1rem 1.25rem; margin-bottom: 1rem; }
.sub-card__title { font-size: .72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .05em; text-transform: uppercase; margin-bottom: .85rem; }
.sub-grid { display: flex; flex-direction: column; gap: .5rem; }
.sub-row  { display: flex; align-items: center; gap: .75rem; font-size: .82rem; }
.sub-row__name { color: var(--text-muted); min-width: 140px; text-transform: capitalize; }
.sub-bar-track { background: var(--border); border-radius: 99px; flex: 1; height: 5px; overflow: hidden; }
.sub-bar-fill  { border-radius: 99px; height: 100%; transition: width .5s ease; }
.sub-row__val  { font-size: .78rem; font-weight: 600; min-width: 36px; text-align: right; }

.summary-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.1rem 1.25rem; margin-bottom: 1rem; }
.summary-card__title { font-size: .72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .05em; text-transform: uppercase; margin-bottom: .6rem; }
.summary-text { color: var(--text-primary); font-size: .875rem; line-height: 1.7; margin: 0; }

.cov-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px,1fr)); gap: 1rem; }
.cov-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.1rem; }
.cov-card--ok   { border-left: 3px solid #48bb78; border-radius: 0 8px 8px 0; }
.cov-card--warn { border-left: 3px solid #ecc94b; border-radius: 0 8px 8px 0; }
.cov-card--bad  { border-left: 3px solid #fc8181; border-radius: 0 8px 8px 0; }
.cov-card__title { font-size: .72rem; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; margin-bottom: .6rem; color: var(--text-muted); }
.cov-item { color: var(--text-muted); font-size: .8rem; padding: .2rem 0; border-bottom: 1px solid var(--border); }
.cov-item:last-child { border-bottom: none; }
</style>
