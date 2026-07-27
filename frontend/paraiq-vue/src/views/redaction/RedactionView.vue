<script setup>
import { ref, onMounted, computed } from 'vue'
import client from '@/api/client'

const tab             = ref('text')
const inputText       = ref('')
const redacted        = ref('')
const findings        = ref([])
const originalPdfUrl  = ref(null)
const redactedPdfUrl  = ref(null)
const selectedDoc     = ref(null)
const vaultDocs       = ref([])
const pickerOpen      = ref(true)
const docFilter       = ref('')
const threshold       = ref(0.5)
const style           = ref('label')
const useClaude       = ref(true)
const loading         = ref(false)
const error           = ref(null)
const files           = ref([])
const currentPdfId    = ref(null)
const presidioOk      = ref(null)

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

async function fetchVaultDocs() {
  try {
    const { data } = await client.get('/redact/documents')
    vaultDocs.value = data.documents || []
  } catch (e) {
    vaultDocs.value = []
  }
}

function selectDoc(doc) {
  selectedDoc.value = doc
  originalPdfUrl.value = doc?.original_url || null
  redactedPdfUrl.value = null
  currentPdfId.value = null
  findings.value = []
  error.value = null
}

async function redactPdf() {
  if (!selectedDoc.value) return
  loading.value = true; error.value = null; currentPdfId.value = null
  redactedPdfUrl.value = null
  try {
    const { data } = await client.post(
      `/redact/case-document/${selectedDoc.value.id}?threshold=${threshold.value}&style=${style.value}&use_claude=${useClaude.value}`
    )
    currentPdfId.value = data.redaction_id || null
    redacted.value = data.redacted_preview || ''
    findings.value = data.findings || []
    presidioOk.value = data.presidio_available

    if (data.download_url) {
      redactedPdfUrl.value = data.download_url
    }
    await fetchFiles()
  } catch(e) {
    error.value = e.response?.data?.detail || 'PDF redaction failed'
  } finally { loading.value = false }
}

