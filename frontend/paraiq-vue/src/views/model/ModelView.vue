<script setup>
import { ref, onMounted } from 'vue'
import client from '@/api/client'
import NlpResultCard from '@/components/ui/NlpResultCard.vue'

const info = ref(null), status = ref(null), examples = ref([])
const predText = ref(''), predResult = ref(null)
const loading = ref(false), training = ref(false), error = ref(null)

async function fetchAll() {
  try {
    const [iRes, sRes, eRes] = await Promise.all([
      client.get('/model/info'), client.get('/model/status'), client.get('/model/examples')
    ])
    info.value = iRes.data; status.value = sRes.data
    examples.value = eRes.data.examples || eRes.data || []
  } catch {}
}
async function train() {
  training.value = true; error.value = null
  try { await client.post('/model/train', {}); await fetchAll() }
  catch (e) { error.value = e.response?.data?.detail || 'Training failed' }
  finally   { training.value = false }
}
async function predict() {
  loading.value = true; error.value = null; predResult.value = null
  try   { const { data } = await client.post('/model/predict', { text: predText.value }); predResult.value = data }
  catch (e) { error.value = e.response?.data?.detail || 'Prediction failed' }
  finally   { loading.value = false }
}
onMounted(fetchAll)
</script>
<template>
  <div class="nlp-mod">
    <div class="nlp-mod__header--split">
      <div><h1 class="nlp-mod__title">Fine-Tuned Model</h1><p class="nlp-mod__sub">Custom model management and inference</p></div>
      <button class="nlp-btn--outline" :disabled="training" @click="train">{{ training?'Training…':'Trigger Training' }}</button>
    </div>
    <div v-if="error" class="nlp-err">{{ error }}</div>

    <div class="model-grid">
      <div v-if="info" class="model-card">
        <div class="model-card__title">Model Info</div>
        <div v-for="(v,k) in info" :key="k" class="model-row">
          <span class="model-row__key">{{ k }}</span><span class="model-row__val">{{ v }}</span>
        </div>
      </div>
      <div v-if="status" class="model-card">
        <div class="model-card__title">Status</div>
        <div v-for="(v,k) in status" :key="k" class="model-row">
          <span class="model-row__key">{{ k }}</span><span class="model-row__val">{{ v }}</span>
        </div>
      </div>
    </div>

    <div class="nlp-input-card" style="margin-top:1.25rem">
      <label class="nlp-field-label">Test prediction</label>
      <textarea v-model="predText" class="nlp-textarea" rows="5" placeholder="Enter text to classify…"/>
      <div class="nlp-input-actions">
        <button class="nlp-btn" :disabled="loading||!predText.trim()" @click="predict">{{ loading?'Predicting…':'Predict' }}</button>
      </div>
    </div>
    <NlpResultCard v-if="predResult" :result="predResult" title="Prediction" style="margin-bottom:1rem"/>

    <div v-if="examples.length" class="model-card" style="margin-top:.5rem">
      <div class="model-card__title">Training Examples ({{ examples.length }})</div>
      <div v-for="(ex,i) in examples.slice(0,10)" :key="i" class="model-ex">
        <span class="model-ex__label">{{ ex.label }}</span>
        <span class="model-ex__text">{{ (ex.text||'').slice(0,100) }}…</span>
      </div>
    </div>
  </div>
</template>
<style scoped>
.model-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.model-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.1rem 1.25rem; }
.model-card__title { font-size: .72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .05em; text-transform: uppercase; margin-bottom: .75rem; }
.model-row { display: flex; justify-content: space-between; font-size: .82rem; padding: .3rem 0; border-bottom: 1px solid var(--border); }
.model-row:last-child { border-bottom: none; }
.model-row__key { color: var(--text-muted); text-transform: capitalize; }
.model-row__val { color: var(--text-primary); font-weight: 500; }
.model-ex { display: flex; align-items: baseline; gap: .75rem; font-size: .8rem; padding: .3rem 0; border-bottom: 1px solid var(--border); }
.model-ex:last-child { border-bottom: none; }
.model-ex__label { color: var(--gold); font-weight: 600; min-width: 80px; flex-shrink: 0; }
.model-ex__text  { color: var(--text-muted); flex: 1; }
</style>
