<script setup>
import { ref, computed } from 'vue'
import client from '@/api/client'
import NlpResultCard from '@/components/ui/NlpResultCard.vue'

const text = ref('')
const result = ref(null)
const loading = ref(false)
const error = ref(null)
const copied = ref(false)

const SAMPLE = `This Settlement Agreement ("Agreement") is entered into as of March 14, 2025, by and between Acme Holdings, Inc., a Delaware corporation with principal offices at 120 Market Street, San Francisco, CA 94105 ("Acme"), and Mr. David Chen, an individual residing at 88 Oak Avenue, Austin, TX 78701 ("Chen").

WHEREAS, on January 9, 2024, Chen filed a complaint in the Superior Court of California, County of San Francisco, Case No. CGC-24-304721, alleging wrongful termination and seeking damages of not less than $850,000;

WHEREAS, Acme denies any and all liability and enters into this Agreement solely to avoid the cost and uncertainty of litigation;

NOW, THEREFORE, in consideration of the mutual promises herein, the parties agree as follows:

1. Payment. Acme shall pay Chen the sum of $425,000 within thirty (30) days of the Effective Date.
2. Release. Chen hereby releases Acme from all claims arising out of or relating to his employment.
3. Confidentiality. The terms of this Agreement shall remain confidential.`

const wordCount = computed(() => {
  const t = text.value.trim()
  if (!t) return 0
  return t.split(/\s+/).filter(Boolean).length
})

const charCount = computed(() => text.value.length)

async function analyze() {
  if (!text.value.trim()) return
  loading.value = true
  error.value = null
  result.value = null
  try {
    const { data } = await client.post('/analyze', { text: text.value })
    result.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Analysis failed — please try again.'
  } finally {
    loading.value = false
  }
}

function clearAll() {
  text.value = ''
  result.value = null
  error.value = null
  copied.value = false
}

function loadExample() {
  text.value = SAMPLE
  result.value = null
  error.value = null
}

async function copyResult() {
  if (!result.value) return
  try {
    await navigator.clipboard.writeText(JSON.stringify(result.value, null, 2))
    copied.value = true
    setTimeout(() => (copied.value = false), 1800)
  } catch {
    error.value = 'Clipboard unavailable in this browser.'
  }
}
</script>

<template>
  <div class="nlp-mod">
    <div class="nlp-mod__header">
      <h1 class="nlp-mod__title">Document Analyzer</h1>
      <p class="nlp-mod__sub">Full NLP analysis — entities, sentiment, clauses &amp; classification</p>
    </div>

    <div class="nlp-input-card">
      <div class="nlp-field-row">
        <label class="nlp-field-label">Document text</label>
        <span class="nlp-counter" :class="{ 'nlp-counter--active': wordCount > 0 }">
          {{ wordCount.toLocaleString() }} words · {{ charCount.toLocaleString() }} chars
        </span>
      </div>
      <textarea
        v-model="text"
        class="nlp-textarea"
        rows="12"
        placeholder="Paste legal document text to analyze…"
      />
      <div class="nlp-input-actions">
        <button class="nlp-btn nlp-btn--ghost" :disabled="!text && !result" @click="clearAll">
          Clear
        </button>
        <button class="nlp-btn nlp-btn--ghost" @click="loadExample">Load example</button>
        <button
          v-if="result"
          class="nlp-btn nlp-btn--ghost"
          @click="copyResult"
        >
          {{ copied ? '✓ Copied' : 'Copy result' }}
        </button>
        <button
          class="nlp-btn"
          :disabled="loading || !text.trim()"
          @click="analyze"
        >
          {{ loading ? 'Analysing…' : 'Analyze' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="nlp-progress">
      <span class="nlp-progress__bar" />
      <span class="nlp-progress__label">Running analysis…</span>
    </div>

    <div v-if="error" class="nlp-err">{{ error }}</div>

    <NlpResultCard v-if="result" :result="result" title="Analysis Result" />
  </div>
</template>

<style scoped>
.nlp-mod { padding: 2rem; max-width: 920px; }
.nlp-mod__header { margin-bottom: 1.5rem; }
.nlp-mod__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.nlp-mod__sub { color: var(--text-muted); font-size: .85rem; margin: .25rem 0 0; }

.nlp-input-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem; }
.nlp-field-row { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: .5rem; gap: 1rem; }
.nlp-field-label { font-size: .72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; font-weight: 600; }
.nlp-counter { font-size: .72rem; color: var(--text-muted); font-family: var(--font-mono); opacity: .6; transition: opacity .2s; }
.nlp-counter--active { opacity: 1; color: var(--gold); }
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
.nlp-progress__label { letter-spacing: .03em; }
@keyframes nlp-spin { to { transform: rotate(360deg); } }

.nlp-err { color: #fc8181; font-size: .875rem; margin-bottom: 1rem; background: rgba(252,129,129,.07); border: 1px solid rgba(252,129,129,.25); border-radius: 6px; padding: .6rem .8rem; }
</style>
