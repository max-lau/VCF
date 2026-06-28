<script setup>
import { ref } from 'vue'
import client from '@/api/client'
import NlpResultCard from '@/components/ui/NlpResultCard.vue'

const text = ref('')

// Per-analysis state
const coref     = ref(null)
const disambig  = ref(null)
const contradict = ref(null)

const loadingCoref      = ref(false)
const loadingDisambig   = ref(false)
const loadingContradict = ref(false)

const errorCoref      = ref(null)
const errorDisambig   = ref(null)
const errorContradict = ref(null)

const analyses = [
  { key: 'coreference', label: 'Coreference Resolution', icon: '⬡', endpoint: '/coreference',        resultRef: () => coref,      loadRef: () => loadingCoref,      errRef: () => errorCoref },
  { key: 'disambig',    label: 'Entity Disambiguation', icon: '◈', endpoint: '/disambiguate',         resultRef: () => disambig,   loadRef: () => loadingDisambig,   errRef: () => errorDisambig },
  { key: 'contradict',   label: 'Contradiction Scan',    icon: '⚠', endpoint: '/contradictions/scan', resultRef: () => contradict, loadRef: () => loadingContradict, errRef: () => errorContradict },
]

const anyLoading = () => loadingCoref.value || loadingDisambig.value || loadingContradict.value

async function runAnalysis(key) {
  if (!text.value.trim()) return
  const a = analyses.find(x => x.key === key)
  if (!a) return
  // set loading + clear state for that analysis
  if (key === 'coreference') { loadingCoref.value = true; errorCoref.value = null; coref.value = null }
  if (key === 'disambig')    { loadingDisambig.value = true; errorDisambig.value = null; disambig.value = null }
  if (key === 'contradict')  { loadingContradict.value = true; errorContradict.value = null; contradict.value = null }
  try {
    const { data } = await client.post(a.endpoint, { text: text.value })
    if (key === 'coreference')      coref.value = data
    else if (key === 'disambig')     disambig.value = data
    else if (key === 'contradict')   contradict.value = data
  } catch (e) {
    const msg = e.response?.data?.detail || 'Analysis failed'
    if (key === 'coreference')      errorCoref.value = msg
    else if (key === 'disambig')     errorDisambig.value = msg
    else if (key === 'contradict')   errorContradict.value = msg
  } finally {
    if (key === 'coreference')      loadingCoref.value = false
    else if (key === 'disambig')     loadingDisambig.value = false
    else if (key === 'contradict')   loadingContradict.value = false
  }
}

async function runAll() {
  if (!text.value.trim()) return
  // Run all three in parallel; each manages its own loading state
  await Promise.allSettled([
    runAnalysis('coreference'),
    runAnalysis('disambig'),
    runAnalysis('contradict'),
  ])
}

function clearAll() {
  coref.value = disambig.value = contradict.value = null
  errorCoref.value = errorDisambig.value = errorContradict.value = null
}
</script>

<template>
  <div class="nlp-mod" style="max-width:1000px">
    <div class="nlp-mod__header nlp-mod__header--split">
      <div>
        <h1 class="nlp-mod__title">Document Insights</h1>
        <p class="nlp-mod__sub">Coreference, disambiguation, and contradiction scanning</p>
      </div>
      <button class="nlp-btn" :disabled="anyLoading() || !text.trim()" @click="runAll">
        {{ anyLoading() ? 'Running…' : 'Run All' }}
      </button>
    </div>

    <div class="nlp-input-card">
      <label class="nlp-field-label">Document text</label>
      <textarea v-model="text" class="nlp-textarea" rows="10"
        placeholder="Paste document for deep analysis…" />
    </div>

    <!-- Per-analysis run buttons -->
    <div class="ins-run-row">
      <button v-for="a in analyses" :key="a.key"
        class="nlp-btn--outline"
        :disabled="a.loadRef().value || !text.trim()"
        @click="runAnalysis(a.key)">
        <span class="ins-run-icon">{{ a.icon }}</span>
        {{ a.loadRef().value ? 'Running…' : a.label }}
      </button>
    </div>

    <!-- Results grid -->
    <div class="ins-grid">
      <div class="ins-cell">
        <NlpResultCard v-if="coref" :result="coref" title="Coreference Resolution" />
        <div v-else-if="loadingCoref" class="ins-loading">Analysing coreference…</div>
        <div v-else-if="errorCoref" class="nlp-err">{{ errorCoref }}</div>
        <div v-else class="ins-placeholder">
          <span class="ins-placeholder__icon">⬡</span>
          <span>Run Coreference Resolution to see results</span>
        </div>
      </div>

      <div class="ins-cell">
        <NlpResultCard v-if="disambig" :result="disambig" title="Entity Disambiguation" />
        <div v-else-if="loadingDisambig" class="ins-loading">Analysing entities…</div>
        <div v-else-if="errorDisambig" class="nlp-err">{{ errorDisambig }}</div>
        <div v-else class="ins-placeholder">
          <span class="ins-placeholder__icon">◈</span>
          <span>Run Entity Disambiguation to see results</span>
        </div>
      </div>

      <div class="ins-cell">
        <NlpResultCard v-if="contradict" :result="contradict" title="Contradiction Scan" />
        <div v-else-if="loadingContradict" class="ins-loading">Scanning for contradictions…</div>
        <div v-else-if="errorContradict" class="nlp-err">{{ errorContradict }}</div>
        <div v-else class="ins-placeholder">
          <span class="ins-placeholder__icon">⚠</span>
          <span>Run Contradiction Scan to see results</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ins-run-row {
  display: flex; flex-wrap: wrap; gap: .6rem;
  margin-bottom: 1.25rem;
}
.ins-run-row .nlp-btn--outline { display: inline-flex; align-items: center; gap: .4rem; }
.ins-run-icon { font-size: .9rem; opacity: .8; }

.ins-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1rem;
}
.ins-cell { display: flex; flex-direction: column; }
.ins-loading {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px;
  color: var(--text-muted); font-size: .85rem; padding: 1.5rem; text-align: center;
  animation: ins-pulse 1.4s ease-in-out infinite;
}
@keyframes ins-pulse { 0%,100% { opacity: 1; } 50% { opacity: .55; } }
.ins-placeholder {
  background: var(--bg-card); border: 1px dashed var(--border); border-radius: 8px;
  color: var(--text-muted); font-size: .82rem; padding: 1.5rem;
  display: flex; flex-direction: column; align-items: center; gap: .5rem;
  text-align: center; min-height: 120px; justify-content: center;
}
.ins-placeholder__icon { font-size: 1.4rem; opacity: .5; }
</style>
