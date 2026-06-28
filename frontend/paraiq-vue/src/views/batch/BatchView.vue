<script setup>
import { ref, computed } from 'vue'
import client from '@/api/client'
import NlpResultCard from '@/components/ui/NlpResultCard.vue'

const texts = ref('')
const results = ref([])
const loading = ref(false)
const error = ref(null)
const progress = ref(0)
const csvFile = ref(null)
const csvName = ref('')

function parseDocuments(raw) {
  // Each line is a separate document, OR multi-line blocks separated by --- on its own line.
  if (raw.includes('\n---\n') || raw.trim() === '---') {
    return raw.split(/\n---\n/).map(t => t.trim()).filter(Boolean)
  }
  return raw.split(/\n/).map(t => t.trim()).filter(Boolean)
}

const docCount = computed(() => parseDocuments(texts.value).length)

function onCsv(e) {
  const f = e.target.files?.[0]
  if (!f) return
  csvFile.value = f
  csvName.value = f.name
  error.value = null
}

async function runBatch() {
  const items = parseDocuments(texts.value)
  if (!items.length) return
  loading.value = true
  error.value = null
  results.value = []
  progress.value = 0
  try {
    progress.value = 15
    const { data } = await client.post('/analyze/batch', { texts: items })
    progress.value = 90
    results.value = data.results || data || []
  } catch (e) {
    error.value = e.response?.data?.detail || 'Batch analysis failed — please try again.'
  } finally {
    progress.value = 100
    loading.value = false
    setTimeout(() => (progress.value = 0), 800)
  }
}

async function runCsv() {
  if (!csvFile.value) return
  loading.value = true
  error.value = null
  results.value = []
  progress.value = 0
  try {
    const form = new FormData()
    form.append('file', csvFile.value)
    progress.value = 15
    const { data } = await client.post('/analyze/batch/csv', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    progress.value = 90
    results.value = data.results || data || []
  } catch (e) {
    error.value = e.response?.data?.detail || 'CSV upload failed — please try again.'
  } finally {
    progress.value = 100
    loading.value = false
    setTimeout(() => (progress.value = 0), 800)
  }
}

function clearAll() {
  texts.value = ''
  results.value = []
  error.value = null
  csvFile.value = null
  csvName.value = ''
}

function exportJson() {
  if (!results.value.length) return
  const blob = new Blob([JSON.stringify(results.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `batch-results-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="nlp-mod">
    <div class="nlp-mod__header">
      <h1 class="nlp-mod__title">Batch Analyzer</h1>
      <p class="nlp-mod__sub">
        Multiple documents — one per line, or multi-line blocks separated by
        <code class="nlp-code">---</code> on its own line
      </p>
    </div>

    <div class="nlp-input-card">
      <div class="nlp-field-row">
        <label class="nlp-field-label">Documents</label>
        <span class="nlp-counter" :class="{ 'nlp-counter--active': docCount > 0 }">
          {{ docCount }} document{{ docCount === 1 ? '' : 's' }} detected
        </span>
      </div>
      <textarea
        v-model="texts"
        class="nlp-textarea"
        rows="12"
        placeholder="First document text&#10;Second document text&#10;---&#10;Or a multi-line document&#10;spanning several lines&#10;---&#10;Third document"
      />
      <div class="nlp-input-actions">
        <button class="nlp-btn nlp-btn--ghost" :disabled="!texts && !results.length" @click="clearAll">
          Clear
        </button>
        <button
          v-if="results.length"
          class="nlp-btn nlp-btn--ghost"
          @click="exportJson"
        >
          ↓ Export JSON
        </button>
        <button
          class="nlp-btn"
          :disabled="loading || !texts.trim()"
          @click="runBatch"
        >
          {{ loading ? 'Processing…' : 'Run Batch' }}
        </button>
      </div>
    </div>

    <div class="nlp-input-card">
      <label class="nlp-field-label">Upload CSV</label>
      <div class="nlp-csv-row">
        <label class="nlp-file-btn">
          <input type="file" accept=".csv,text/csv" @change="onCsv" />
          Choose file
        </label>
        <span class="nlp-file-name">{{ csvName || 'No file selected' }}</span>
        <button
          class="nlp-btn"
          :disabled="loading || !csvFile"
          @click="runCsv"
        >
          {{ loading ? 'Uploading…' : 'Analyze CSV' }}
        </button>
      </div>
    </div>

    <div v-if="loading || progress > 0" class="nlp-progress">
      <div class="nlp-progress__track">
        <div class="nlp-progress__fill" :style="{ width: progress + '%' }" />
      </div>
      <span class="nlp-progress__label">{{ progress < 100 ? 'Processing batch…' : 'Done' }}</span>
    </div>

    <div v-if="error" class="nlp-err">{{ error }}</div>

    <div v-if="results.length" class="nlp-results">
      <div class="nlp-results__head">
        <span class="nlp-results__label">{{ results.length }} result{{ results.length === 1 ? '' : 's' }}</span>
        <button class="nlp-btn nlp-btn--ghost nlp-btn--sm" @click="exportJson">↓ Export JSON</button>
      </div>
      <div v-for="(r, i) in results" :key="i" class="nlp-result-item">
        <div class="nlp-result-item__index">{{ i + 1 }}</div>
        <NlpResultCard :result="r" :title="`Document ${i + 1}`" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.nlp-mod { padding: 2rem; max-width: 960px; }
.nlp-mod__header { margin-bottom: 1.5rem; }
.nlp-mod__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.nlp-mod__sub { color: var(--text-muted); font-size: .85rem; margin: .25rem 0 0; }
.nlp-code { font-family: var(--font-mono); color: var(--gold); background: rgba(201,168,76,.1); padding: .05rem .3rem; border-radius: 3px; font-size: .82rem; }

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
.nlp-btn--sm { font-size: .78rem; padding: .35rem .9rem; }

.nlp-csv-row { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; margin-top: .5rem; }
.nlp-file-btn { display: inline-flex; align-items: center; background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: .8rem; font-weight: 600; padding: .5rem .9rem; transition: border-color .15s, color .15s; }
.nlp-file-btn:hover { border-color: var(--gold); color: var(--gold); }
.nlp-file-btn input { display: none; }
.nlp-file-name { color: var(--text-muted); font-size: .8rem; font-family: var(--font-mono); }

.nlp-progress { display: flex; align-items: center; gap: .75rem; margin-bottom: 1.25rem; }
.nlp-progress__track { flex: 1; height: 6px; background: var(--border); border-radius: 99px; overflow: hidden; }
.nlp-progress__fill { height: 100%; background: var(--gold); border-radius: 99px; transition: width .4s ease; }
.nlp-progress__label { color: var(--text-muted); font-size: .78rem; white-space: nowrap; }

.nlp-err { color: #fc8181; font-size: .875rem; margin-bottom: 1rem; background: rgba(252,129,129,.07); border: 1px solid rgba(252,129,129,.25); border-radius: 6px; padding: .6rem .8rem; }

.nlp-results { display: flex; flex-direction: column; gap: 1rem; }
.nlp-results__head { display: flex; align-items: center; justify-content: space-between; }
.nlp-results__label { font-size: .78rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .06em; font-weight: 600; }
.nlp-result-item { display: flex; gap: .75rem; align-items: flex-start; }
.nlp-result-item__index { flex-shrink: 0; width: 26px; height: 26px; border-radius: 50%; background: var(--gold); color: #000; font-size: .75rem; font-weight: 700; display: flex; align-items: center; justify-content: center; margin-top: .35rem; }
.nlp-result-item :deep(.rc) { flex: 1; min-width: 0; }
</style>
