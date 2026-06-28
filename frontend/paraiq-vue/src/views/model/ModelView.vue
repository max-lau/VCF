<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'
import NlpResultCard from '@/components/ui/NlpResultCard.vue'

const status   = ref(null)
const info     = ref(null)
const dataset  = ref(null)
const examples = ref([])
const loadingExamples = ref(false)

const predText   = ref('')
const predResult = ref(null)
const predicting = ref(false)
const error      = ref(null)

const STATUS_META = {
  training: { label: 'Training', color: '#ffb74d', icon: '⚙' },
  idle:     { label: 'Idle',     color: '#4caf79', icon: '✓' },
  ready:    { label: 'Ready',    color: '#4caf79', icon: '✓' },
  error:    { label: 'Error',    color: '#fc8181', icon: '✕' },
}

const statusMeta = computed(() => {
  const raw = (status.value?.status || status.value?.state || 'idle').toLowerCase()
  return STATUS_META[raw] || { label: raw, color: '#888', icon: '◎' }
})

const accuracyMetrics = computed(() => {
  if (!info.value) return []
  const src = info.value.accuracy || info.value.metrics || info.value
  const keys = ['accuracy', 'precision', 'recall', 'f1', 'f1_score', 'val_accuracy']
  return keys.filter(k => src[k] != null).map(k => ({
    key: k.replace(/_/g, ' '),
    value: typeof src[k] === 'number' ? (src[k] <= 1 ? (src[k] * 100).toFixed(2) + '%' : src[k]) : src[k]
  }))
})

const labelDistribution = computed(() => {
  if (!dataset.value?.label_distribution) return []
  const dist = dataset.value.label_distribution
  const total = Object.values(dist).reduce((a, b) => a + Number(b), 0) || 1
  return Object.entries(dist)
    .map(([label, count]) => ({ label, count, pct: Math.round((count / total) * 100) }))
    .sort((a, b) => b.count - a.count)
})

async function fetchAll() {
  error.value = null
  try {
    const [sRes, iRes, dRes] = await Promise.all([
      client.get('/model/status').catch(() => ({ data: null })),
      client.get('/model/info').catch(() => ({ data: null })),
      client.get('/model/dataset').catch(() => ({ data: null })),
    ])
    status.value = sRes.data
    info.value = iRes.data
    dataset.value = dRes.data
  } catch (e) {
    error.value = 'Failed to load model data'
  }
}

async function fetchExamples() {
  loadingExamples.value = true
  try {
    const { data } = await client.get('/model/examples')
    const list = data.examples || data || []
    examples.value = list.slice(0, 5)
  } catch { examples.value = [] }
  finally { loadingExamples.value = false }
}

async function predict() {
  if (!predText.value.trim()) return
  predicting.value = true; error.value = null; predResult.value = null
  try {
    const { data } = await client.post('/model/predict', { text: predText.value })
    predResult.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Prediction failed'
  } finally { predicting.value = false }
}

function pct(v) { return `${Math.min(100, Math.max(0, Math.round(v)))}%` }

onMounted(() => {
  fetchAll()
  fetchExamples()
})
</script>

