<script setup>
import { ref, computed } from 'vue'
import client from '@/api/client'
import NlpResultCard from '@/components/ui/NlpResultCard.vue'

const witnessName = ref('')
const text = ref('')
const result = ref(null)
const loading = ref(false)
const error = ref(null)

const SAMPLE = `On the evening of June 3rd I was at home watching television. I did not leave the house until the following morning. I have never met the defendant before. We have never been introduced. I am certain the car was red. Actually, I think it might have been dark blue. I cannot recall the exact time but it was around 9 PM. No, it was closer to 11 PM. I am absolutely sure of that.`

function pct(v) { return Math.round((v || 0) * 100) }

const overall = computed(() => {
  if (!result.value) return 0
  return pct(result.value.overall_score ?? result.value.score ?? result.value.credibility_score ?? 0)
})

function bandColor(p) {
  if (p > 70) return '#48bb78'
  if (p >= 40) return '#ecc94b'
  return '#fc8181'
}
function bandLabel(p) {
  if (p > 70) return 'High credibility'
  if (p >= 40) return 'Moderate credibility'
  return 'Low credibility'
}
const gaugeColor = computed(() => bandColor(overall.value))
const gaugeLabel = computed(() => bandLabel(overall.value))

// Circular gauge: circumference of r=52 → 2πr ≈ 326.7
const R = 52
const CIRC = 2 * Math.PI * R
const dashOffset = computed(() => CIRC * (1 - overall.value / 100))

async function score() {
  if (!text.value.trim()) return
  loading.value = true
  error.value = null
  result.value = null
  try {
    const payload = { text: text.value }
    if (witnessName.value.trim()) payload.witness_name = witnessName.value.trim()
    const { data } = await client.post('/credibility/score', payload)
    result.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Scoring failed — please try again.'
  } finally {
    loading.value = false
  }
}

function loadExample() {
  text.value = SAMPLE
  result.value = null
  error.value = null
}

function clearAll() {
  text.value = ''
  witnessName.value = ''
  result.value = null
  error.value = null
}
</script>

