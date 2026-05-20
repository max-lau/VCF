<script setup>
import { ref } from 'vue'
import client from '@/api/client'
import NlpResultCard from '@/components/ui/NlpResultCard.vue'

const texts = ref(''), results = ref([]), loading = ref(false), error = ref(null), csvMode = ref(false)

async function runBatch() {
  loading.value = true; error.value = null; results.value = []
  const items = texts.value.split('\n---\n').map(t => t.trim()).filter(Boolean)
  try {
    if (csvMode.value) {
      const { data } = await client.post('/analyze/batch/csv', { texts: items })
      const url = URL.createObjectURL(new Blob([data], { type: 'text/csv' }))
      Object.assign(document.createElement('a'), { href: url, download: 'batch-results.csv' }).click()
    } else {
      const { data } = await client.post('/analyze/batch', { texts: items })
      results.value = data.results || data || []
    }
  } catch (e) { error.value = e.response?.data?.detail || 'Batch failed' }
  finally     { loading.value = false }
}
</script>
<template>
  <div class="nlp-mod">
    <div class="nlp-mod__header">
      <h1 class="nlp-mod__title">Batch Analyzer</h1>
      <p class="nlp-mod__sub">Multiple documents — separate with <code class="nlp-code">---</code> on its own line</p>
    </div>
    <div class="nlp-input-card">
      <label class="nlp-field-label">Documents (separated by ---)</label>
      <textarea v-model="texts" class="nlp-textarea" rows="12"
        placeholder="First document text&#10;---&#10;Second document text&#10;---&#10;Third document text"/>
      <div class="nlp-input-actions">
        <label class="nlp-csv-toggle"><input type="checkbox" v-model="csvMode"/> Export as CSV</label>
        <button class="nlp-btn" :disabled="loading||!texts.trim()" @click="runBatch">
          {{ loading?'Processing…':csvMode?'Batch → CSV':'Run Batch' }}
        </button>
      </div>
    </div>
    <div v-if="error" class="nlp-err">{{ error }}</div>
    <div v-if="results.length" class="nlp-results">
      <div class="nlp-results__label">{{ results.length }} results</div>
      <NlpResultCard v-for="(r,i) in results" :key="i" :result="r" :title="`Document ${i+1}`"/>
    </div>
  </div>
</template>