function downloadPdf(url) {
  if (!url) return
  window.open(url, '_blank')
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

onMounted(() => {
  fetchFiles()
  fetchVaultDocs()
})
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
    <div v-if="tab === 'pdf'" class="panel pdf-panel">
      <div class="pdf-workspace">
        <!-- Document picker (right side) -->
        <div class="doc-picker" :class="{ collapsed: !pickerOpen }">
          <div class="doc-picker__header" @click="pickerOpen = !pickerOpen">
            <span class="col-label">Document vault</span>
            <span class="doc-picker__toggle">{{ pickerOpen ? '›' : '‹' }}</span>
          </div>
          <div v-if="pickerOpen" class="doc-picker__body">
            <input v-model="docFilter" class="doc-picker__search" placeholder="Search files or cases…"/>
            <div v-if="!vaultDocs.length" class="doc-picker__empty">No documents in the vault yet.<br>Run OCR Intake or Email Intake first.</div>
            <div v-else class="doc-picker__list">
              <button
                v-for="doc in vaultDocs.filter(d => (d.document_name + ' ' + (d.case_number||'') + ' ' + (d.client_name||'')).toLowerCase().includes(docFilter.toLowerCase()))"
                :key="doc.id"
                class="doc-picker__item"
                :class="{ active: selectedDoc?.id === doc.id }"
                @click="selectDoc(doc)"
              >
                <div class="doc-picker__name">{{ doc.document_name }}</div>
                <div class="doc-picker__meta">
                  <span v-if="doc.case_number" class="case-chip">{{ doc.case_number }}</span>
                  <span v-if="doc.client_name">{{ doc.client_name }}</span>
                  <span v-if="doc.doc_type" class="dim">{{ doc.doc_type }}</span>
                </div>
              </button>
            </div>
          </div>
        </div>

        <!-- Preview area -->
        <div class="pdf-preview-wrap">
          <div class="submit-row">
            <div class="selected-doc">
              <span v-if="selectedDoc" class="selected-doc__name">{{ selectedDoc.document_name }}</span>
              <span v-else class="selected-doc__placeholder">Select a document from the vault</span>
            </div>
            <button class="piq-btn-gold" :disabled="loading || !selectedDoc" @click="redactPdf">
              {{ loading ? 'Processing…' : 'Redact File' }}
            </button>
          </div>

          <div class="pdf-preview-row">
            <div class="pdf-preview-col">
              <div class="col-label">Original file</div>
              <iframe v-if="originalPdfUrl" :src="originalPdfUrl" class="pdf-frame" type="application/pdf"></iframe>
              <div v-else class="pdf-frame pdf-frame--empty">Select a vault document to preview the original…</div>
            </div>
            <div class="pdf-preview-col">
              <div class="col-label">Redacted file</div>
              <iframe v-if="redactedPdfUrl" :src="redactedPdfUrl" class="pdf-frame" type="application/pdf"></iframe>
              <div v-else class="pdf-frame pdf-frame--empty">Redacted preview will appear here…</div>
            </div>
          </div>

          <div v-if="currentPdfId" class="success-msg">
            ✓ Redaction complete —
            <button class="link-btn" @click="downloadPdf(redactedPdfUrl)">Download redacted file</button>
          </div>

          <div v-if="findings.length && tab === 'pdf'" class="findings-summary">
            {{ findings.length }} PII finding{{ findings.length !== 1 ? 's' : '' }} detected
            <span v-if="findings.some(f => f.source === 'claude')" class="dim sm">(Claude-enhanced)</span>
          </div>
        </div>
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
              <td><button class="action-btn" @click="downloadPdf(f.download_url)">↓ Download</button></td>
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

.submit-row { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-top: .75rem; }

.pdf-workspace { display: flex; gap: 1rem; min-height: 520px; }
.pdf-preview-wrap { flex: 1; display: flex; flex-direction: column; min-width: 0; }

.doc-picker { width: 320px; flex-shrink: 0; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); display: flex; flex-direction: column; max-height: 620px; transition: width .2s; }
.doc-picker.collapsed { width: 42px; }
.doc-picker__header { display: flex; align-items: center; justify-content: space-between; padding: .65rem .8rem; border-bottom: 1px solid var(--border); cursor: pointer; user-select: none; }
.doc-picker__header .col-label { margin: 0; }
.doc-picker__toggle { color: var(--gold); font-size: 1.1rem; }
.doc-picker__body { display: flex; flex-direction: column; flex: 1; overflow: hidden; }
.doc-picker__search { background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: .8rem; margin: .6rem; padding: .4rem .6rem; }
.doc-picker__search:focus { border-color: var(--gold); outline: none; }
.doc-picker__list { flex: 1; overflow-y: auto; padding: 0 .6rem .6rem; }
.doc-picker__item { width: 100%; text-align: left; background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); cursor: pointer; margin-bottom: .4rem; padding: .55rem .65rem; transition: all .15s; }
.doc-picker__item:hover { border-color: var(--gold); }
.doc-picker__item.active { border-color: var(--gold); background: rgba(246,173,85,.12); }
.doc-picker__name { font-size: .85rem; font-weight: 500; line-height: 1.3; word-break: break-word; }
.doc-picker__meta { display: flex; flex-wrap: wrap; gap: .35rem; align-items: center; margin-top: .25rem; font-size: .72rem; color: var(--text-muted); }
.case-chip { background: rgba(246,173,85,.15); color: #f6ad55; padding: .05rem .35rem; border-radius: 4px; font-weight: 600; }
.doc-picker__empty { color: var(--text-muted); font-size: .8rem; padding: 1rem; text-align: center; }

.selected-doc { min-width: 0; }
.selected-doc__name { color: var(--text-primary); font-weight: 500; font-size: .9rem; }
.selected-doc__placeholder { color: var(--text-muted); font-size: .85rem; }

.pdf-preview-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1rem; flex: 1; }
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
