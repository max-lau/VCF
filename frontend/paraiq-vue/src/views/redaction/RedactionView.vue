<script setup>
import { ref, onMounted, computed } from 'vue'
import client from '@/api/client'

const tab             = ref('text')
const inputText       = ref('')
const redacted        = ref('')
const findings        = ref([])
const pdfFile         = ref(null)
const pdfFileInput    = ref(null)
const originalPdfUrl  = ref(null)
const redactedPdfUrl  = ref(null)
const threshold       = ref(0.5)
const style           = ref('label')
const useClaude       = ref(true)
const loading         = ref(false)
const error           = ref(null)
const files           = ref([])
const currentPdfId    = ref(null)
const presidioOk      = ref(null)

const MAX_FILE_SIZE = 20 * 1024 * 1024

const styleLabel = computed(() => {
  const labels = { label: 'Label [CATEGORY]', black: 'Black box', white: 'White out', highlight: 'Highlight [[CATEGORY]]' }
  return labels[style.value] || style.value
})

async function redactText() {
  if (!inputText.value.trim()) return
  loading.value = true; error.value = null; redacted.value = ''; findings.value = []
  try {
    const { data } = await client.post('/redact/text', {
      text: inputText.value,
      threshold: threshold.value,
      style: style.value,
      use_claude: useClaude.value,
    })
    redacted.value = data.redacted_text || ''
    findings.value = data.findings || []
    presidioOk.value = data.presidio_available
  } catch(e) {
    error.value = e.response?.data?.detail || 'Redaction failed'
  } finally { loading.value = false }
}

function onPdfFile(e) {
  const f = e.target.files?.[0]
  if (f && f.size > MAX_FILE_SIZE) {
    error.value = 'File too large. Max size is 20 MB.'
    pdfFile.value = null
    originalPdfUrl.value = null
    return
  }
  pdfFile.value = f || null
  if (originalPdfUrl.value) URL.revokeObjectURL(originalPdfUrl.value)
  originalPdfUrl.value = f ? URL.createObjectURL(f) : null
  redactedPdfUrl.value = null
  currentPdfId.value = null
  error.value = null
}