<template>
  <div class="nlp-mod">
    <div class="nlp-mod__header">
      <h1 class="nlp-mod__title">Credibility Scorer</h1>
      <p class="nlp-mod__sub">AI-powered witness testimony &amp; document credibility analysis</p>
    </div>

    <div class="nlp-input-card">
      <label class="nlp-field-label">Witness name <span class="nlp-opt">(optional)</span></label>
      <input
        v-model="witnessName"
        type="text"
        class="nlp-input"
        placeholder="e.g. John Smith"
      />
      <label class="nlp-field-label nlp-field-label--mt">Testimony or document text</label>
      <textarea
        v-model="text"
        class="nlp-textarea"
        rows="10"
        placeholder="Paste witness testimony transcript or document…"
      />
      <div class="nlp-input-actions">
        <button class="nlp-btn nlp-btn--ghost" :disabled="!text && !result && !witnessName" @click="clearAll">
          Clear
        </button>
        <button class="nlp-btn nlp-btn--ghost" @click="loadExample">Load example</button>
        <button
          class="nlp-btn"
          :disabled="loading || !text.trim()"
          @click="score"
        >
          {{ loading ? 'Scoring…' : 'Score Credibility' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="nlp-progress">
      <span class="nlp-progress__bar" />
      <span class="nlp-progress__label">Scoring testimony…</span>
    </div>

    <div v-if="error" class="nlp-err">{{ error }}</div>

    <div v-if="result" class="nlp-results">
      <div class="nlp-gauge-card">
        <div class="nlp-gauge">
          <svg viewBox="0 0 120 120" class="nlp-gauge__svg">
            <circle cx="60" cy="60" :r="R" fill="none" stroke="var(--border)" stroke-width="9" />
            <circle
              cx="60" cy="60" :r="R" fill="none"
              :stroke="gaugeColor" stroke-width="9" stroke-linecap="round"
              :stroke-dasharray="CIRC" :stroke-dashoffset="dashOffset"
              transform="rotate(-90 60 60)"
              class="nlp-gauge__fill"
            />
          </svg>
          <div class="nlp-gauge__center">
            <div class="nlp-gauge__val" :style="{ color: gaugeColor }">{{ overall }}<span class="nlp-gauge__pct">%</span></div>
            <div class="nlp-gauge__band" :style="{ color: gaugeColor }">{{ gaugeLabel }}</div>
          </div>
        </div>
        <div v-if="witnessName" class="nlp-gauge-card__witness">
          Witness: <strong>{{ witnessName }}</strong>
        </div>
      </div>

      <NlpResultCard :result="result" title="Detailed Credibility Breakdown" />
    </div>
  </div>
</template>

<style scoped>
.nlp-mod { padding: 2rem; max-width: 920px; }
.nlp-mod__header { margin-bottom: 1.5rem; }
.nlp-mod__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.nlp-mod__sub { color: var(--text-muted); font-size: .85rem; margin: .25rem 0 0; }

.nlp-input-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem; }
.nlp-field-label { font-size: .72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; font-weight: 600; display: block; margin-bottom: .4rem; }
.nlp-field-label--mt { margin-top: 1rem; }
.nlp-opt { font-weight: 400; opacity: .6; text-transform: none; letter-spacing: 0; }
.nlp-input { background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; box-sizing: border-box; color: var(--text-primary); font-family: inherit; font-size: .875rem; padding: .55rem .75rem; width: 100%; }
.nlp-input:focus { border-color: var(--gold); outline: none; }
.nlp-textarea { background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; box-sizing: border-box; color: var(--text-primary); font-family: inherit; font-size: .875rem; line-height: 1.6; padding: .75rem; resize: vertical; width: 100%; }
.nlp-textarea:focus { border-color: var(--gold); outline: none; }

.nlp-input-actions { display: flex; justify-content: flex-end; gap: .5rem; margin-top: .75rem; flex-wrap: wrap; }
.nlp-btn { background: var(--gold); border: none; border-radius: 6px; color: #000; cursor: pointer; font-size: .875rem; font-weight: 600; padding: .55rem 1.4rem; transition: opacity .2s; }
.nlp-btn:hover:not(:disabled) { opacity: .85; }
.nlp-btn:disabled { cursor: not-allowed; opacity: .4; }
.nlp-btn--ghost { background: transparent; border: 1px solid var(--border); color: var(--text-muted); }
.nlp-btn--ghost:hover:not(:disabled) { border-color: var(--gold); color: var(--gold); opacity: 1; }

.nlp-progress { display: flex; align-items: center; gap: .75rem; margin-bottom: 1.25rem; color: var(--text-muted); font-size: .8rem; }
.nlp-progress__bar { width: 14px; height: 14px; border: 2px solid var(--gold); border-top-color: transparent; border-radius: 50%; animation: nlp-spin .7s linear infinite; }
@keyframes nlp-spin { to { transform: rotate(360deg); } }

.nlp-err { color: #fc8181; font-size: .875rem; margin-bottom: 1rem; background: rgba(252,129,129,.07); border: 1px solid rgba(252,129,129,.25); border-radius: 6px; padding: .6rem .8rem; }

.nlp-results { display: flex; flex-direction: column; gap: 1rem; }
.nlp-gauge-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.75rem; display: flex; flex-direction: column; align-items: center; gap: .5rem; }
.nlp-gauge { position: relative; width: 180px; height: 180px; }
.nlp-gauge__svg { width: 100%; height: 100%; }
.nlp-gauge__fill { transition: stroke-dashoffset .8s ease; }
.nlp-gauge__center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.nlp-gauge__val { font-size: 2.6rem; font-weight: 700; line-height: 1; }
.nlp-gauge__pct { font-size: 1.2rem; }
.nlp-gauge__band { font-size: .74rem; font-weight: 600; margin-top: .35rem; letter-spacing: .03em; }
.nlp-gauge-card__witness { color: var(--text-muted); font-size: .8rem; margin-top: .25rem; }
.nlp-gauge-card__witness strong { color: var(--text-primary); }
</style>
