<script setup>
const token = () => localStorage.getItem('paraiq_token')
import { ref, computed, onMounted } from 'vue'
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

// ── Result formatting (replaces raw JSON dump) ─────────────────────────────
function firstNonNull(...args) { return args.find(a => a !== undefined && a !== null) }

const extractedText = computed(() => {
  const r = result.value
  if (!r) return ''
  if (typeof r === 'string') return r
  return firstNonNull(r.ocr?.text, r.text, r.transcription, '')
})

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}
function boldify(s) {
  return s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}
function renderExtractedText(text) {
  if (!text) return ''
  const lines = escapeHtml(text).split('\n')
  let html = ''
  let i = 0
  let paraBuf = []
  function flushPara() {
    if (paraBuf.length) { html += `<p>${paraBuf.join(' ')}</p>`; paraBuf = [] }
  }
  while (i < lines.length) {
    const line = lines[i]
    if (/^\|.*\|\s*$/.test(line)) {
      flushPara()
      const tableLines = []
      while (i < lines.length && /^\|.*\|\s*$/.test(lines[i])) { tableLines.push(lines[i]); i++ }
      const rows = tableLines
        .map(l => l.replace(/^\||\|$/g, '').split('|').map(c => c.trim()))
        .filter(cells => !cells.every(c => /^:?-+:?$/.test(c)))
      if (rows.length) {
        const header = rows[0]
        const body = rows.slice(1)
        html += '<table class="ocr-table"><tbody>'
        html += `<tr>${header.map(h=>`<th>${boldify(h)}</th>`).join('')}</tr>`
        body.forEach(r => { html += `<tr>${r.map(c=>`<td>${boldify(c)}</td>`).join('')}</tr>` })
        html += '</tbody></table>'
      }
      continue
    }
    const h3 = line.match(/^###\s+(.*)/)
    const h2 = line.match(/^##\s+(.*)/)
    const h1 = line.match(/^#\s+(.*)/)
    if (h3) { flushPara(); html += `<h5 class="ocr-h">${boldify(h3[1])}</h5>`; i++; continue }
    if (h2) { flushPara(); html += `<h4 class="ocr-h">${boldify(h2[1])}</h4>`; i++; continue }
    if (h1) { flushPara(); html += `<h3 class="ocr-h">${boldify(h1[1])}</h3>`; i++; continue }
    if (/^_{3,}$/.test(line.trim())) { flushPara(); html += '<hr class="ocr-hr">'; i++; continue }
    if (line.trim() === '') { flushPara(); i++; continue }
    paraBuf.push(boldify(line))
    i++
  }
  flushPara()
  return html
}
const formattedOcrText = computed(() => renderExtractedText(extractedText.value))

const riskInfo = computed(() => (result.value && typeof result.value === 'object') ? result.value.risk : null)
const CATEGORY_LABELS = { personal_injury: 'Personal Injury' }
function friendlyCategory(c) {
  return CATEGORY_LABELS[c] || (c || '').replace(/_/g,' ').replace(/\b\w/g, ch => ch.toUpperCase())
}

// Drops entities that are clearly NER noise (markdown symbols, whole lines
// mistagged as an entity, low-value bare single digits) without trying to
// re-classify genuinely ambiguous short tokens (e.g. abbreviations) — that
// would risk hiding real entities in other documents.
function isJunkEntity(e) {
  const t = (e.text || '').trim()
  if (!t) return true
  if (/^[^\w]+$/.test(t)) return true
  if (t.length > 40) return true
  if (e.type === 'MONEY' && !/[\d$]/.test(t)) return true
  if (e.type === 'CARDINAL' && /^\d{1,2}$/.test(t) && Number(t) <= 3) return true
  return false
}
const cleanEntities = computed(() => {
  const r = result.value
  const ents = (r && typeof r === 'object') ? (r.entities || []) : []
  return ents.filter(e => !isJunkEntity(e))
})
const ENTITY_TYPE_LABELS = { PERSON:'Person', ORG:'Organization', GPE:'Location', DATE:'Date', MONEY:'Amount', CARDINAL:'Number' }
function friendlyEntityType(t) { return ENTITY_TYPE_LABELS[t] || t }

const FORM_FIELD_LABELS = {
  doc_type: 'Document Type',
  client_name: 'Client Name',
  date_of_birth: 'Date of Birth',
  ssn_last4: 'SSN (Last 4)',
  exposure_location: 'Exposure Location',
  presence_dates: 'Presence Dates',
  employer: 'Employer',
  provider_name: 'Provider Name',
  benefit_amount: 'Benefit Amount',
  annual_income: 'Annual Income',
  medical_conditions: 'Medical Conditions',
  phone: 'Phone', 
  email: 'Email', 
  urgent: 'Urgent',
}
const formFieldRows = computed(() => {
  const r = result.value
  const ff = (r && typeof r === 'object') ? r.form_fields : null
  if (!ff) return []
  const rows = Object.entries(FORM_FIELD_LABELS)
    .filter(([k]) => k in ff && ff[k] !== null)
    .map(([k, label]) => {
      let val = ff[k]
      if (Array.isArray(val)) val = val.join(', ')
      if (k === 'urgent') val = val ? 'Yes' : 'No'
      return { label, value: val }
    })
  if (Array.isArray(ff.key_facts) && ff.key_facts.length) {
    rows.push({ label: 'Key Facts', value: ff.key_facts.join('; ') })
  }
  return rows
})

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
      <div v-if="extractedText" class="result-block">
        <div class="result-block__label">Extracted Text</div>
        <div class="ocr-text" v-html="formattedOcrText"></div>
      </div>
      <div v-if="riskInfo" class="result-block">
        <div class="result-block__label">Risk Assessment</div>
        <div class="risk-row">
          <span class="status-pill" :class="'risk-' + riskInfo.level">{{ riskInfo.level }} risk</span>
          <span class="risk-score">Score: {{ riskInfo.score }}</span>
        </div>
        <ul v-if="riskInfo.top_signals && riskInfo.top_signals.length" class="risk-signals">
          <li v-for="(s, idx) in riskInfo.top_signals" :key="idx">
            {{ friendlyCategory(s.category) }} — {{ s.matches }} match<span v-if="s.matches !== 1">es</span>
          </li>
        </ul>
      </div>
      <div v-if="cleanEntities.length" class="result-block">
        <div class="result-block__label">Key Entities</div>
        <div class="piq-table-wrap">
          <table class="piq-table">
            <thead><tr><th>Text</th><th>Type</th></tr></thead>
            <tbody>
              <tr v-for="(e, idx) in cleanEntities" :key="idx">
                <td class="bold">{{ e.text }}</td>
                <td class="dim">{{ friendlyEntityType(e.type) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-if="formFieldRows.length" class="result-block">
        <div class="result-block__label">Form Fields</div>
        <div class="field-grid">
          <div v-for="f in formFieldRows" :key="f.label" class="field-row">
            <span class="field-row__label">{{ f.label }}</span>
            <span class="field-row__value" :class="{ dim: !f.value }">{{ f.value || 'Not detected' }}</span>
          </div>
        </div>
      </div>
      <details class="raw-fallback">
        <summary>Raw response (debug)</summary>
        <pre class="result-pre">{{ typeof result === 'string' ? result : JSON.stringify(result, null, 2) }}</pre>
      </details>
    </div>

    <!-- History -->
    <div v-if="history.length" class="history-section">
      <div class="section-label">Recent intake history</div>
      <div class="piq-table-wrap">
        <table class="piq-table">
              <div v-if="history.length" class="history-section">
      <div class="section-label">Recent intake history</div>
      <div class="piq-table-wrap">
        <table class="piq-table">
          <thead><tr><th>File</th><th>Date</th><th>OCR Engine</th><th>View File</th></tr></thead>
          <tbody>
            <tr v-for="h in history" :key="h.id">
              <td class="bold">{{ h.filename || '—' }}</td>
              <td class="dim">{{ fmtDate(h.created_at) }}</td>
              <td class="dim">{{ h.ocr_engine || '—' }}</td>
              <td><a v-if="h.file_url" :href="`/intake/file/${h.file_url}?token=${token()}`" target="_blank" class="bl-link">View PDF ↗</a>
                <span v-else class="dim">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
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
.result-block { margin-bottom: 1.5rem; }
.result-block:last-child { margin-bottom: 0; }
.result-block__label { font-size: .72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .05em; margin-bottom: .6rem; text-transform: uppercase; }
.ocr-text { background: var(--bg-raised, #0d0d1a); border-radius: 6px; padding: 1rem 1.25rem; color: var(--text-primary); font-size: .875rem; line-height: 1.7; }
.ocr-text p { margin: 0 0 .85rem; }
.ocr-text p:last-child { margin-bottom: 0; }
.ocr-h { color: var(--gold); font-family: var(--font-display); margin: 1rem 0 .5rem; }
.ocr-h:first-child { margin-top: 0; }
.ocr-table { border-collapse: collapse; margin: .5rem 0 1rem; width: 100%; }
.ocr-table td, .ocr-table th { border: 1px solid var(--border); padding: .4rem .7rem; font-size: .83rem; text-align: left; }
.ocr-table th { background: var(--bg-card); color: var(--text-muted); font-weight: 600; }
.ocr-hr { border: none; border-top: 1px solid var(--border); margin: 1rem 0; }
.risk-row { align-items: center; display: flex; gap: .75rem; margin-bottom: .5rem; }
.risk-score { color: var(--text-muted); font-size: .82rem; }
.risk-low { background: rgba(72,187,120,.15); color: #48bb78; }
.risk-medium { background: rgba(214,158,46,.15); color: #d69e2e; }
.risk-high { background: rgba(252,129,129,.15); color: #fc8181; }
.risk-signals { color: var(--text-muted); font-size: .82rem; line-height: 1.7; margin: 0; padding-left: 1.1rem; }
.field-grid { display: grid; gap: .6rem; grid-template-columns: 1fr 1fr; }
.field-row { display: flex; flex-direction: column; gap: .15rem; }
.field-row__label { color: var(--text-muted); font-size: .72rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.field-row__value { color: var(--text-primary); font-size: .875rem; }
.field-row__value.dim { color: var(--text-muted); font-style: italic; }
.raw-fallback { margin-top: 1rem; }
.raw-fallback summary { color: var(--text-muted); cursor: pointer; font-size: .78rem; }
.raw-fallback .result-pre { margin-top: .5rem; }
</style>