async function redactPdf() {
  if (!pdfFile.value) return
  loading.value = true; error.value = null; currentPdfId.value = null
  if (redactedPdfUrl.value) URL.revokeObjectURL(redactedPdfUrl.value)
  redactedPdfUrl.value = null
  try {
    const fd = new FormData()
    fd.append('file', pdfFile.value)
    const { data } = await client.post(
      `/redact/pdf?threshold=${threshold.value}&style=${style.value}&use_claude=${useClaude.value}`,
      fd,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    currentPdfId.value = data.redaction_id || null
    redacted.value = data.redacted_preview || ''
    findings.value = data.findings || []
    presidioOk.value = data.presidio_available

    // Load redacted file as blob for side-by-side preview
    if (currentPdfId.value) {
      const res = await fetch(`/redact/${currentPdfId.value}/download`, {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('paraiq_token')}` }
      })
      if (res.ok) {
        const blob = await res.blob()
        redactedPdfUrl.value = URL.createObjectURL(blob)
      }
    }
    await fetchFiles()
  } catch(e) {
    error.value = e.response?.data?.detail || 'PDF redaction failed'
  } finally { loading.value = false }
}

function downloadPdf(id) {
  window.open(`/redact/${id}/download`, '_blank')
}

async function deleteFile(id) {
  if (!confirm('Delete this file?')) return
  await client.delete(`/redact/${id}`)
  await fetchFiles()
}

async function fetchFiles() {
  try {
    const { data } = await client.get('/redact/files')
    files.value = data.files || []
  } catch { files.value = [] }
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' })
}

onMounted(fetchFiles)
</script>

<template>
  <div class="mod">
    <div class="mod__header">
      <div>
        <h1 class="mod__title">Redaction</h1>
        <p class="mod__sub">
          Automated PII and privilege redaction for safe external sharing.
          <span v-if="presidioOk === false" class="fallback-badge">Claude-only mode — Presidio not installed</span>
        </p>
      </div>
    </div>

    <!-- Tabs -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: tab === 'text' }" @click="tab = 'text'">Text Redaction</button>
      <button class="tab-btn" :class="{ active: tab === 'pdf' }"  @click="tab = 'pdf'">PDF Redaction</button>
      <button class="tab-btn" :class="{ active: tab === 'files' }" @click="tab = 'files'; fetchFiles()">Redacted Files</button>
    </div>

    <div v-if="error" class="err-msg">{{ error }}</div>

    <!-- Shared options -->
    <div class="options-row">
      <label class="opt-label">Threshold
        <input type="range" v-model.number="threshold" min="0" max="1" step="0.05" style="width:120px"/>
        <span class="opt-val">{{ threshold }}</span>
      </label>
      <label class="opt-label">Style
        <select v-model="style" class="piq-select">
          <option value="label">Label [CATEGORY]</option>
          <option value="black">Black box</option>
          <option value="white">White out</option>
          <option value="highlight">Highlight</option>
        </select>
      </label>
      <label class="opt-label checkbox">
        <input type="checkbox" v-model="useClaude"/>
        Use Claude AI
      </label>
    </div>

    <!-- Text tab -->
    <div v-if="tab === 'text'" class="panel">
      <div class="two-col">
        <div class="col-block">
          <div class="col-label">Original text</div>
          <textarea v-model="inputText" class="piq-textarea" rows="14"
            placeholder="Paste text containing PII or privileged information…"/>
          <button class="piq-btn-gold mt" :disabled="loading || !inputText.trim()" @click="redactText">
            {{ loading ? 'Redacting…' : 'Redact Text' }}
          </button>
        </div>
        <div class="col-block">
          <div class="col-label">Redacted output — {{ styleLabel }}</div>
          <div class="redacted-box" v-if="redacted">{{ redacted }}</div>
          <div class="redacted-box redacted-box--empty" v-else>Redacted text will appear here…</div>
          <div v-if="findings.length" class="findings-summary">
            {{ findings.length }} finding{{ findings.length !== 1 ? 's' : '' }}
            <span v-if="findings.some(f => f.source === 'claude')" class="dim sm">(Claude-enhanced)</span>
          </div>
        </div>
      </div>
    </div>

    <!-- PDF tab -->
    <div v-if="tab === 'pdf'" class="panel">
      <div class="drop-zone" :class="{ 'has-file': pdfFile }"
        @dragover.prevent @drop.prevent="e => { const f = e.dataTransfer.files[0]; if (f) { pdfFile = f; onPdfFile({ target: { files: [f] } }) } }"
        @click="pdfFileInput.click()">
        <input ref="pdfFileInput" type="file" accept=".pdf,.txt,.docx" style="display:none" @change="onPdfFile"/>
        <div class="drop-zone__icon">↑</div>
        <div class="drop-zone__title">{{ pdfFile ? pdfFile.name : 'Drop file here or click to upload' }}</div>
        <div class="drop-zone__sub">PDF, TXT, DOCX · max 20 MB</div>
      </div>
      <div class="submit-row">
        <button class="piq-btn-gold" :disabled="loading || !pdfFile" @click="redactPdf">
          {{ loading ? 'Processing…' : 'Redact File' }}
        </button>
      </div>

      <!-- Side-by-side PDF preview -->
      <div v-if="originalPdfUrl || redactedPdfUrl" class="pdf-preview-row">
        <div class="pdf-preview-col">
          <div class="col-label">Original file</div>
          <iframe v-if="originalPdfUrl" :src="originalPdfUrl" class="pdf-frame" type="application/pdf"></iframe>
          <div v-else class="pdf-frame pdf-frame--empty">Original preview unavailable</div>
        </div>
        <div class="pdf-preview-col">
          <div class="col-label">Redacted file</div>
          <iframe v-if="redactedPdfUrl" :src="redactedPdfUrl" class="pdf-frame" type="application/pdf"></iframe>
          <div v-else class="pdf-frame pdf-frame--empty">Redacted preview will appear here…</div>
        </div>
      </div>

      <div v-if="currentPdfId" class="success-msg">
        ✓ Redaction complete —
        <button class="link-btn" @click="downloadPdf(currentPdfId)">Download redacted file</button>
      </div>

      <div v-if="findings.length && tab === 'pdf'" class="findings-summary">
        {{ findings.length }} PII finding{{ findings.length !== 1 ? 's' : '' }} detected
        <span v-if="findings.some(f => f.source === 'claude')" class="dim sm">(Claude-enhanced)</span>
      </div>
    </div>

    <!-- Files tab -->
    <div v-if="tab === 'files'" class="panel">
      <div v-if="!files.length" class="empty-state">No redacted files yet.</div>
      <div v-else class="piq-table-wrap">
        <table class="piq-table">
          <thead><tr><th>File</th><th>Date</th><th>Style</th><th>Download</th><th></th></tr></thead>
          <tbody>
            <tr v-for="f in files" :key="f.redaction_id">
              <td class="bold">{{ f.filename || `File #${f.redaction_id}` }}</td>
              <td class="dim">{{ fmtDate(f.created_at) }}</td>
              <td class="dim">{{ f.style || '—' }}</td>
              <td><button class="action-btn" @click="downloadPdf(f.redaction_id)">↓ Download</button></td>
              <td><button class="action-btn action-btn--del" @click="deleteFile(f.redaction_id)">✕</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

  </div>
</template>

<style scoped>
.mod { padding: 2rem; max-width: 1050px; }
.mod__header { margin-bottom: 1.25rem; }
.mod__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.mod__sub   { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.fallback-badge { display: inline-block; margin-left: .5rem; padding: .15rem .5rem; border-radius: 4px; background: rgba(246,173,85,.15); color: #f6ad55; font-size: .72rem; font-weight: 600; }

.tab-bar { display: flex; gap: .5rem; margin-bottom: 1.25rem; border-bottom: 1px solid var(--border); padding-bottom: .75rem; }
.tab-btn { background: none; border: 1px solid transparent; border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: .875rem; padding: .4rem .9rem; transition: all .15s; }
.tab-btn:hover { color: var(--text-primary); }
.tab-btn.active { border-color: var(--gold); color: var(--gold); }

.panel { }
.err-msg { color: #fc8181; font-size: .875rem; margin-bottom: 1rem; }
.success-msg { color: #48bb78; font-size: .875rem; margin-top: .75rem; }
.link-btn { background: none; border: none; color: var(--gold); cursor: pointer; font-size: .875rem; text-decoration: underline; }

.options-row { display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 1rem; padding: .75rem 1rem; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; }
.opt-label { display: flex; align-items: center; gap: .5rem; font-size: .8rem; color: var(--text-muted); }
.opt-label.checkbox { gap: .4rem; cursor: pointer; }
.opt-val { color: var(--gold); font-weight: 600; min-width: 30px; }
.piq-select { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: .8rem; padding: .3rem .6rem; }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.col-block { display: flex; flex-direction: column; gap: .5rem; }
.col-label { font-size: .72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .05em; text-transform: uppercase; }
.piq-textarea { background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-family: inherit; font-size: .875rem; line-height: 1.6; padding: .75rem; resize: vertical; width: 100%; box-sizing: border-box; }
.piq-textarea:focus { border-color: var(--gold); outline: none; }
.redacted-box { background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; flex: 1; font-size: .875rem; line-height: 1.6; min-height: 200px; padding: .75rem; white-space: pre-wrap; word-break: break-word; color: var(--text-primary); }
.redacted-box--empty { color: var(--text-muted); font-style: italic; }
.findings-summary { font-size: .78rem; color: var(--text-muted); }

.drop-zone { background: var(--bg-card); border: 2px dashed var(--border); border-radius: 10px; cursor: pointer; padding: 2rem; text-align: center; transition: border-color .15s; }
.drop-zone:hover, .drop-zone.has-file { border-color: var(--gold); }
.drop-zone__icon  { color: var(--gold); font-size: 1.5rem; margin-bottom: .4rem; opacity: .6; }
.drop-zone__title { color: var(--text-primary); font-size: .9rem; font-weight: 500; margin-bottom: .2rem; }
.drop-zone__sub   { color: var(--text-muted); font-size: .75rem; }
.submit-row { display: flex; justify-content: flex-end; margin-top: .75rem; }

.pdf-preview-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1rem; }
.pdf-preview-col { display: flex; flex-direction: column; gap: .5rem; min-height: 420px; }
.pdf-frame { flex: 1; width: 100%; min-height: 400px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-raised, #0d0d1a); }
.pdf-frame--empty { display: flex; align-items: center; justify-content: center; color: var(--text-muted); font-style: italic; font-size: .875rem; }

.piq-btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #000; cursor: pointer; font-size: .875rem; font-weight: 600; padding: .55rem 1.4rem; transition: opacity .2s; }
.piq-btn-gold:hover:not(:disabled) { opacity: .85; }
.piq-btn-gold:disabled { cursor: not-allowed; opacity: .4; }
.mt { margin-top: .5rem; align-self: flex-start; }

.empty-state { color: var(--text-muted); padding: 3rem; text-align: center; font-size: .875rem; }
.piq-table-wrap { border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; }
.piq-table { border-collapse: collapse; font-size: .875rem; width: 100%; }
.piq-table th { background: var(--bg-card); border-bottom: 1px solid var(--border); color: var(--text-muted); font-size: .72rem; font-weight: 600; letter-spacing: .05em; padding: .65rem .9rem; text-align: left; text-transform: uppercase; }
.piq-table td { border-bottom: 1px solid var(--border); padding: .7rem .9rem; vertical-align: middle; }
.piq-table tr:last-child td { border-bottom: none; }
.bold { color: var(--text-primary); font-weight: 500; }
.dim  { color: var(--text-muted); }

.action-btn { background: none; border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); cursor: pointer; font-size: .78rem; padding: .3rem .7rem; transition: all .2s; white-space: nowrap; }
.action-btn:hover { border-color: var(--gold); color: var(--gold); }
.action-btn--del:hover { border-color: #fc8181 !important; color: #fc8181 !important; }
</style>
