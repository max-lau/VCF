<script setup>
import { ref } from 'vue'
import client from '@/api/client'
import NlpResultCard from '@/components/ui/NlpResultCard.vue'

const text = ref(''), loading = ref(false), error = ref(null)
const coref = ref(null), disambig = ref(null), contradict = ref(null)

async function runAll() {
  if (!text.value.trim()) return
  loading.value = true; error.value = null
  coref.value = disambig.value = contradict.value = null
  try {
    const [cRes, dRes] = await Promise.all([
      client.post('/coreference', { text: text.value }),
      client.post('/disambiguate', { text: text.value }),
    ])
    coref.value = cRes.data; disambig.value = dRes.data
    try { const { data } = await client.post('/contradictions/scan', { text: text.value }); contradict.value = data } catch {}
  } catch (e) { error.value = e.response?.data?.detail || 'Analysis failed' }
  finally     { loading.value = false }
}
</script>
<template>
  <div class="nlp-mod" style="max-width:950px">
    <div class="nlp-mod__header">
      <h1 class="nlp-mod__title">Document Insights</h1>
      <p class="nlp-mod__sub">Coreference, disambiguation, and contradiction scanning</p>
    </div>
    <div class="nlp-input-card">
      <label class="nlp-field-label">Document text</label>
      <textarea v-model="text" class="nlp-textarea" rows="10" placeholder="Paste document for deep analysis…"/>
      <div class="nlp-input-actions">
        <button class="nlp-btn" :disabled="loading||!text.trim()" @click="runAll">
          {{ loading?'Analysing…':'Run Insights' }}
        </button>
      </div>
    </div>
    <div v-if="error" class="nlp-err">{{ error }}</div>
    <div v-if="coref||disambig||contradict" class="nlp-results">
      <NlpResultCard v-if="coref"      :result="coref"      title="Coreference Resolution"/>
      <NlpResultCard v-if="disambig"   :result="disambig"   title="Entity Disambiguation"/>
      <NlpResultCard v-if="contradict" :result="contradict" title="Contradiction Scan"/>
    </div>
  </div>
</template>