<template>
  <div class="mod">
    <div class="mod__header">
      <div>
        <h1 class="mod__title">Fine-Tuned Model</h1>
        <p class="mod__sub">Custom model management, monitoring, and inference</p>
      </div>
      <button class="btn-secondary" @click="fetchAll">↻ Refresh</button>
    </div>

    <div v-if="error" class="err-msg">{{ error }}</div>

    <!-- Top dashboard grid -->
    <div class="grid">
      <!-- Status card -->
      <div class="card card--status">
        <div class="card__label">Model Status</div>
        <div class="status-block">
          <span class="status-dot" :style="{ background: statusMeta.color }">{{ statusMeta.icon }}</span>
          <div>
            <div class="status-label" :style="{ color: statusMeta.color }">{{ statusMeta.label }}</div>
            <div v-if="status?.progress != null" class="status-progress">
              <div class="progress-track">
                <div class="progress-fill" :style="{ width: pct(status.progress * (status.progress <= 1 ? 100 : 1)) }"></div>
              </div>
              <span>{{ Math.round(status.progress * (status.progress <= 1 ? 100 : 1)) }}%</span>
            </div>
            <div v-if="status?.message" class="status-msg">{{ status.message }}</div>
          </div>
        </div>
      </div>

      <!-- Info card -->
      <div class="card">
        <div class="card__label">Model Info</div>
        <div class="kv-row" v-if="info?.name"><span class="kv-key">Name</span><span class="kv-val">{{ info.name }}</span></div>
        <div class="kv-row" v-if="info?.type"><span class="kv-key">Type</span><span class="kv-val">{{ info.type }}</span></div>
        <div class="kv-row" v-if="info?.base_model"><span class="kv-key">Base</span><span class="kv-val mono">{{ info.base_model }}</span></div>
        <div class="kv-row" v-if="info?.version"><span class="kv-key">Version</span><span class="kv-val">{{ info.version }}</span></div>
        <div class="kv-row" v-if="info?.trained_at"><span class="kv-key">Trained</span><span class="kv-val">{{ new Date(info.trained_at).toLocaleDateString() }}</span></div>
        <div class="kv-row" v-if="!info" style="opacity:.6"><span class="kv-val">No model info available</span></div>

        <div v-if="accuracyMetrics.length" class="metric-section">
          <div class="metric-label">Accuracy Metrics</div>
          <div class="metric-grid">
            <div v-for="m in accuracyMetrics" :key="m.key" class="metric">
              <div class="metric__val">{{ m.value }}</div>
              <div class="metric__key">{{ m.key }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Dataset card -->
      <div class="card">
        <div class="card__label">Dataset Stats</div>
        <div class="dataset-total">
          <div class="dataset-total__n">{{ Number(dataset?.total_examples ?? dataset?.total ?? 0).toLocaleString() }}</div>
          <div class="dataset-total__l">Total Examples</div>
        </div>
        <div v-if="labelDistribution.length" class="dist-section">
          <div class="metric-label">Label Distribution</div>
          <div v-for="d in labelDistribution" :key="d.label" class="dist-row">
            <span class="dist-row__label">{{ d.label }}</span>
            <div class="dist-bar-wrap"><div class="dist-bar" :style="{ width: pct(d.pct) }"></div></div>
            <span class="dist-row__count">{{ d.count }}</span>
          </div>
        </div>
        <div v-else-if="!dataset" style="opacity:.6;font-size:.85rem;color:var(--text-muted)">No dataset info available</div>
      </div>
    </div>

    <!-- Prediction testing panel -->
    <div class="panel">
      <div class="panel__header">
        <div class="panel__title">Test Prediction</div>
        <div class="panel__sub">Run inference against the fine-tuned model</div>
      </div>
      <textarea
        v-model="predText"
        class="textarea"
        rows="4"
        placeholder="Enter text to classify / analyze…"
      />
      <div class="panel__actions">
        <button class="btn-gold" :disabled="predicting || !predText.trim()" @click="predict">
          {{ predicting ? 'Predicting…' : 'Run Prediction' }}
        </button>
        <button class="btn-ghost" @click="predText = ''; predResult = null">Clear</button>
      </div>
      <NlpResultCard v-if="predResult" :result="predResult" title="Prediction Result" style="margin-top:1rem" />
    </div>

    <!-- Training examples preview -->
    <div class="panel">
      <div class="panel__header">
        <div class="panel__title">Training Examples</div>
        <div class="panel__sub">Sample {{ examples.length }} of dataset</div>
      </div>
      <div v-if="loadingExamples" class="state-msg">Loading examples…</div>
      <div v-else-if="!examples.length" class="empty-inline">No training examples available.</div>
      <div v-else class="ex-list">
        <div v-for="(ex, i) in examples" :key="i" class="ex-item">
          <span class="ex-item__label" v-if="ex.label">{{ ex.label }}</span>
          <span class="ex-item__text">{{ (ex.text || '').slice(0, 180) }}{{ (ex.text || '').length > 180 ? '…' : '' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mod { padding: 2rem; max-width: 1200px; }
.mod__header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.25rem; }
.mod__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.mod__sub { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.err-msg { color: #fc8181; font-size: 0.875rem; margin-bottom: 1rem; }
.grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; margin-bottom: 1.5rem; }
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
.card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.1rem 1.25rem; }
.card--status { display: flex; flex-direction: column; }
.card__label { font-size: 0.72rem; color: var(--text-muted); font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 0.75rem; }
.status-block { display: flex; gap: 0.75rem; align-items: flex-start; }
.status-dot { align-items: center; border-radius: 50%; display: inline-flex; font-size: 0.85rem; height: 32px; justify-content: center; opacity: 0.9; width: 32px; flex-shrink: 0; }
.status-label { font-size: 1rem; font-weight: 600; }
.status-progress { align-items: center; display: flex; gap: 0.5rem; margin-top: 0.5rem; }
.progress-track { background: rgba(255,255,255,.07); border-radius: 3px; flex: 1; height: 5px; overflow: hidden; }
.progress-fill { background: var(--gold); height: 100%; transition: width 0.35s ease; }
.status-msg { color: var(--text-muted); font-size: 0.78rem; margin-top: 0.4rem; }
.kv-row { display: flex; justify-content: space-between; font-size: 0.82rem; padding: 0.3rem 0; border-bottom: 1px solid var(--border); }
.kv-row:last-child { border-bottom: none; }
.kv-key { color: var(--text-muted); text-transform: capitalize; }
.kv-val { color: var(--text-primary); font-weight: 500; text-align: right; word-break: break-word; }
.mono { font-family: var(--font-mono); }
.metric-section { margin-top: 0.85rem; padding-top: 0.75rem; border-top: 1px solid var(--border); }
.metric-label { font-size: 0.68rem; color: var(--text-muted); font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 0.5rem; }
.metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
.metric { background: var(--bg-raised); border-radius: 6px; padding: 0.5rem 0.65rem; text-align: center; }
.metric__val { color: var(--gold); font-size: 1.05rem; font-weight: 700; font-family: var(--font-mono); }
.metric__key { color: var(--text-muted); font-size: 0.68rem; text-transform: capitalize; margin-top: 0.15rem; }
.dataset-total { text-align: center; padding: 0.5rem 0 0.75rem; }
.dataset-total__n { color: var(--gold); font-size: 1.8rem; font-weight: 700; font-family: var(--font-mono); }
.dataset-total__l { color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; }
.dist-section { margin-top: 0.5rem; padding-top: 0.75rem; border-top: 1px solid var(--border); }
.dist-row { display: flex; align-items: center; gap: 0.6rem; padding: 0.25rem 0; font-size: 0.78rem; }
.dist-row__label { color: var(--text-muted); min-width: 80px; flex-shrink: 0; }
.dist-bar-wrap { flex: 1; height: 5px; background: rgba(255,255,255,.07); border-radius: 3px; overflow: hidden; }
.dist-bar { background: var(--gold); height: 100%; transition: width 0.35s ease; opacity: 0.85; }
.dist-row__count { color: var(--text-primary); font-weight: 600; min-width: 30px; text-align: right; }
.panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.5rem; }
.panel__header { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 0.85rem; }
.panel__title { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }
.panel__sub { color: var(--text-muted); font-size: 0.78rem; }
.textarea { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-family: inherit; font-size: 0.88rem; outline: none; padding: 0.7rem 0.85rem; resize: vertical; width: 100%; box-sizing: border-box; }
.textarea:focus { border-color: var(--gold); }
.panel__actions { display: flex; gap: 0.5rem; margin-top: 0.75rem; }
.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #000; cursor: pointer; font-size: 0.85rem; font-weight: 600; padding: 0.55rem 1.4rem; transition: opacity 0.2s; }
.btn-gold:hover:not(:disabled) { opacity: 0.85; }
.btn-gold:disabled { cursor: not-allowed; opacity: 0.4; }
.btn-ghost { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.55rem 1rem; transition: all 0.15s; }
.btn-ghost:hover { background: var(--bg-raised); color: var(--text-primary); }
.ex-list { display: flex; flex-direction: column; gap: 0.4rem; }
.ex-item { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; display: flex; gap: 0.75rem; padding: 0.55rem 0.75rem; align-items: baseline; }
.ex-item__label { background: rgba(201,168,76,.18); border-radius: 4px; color: var(--gold); flex-shrink: 0; font-size: 0.7rem; font-weight: 600; min-width: 70px; padding: 0.15rem 0.4rem; text-align: center; }
.ex-item__text { color: var(--text-muted); flex: 1; font-size: 0.82rem; line-height: 1.5; }
.empty-inline { color: var(--text-muted); font-size: 0.85rem; padding: 1rem 0; text-align: center; }
.state-msg { color: var(--text-muted); padding: 1.5rem; text-align: center; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; transition: all 0.15s; }
.btn-secondary:hover { background: var(--bg-raised); color: var(--text-primary); }
</style>
