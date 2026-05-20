<script setup>
import { ref, onMounted } from 'vue'
import client from '@/api/client'

const tab         = ref('text')
const inputText   = ref('')
const redacted    = ref('')
const pdfFile     = ref(null)
const pdfFileInput= ref(null)
const threshold   = ref(0.5)
const style       = ref('black')
const useClaude   = ref(false)
const loading     = ref(false)
const error       = ref(null)
const files       = ref([])
const currentPdfId= ref(null)

async function redactText() {
  if (!inputText.value.trim()) return
  loading.value = true; error.value = null
  try {
    const { data } = await client.post('/redact/text', { text: inputText.value })
    redacted.value = data.redacted_text || data.text || JSON.stringify(data)
  } catch(e) { error.value = e.response?.data?.detail || 'Redaction failed' }
  finally { loading.value = false }
}

function onPdfFile(e) { pdfFile.value = e.target.files[0] || null }

async function redactPdf() {
  if (!pdfFile.value) return
  loading.value = true; error.value = null
  try {
    const fd = new FormData()
    fd.append('file', pdfFile.value)
    const { data } = await client.post(
      `/redact/pdf?threshold=${threshold.value}&style=${style.value}&use_claude=${useClaude.value}`,
      fd
    )
    currentPdfId.value = data.id || data.file_id || null
    await fetchFiles()
  } catch(e) { error.value = e.response?.data?.detail || 'PDF redaction failed' }
  finally { loading.value = false }
}

function downloadPdf(id) {
  window.open(`/api/redact/download/${id}`, '_blank')
}

async function deleteFile(id) {
  if (!confirm('Delete this file?')) return
  await client.delete(`/redact/${id}`)
  await fetchFiles()
}

async function fetchFiles() {
  try {
    const { data } = await client.get('/redact/files')
    files.value = data.files || data || []
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
        <p class="mod__sub">Automated PII and privilege redaction</p>
      </div>
    </div>

    <!-- Tabs -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: tab === 'text' }" @click="tab = 'text'">Text Redaction</button>
      <button class="tab-btn" :class="{ active: tab === 'pdf' }"  @click="tab = 'pdf'">PDF Redaction</button>
      <button class="tab-btn" :class="{ active: tab === 'files' }" @click="tab = 'files'; fetchFiles()">Redacted Files</button>
    </div>

    <div v-if="error" class="err-msg">{{ error }}</div>

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
          <div class="col-label">Redacted output</div>
          <div class="redacted-box" v-if="redacted">{{ redacted }}</div>
          <div class="redacted-box redacted-box--empty" v-else>Redacted text will appear here…</div>
        </div>
      </div>
    </div>

    <!-- PDF tab -->
    <div v-if="tab === 'pdf'" class="panel">
      <div class="options-row">
        <label class="opt-label">Threshold
          <input type="range" v-model.number="threshold" min="0" max="1" step="0.05" style="width:120px"/>
          <span class="opt-val">{{ threshold }}</span>
        </label>
        <label class="opt-label">Style
          <select v-model="style" class="piq-select">
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
      <div class="drop-zone" :class="{ 'has-file': pdfFile }"
        @dragover.prevent @drop.prevent="e => { pdfFile = e.dataTransfer.files[0] }"
        @click="pdfFileInput.click()">
        <input ref="pdfFileInput" type="file" accept=".pdf" style="display:none" @change="onPdfFile"/>
        <div class="drop-zone__icon">↑</div>
        <div class="drop-zone__title">{{ pdfFile ? pdfFile.name : 'Drop PDF here or click to upload' }}</div>
        <div class="drop-zone__sub">PDF files only</div>
      </div>
      <div class="submit-row">
        <button class="piq-btn-gold" :disabled="loading || !pdfFile" @click="redactPdf">
          {{ loading ? 'Processing…' : 'Redact PDF' }}
        </button>
      </div>
      <div v-if="currentPdfId" class="success-msg">
        ✓ Redaction complete —
        <button class="link-btn" @click="downloadPdf(currentPdfId)">Download redacted PDF</button>
      </div>
    </div>

    <!-- Files tab -->
    <div v-if="tab === 'files'" class="panel">
      <div v-if="!files.length" class="empty-state">No redacted files yet.</div>
      <div v-else class="piq-table-wrap">
        <table class="piq-table">
          <thead><tr><th>File</th><th>Date</th><th>Style</th><th>Download</th><th></th></tr></thead>
          <tbody>
            <tr v-for="f in files" :key="f.id">
              <td class="bold">{{ f.filename || f.file_name || `File #${f.id}` }}</td>
              <td class="dim">{{ fmtDate(f.created_at) }}</td>
              <td class="dim">{{ f.style || '—' }}</td>
              <td><button class="action-btn" @click="downloadPdf(f.id)">↓ Download</button></td>
              <td><button class="action-btn action-btn--del" @click="deleteFile(f.id)">✕</button></td>
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

.tab-bar { display: flex; gap: .5rem; margin-bottom: 1.25rem; border-bottom: 1px solid var(--border); padding-bottom: .75rem; }
.tab-btn { background: none; border: 1px solid transparent; border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: .875rem; padding: .4rem .9rem; transition: all .15s; }
.tab-btn:hover { color: var(--text-primary); }
.tab-btn.active { border-color: var(--gold); color: var(--gold); }

.panel { }
.err-msg { color: #fc8181; font-size: .875rem; margin-bottom: 1rem; }
.success-msg { color: #48bb78; font-size: .875rem; margin-top: .75rem; }
.link-btn { background: none; border: none; color: var(--gold); cursor: pointer; font-size: .875rem; text-decoration: underline; }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.col-block { display: flex; flex-direction: column; gap: .5rem; }
.col-label { font-size: .72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .05em; text-transform: uppercase; }
.piq-textarea { background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-family: inherit; font-size: .875rem; line-height: 1.6; padding: .75rem; resize: vertical; width: 100%; box-sizing: border-box; }
.piq-textarea:focus { border-color: var(--gold); outline: none; }
.redacted-box { background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; flex: 1; font-size: .875rem; line-height: 1.6; min-height: 200px; padding: .75rem; white-space: pre-wrap; word-break: break-word; color: var(--text-primary); }
.redacted-box--empty { color: var(--text-muted); font-style: italic; }

.options-row { display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
.opt-label { display: flex; align-items: center; gap: .5rem; font-size: .8rem; color: var(--text-muted); }
.opt-label.checkbox { gap: .4rem; cursor: pointer; }
.opt-val { color: var(--gold); font-weight: 600; min-width: 30px; }
.piq-select { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: .8rem; padding: .3rem .6rem; }

.drop-zone { background: var(--bg-card); border: 2px dashed var(--border); border-radius: 10px; cursor: pointer; padding: 2rem; text-align: center; transition: border-color .15s; }
.drop-zone:hover, .drop-zone.has-file { border-color: var(--gold); }
.drop-zone__icon  { color: var(--gold); font-size: 1.5rem; margin-bottom: .4rem; opacity: .6; }
.drop-zone__title { color: var(--text-primary); font-size: .9rem; font-weight: 500; margin-bottom: .2rem; }
.drop-zone__sub   { color: var(--text-muted); font-size: .75rem; }
.submit-row { display: flex; justify-content: flex-end; margin-top: .75rem; }

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
