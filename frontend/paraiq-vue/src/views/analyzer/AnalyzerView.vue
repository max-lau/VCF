<script setup>
import { ref } from 'vue'
import client from '@/api/client'
import NlpResultCard from '@/components/ui/NlpResultCard.vue'

const text = ref(''), result = ref(null), loading = ref(false), error = ref(null)

async function analyze() {
  loading.value = true; error.value = null; result.value = null
  try   { const { data } = await client.post('/analyze', { text: text.value }); result.value = data }
  catch (e) { error.value = e.response?.data?.detail || 'Analysis failed' }
  finally   { loading.value = false }
}
</script>
<template>
  <div class="nlp-mod">
    <div class="nlp-mod__header">
      <h1 class="nlp-mod__title">Document Analyzer</h1>
      <p class="nlp-mod__sub">Full NLP analysis — entities, sentiment, clauses</p>
    </div>
    <div class="nlp-input-card">
      <label class="nlp-field-label">Document text</label>
      <textarea v-model="text" class="nlp-textarea" rows="10" placeholder="Paste legal document text…"/>
      <div class="nlp-input-actions">
        <button class="nlp-btn" :disabled="loading||!text.trim()" @click="analyze">
          {{ loading?'Analysing…':'Analyze' }}
        </button>
      </div>
    </div>
    <div v-if="error" class="nlp-err">{{ error }}</div>
    <NlpResultCard v-if="result" :result="result" title="Analysis Result"/>
  </div>
</template>
