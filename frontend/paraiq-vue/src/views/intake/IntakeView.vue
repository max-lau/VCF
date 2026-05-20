<script setup>
import { ref, onMounted } from 'vue'
import client from '@/api/client'

const mode      = ref('analyze')
const file      = ref(null)
const loading   = ref(false)
const result    = ref(null)
const error     = ref(null)
const history   = ref([])
const fileInput = ref(null)

const modes = [
  { key: 'analyze', label: 'Analyze', sub: 'Full NLP analysis' },
  { key: 'scan',    label: 'Scan',    sub: 'Quick OCR scan' },
  { key: 'form',    label: 'Form',    sub: 'Form field extraction' },
]

const endpointMap = { analyze: '/intake/analyze', scan: '/intake/scan', form: '/intake/form' }

function onFile(e) { file.value = e.target.files[0] || null }
function onDrop(e) { e.preventDefault(); file.value = e.dataTransfer.files[0] || null }

async function submit() {
  if (!file.value) return
  loading.value = true
  error.value   = null
  result.value  = null
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    const { data } = await client.post(endpointMap[mode.value], fd)
    result.value = data
    await fetchHistory()
  } catch(e) {
    error.value = e.response?.data?.detail || 'Intake failed'
  } finally { loading.value = false }
}

async function fetchHistory() {
  try {
    const { data } = await client.get('/intake/history')
    history.value = data.history || data || []
  } catch { history.value = [] }
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' })
}

onMounted(fetchHistory)
</script>

<template>
  <div class="mod">
    <div class="mod__header">
      <div>
        <h1 class="mod__title">OCR Document Intake</h1>
        <p class="mod__sub">Extract and analyse text from uploaded documents</p>
      </div>
    </div>

    <!-- Mode selector -->
    <div class="mode-bar">
      <button v-for="m in modes" :key="m.key"
        class="mode-btn" :class="{ active: mode === m.key }"
        @click="mode = m.key">
        <span class="mode-btn__label">{{ m.label }}</span>
        <span class="mode-btn__sub">{{ m.sub }}</span>
      </button>
    </div>

    <!-- Drop zone -->
    <div class="drop-zone" :class="{ 'has-file': file }"
      @dragover.prevent @drop="onDrop" @click="fileInput.click()">
      <input ref="fileInput" type="file" style="display:none"
        accept=".pdf,.png,.jpg,.jpeg,.tiff,.docx" @change="onFile"/>
      <div class="drop-zone__icon">↑</div>
      <div class="drop-zone__title">{{ file ? file.name : 'Drop document here or click to upload' }}</div>
      <div class="drop-zone__sub">PDF · PNG · JPG · TIFF · DOCX</div>
    </div>

    <div class="submit-row">
      <button class="piq-btn-gold" :disabled="loading || !file" @click="submit">
        {{ loading ? 'Processing…' : `Run ${modes.find(m=>m.key===mode).label}` }}
      </button>
    </div>

    <div v-if="error" class="err-msg">{{ error }}</div>

    <!-- Result -->
    <div v-if="result" class="result-card">
      <div class="result-card__title">Result</div>
      <pre class="result-pre">{{ typeof result === 'string' ? result : JSON.stringify(result, null, 2) }}</pre>
    </div>

    <!-- History -->
    <div v-if="history.length" class="history-section">
      <div class="section-label">Recent intake history</div>
      <div class="piq-table-wrap">
        <table class="piq-table">
          <thead><tr><th>File</th><th>Mode</th><th>Date</th><th>Status</th></tr></thead>
          <tbody>
            <tr v-for="h in history" :key="h.id">
              <td class="bold">{{ h.filename || h.file_name || '—' }}</td>
              <td class="dim">{{ h.mode || '—' }}</td>
              <td class="dim">{{ fmtDate(h.created_at) }}</td>
              <td><span class="status-pill" :class="'s-' + (h.status||'done')">{{ h.status || 'done' }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mod { padding: 2rem; max-width: 900px; }
.mod__header { margin-bottom: 1.5rem; }
.mod__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.mod__sub   { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }

.mode-bar { display: flex; gap: .75rem; margin-bottom: 1.25rem; flex-wrap: wrap; }
.mode-btn { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; cursor: pointer; display: flex; flex-direction: column; padding: .65rem 1.1rem; text-align: left; transition: border-color .15s; }
.mode-btn.active { border-color: var(--gold); }
.mode-btn__label { color: var(--text-primary); font-size: .875rem; font-weight: 600; }
.mode-btn__sub   { color: var(--text-muted); font-size: .72rem; margin-top: .1rem; }

.drop-zone { background: var(--bg-card); border: 2px dashed var(--border); border-radius: 10px; cursor: pointer; padding: 2.5rem; text-align: center; transition: border-color .15s; }
.drop-zone:hover, .drop-zone.has-file { border-color: var(--gold); }
.drop-zone__icon  { color: var(--gold); font-size: 1.8rem; margin-bottom: .5rem; opacity: .6; }
.drop-zone__title { color: var(--text-primary); font-size: .95rem; font-weight: 500; margin-bottom: .25rem; }
.drop-zone__sub   { color: var(--text-muted); font-size: .78rem; }

.submit-row { display: flex; justify-content: flex-end; margin: .75rem 0 1rem; }
.piq-btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #000; cursor: pointer; font-size: .875rem; font-weight: 600; padding: .55rem 1.4rem; transition: opacity .2s; }
.piq-btn-gold:hover:not(:disabled) { opacity: .85; }
.piq-btn-gold:disabled { cursor: not-allowed; opacity: .4; }

.err-msg { color: #fc8181; font-size: .875rem; margin-bottom: 1rem; }

.result-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem; }
.result-card__title { font-size: .72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .05em; margin-bottom: .75rem; text-transform: uppercase; }
.result-pre { background: var(--bg-raised, #0d0d1a); border-radius: 6px; color: var(--text-muted); font-family: var(--font-mono); font-size: .78rem; line-height: 1.6; margin: 0; overflow-x: auto; padding: 1rem; white-space: pre-wrap; word-break: break-word; }

.history-section { margin-top: 1.5rem; }
.section-label { font-size: .72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .05em; margin-bottom: .75rem; text-transform: uppercase; }
.piq-table-wrap { border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; }
.piq-table { border-collapse: collapse; font-size: .875rem; width: 100%; }
.piq-table th { background: var(--bg-card); border-bottom: 1px solid var(--border); color: var(--text-muted); font-size: .72rem; font-weight: 600; letter-spacing: .05em; padding: .65rem .9rem; text-align: left; text-transform: uppercase; }
.piq-table td { border-bottom: 1px solid var(--border); padding: .7rem .9rem; vertical-align: middle; }
.piq-table tr:last-child td { border-bottom: none; }
.bold { color: var(--text-primary); font-weight: 500; }
.dim  { color: var(--text-muted); }
.status-pill { border-radius: 4px; font-size: .72rem; font-weight: 600; padding: .2rem .5rem; text-transform: capitalize; background: rgba(72,187,120,.15); color: #48bb78; }
</style>
