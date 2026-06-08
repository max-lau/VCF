<template>
  <div class="da-root">

    <!-- Doc type selector -->
    <div class="da-selector">
      <button v-for="dt in DOC_TYPES" :key="dt.key"
        :class="['da-type-btn', { active: docType === dt.key }]"
        @click="selectType(dt.key)">
        <span class="da-type-icon">{{ dt.icon }}</span>
        <span class="da-type-label">{{ dt.label }}</span>
      </button>
    </div>

    <!-- Config panel -->
    <div class="da-config">
      <div class="da-config__left">
        <div v-if="docType === 'motion'" class="field-row">
          <label class="field__label">Motion type</label>
          <select v-model="motionType" class="piq-input">
            <option value="motion_to_dismiss">Motion to Dismiss</option>
            <option value="motion_to_compel">Motion to Compel</option>
            <option value="msj">Motion for Summary Judgment</option>
            <option value="motion_in_limine">Motion in Limine</option>
          </select>
        </div>
        <div class="field-row">
          <label class="field__label">Additional instructions <span class="dim">(optional)</span></label>
          <textarea v-model="instructions" class="piq-input da-instructions"
            :placeholder="currentType.placeholder" rows="2"></textarea>
        </div>
      </div>
      <div class="da-config__right">
        <button class="btn-generate" @click="generate" :disabled="generating">
          <span v-if="generating" class="spinner">⟳</span>
          <span v-else>✦</span>
          {{ generating ? 'Drafting…' : 'Generate draft' }}
        </button>
      </div>
    </div>

    <!-- Generating -->
    <div v-if="generating" class="da-generating">
      <div class="da-generating__pulse">✦</div>
      <div class="da-generating__text">Claude is drafting your {{ currentType.label.toLowerCase() }}…</div>
    </div>

    <!-- Output -->
    <div v-else-if="draft" class="da-output">
      <div class="da-output__toolbar">
        <div class="da-output__meta">
          <span class="da-output__badge">{{ currentType.label }}</span>
          <span class="dim sm">{{ draft.case_number }} · {{ draft.generated_at }}</span>
        </div>
        <div class="da-output__actions">
          <button class="btn-action" :class="{ 'btn-action--active': viewMode === 'preview' }"
            @click="viewMode = 'preview'">Preview</button>
          <button class="btn-action" :class="{ 'btn-action--active': viewMode === 'edit' }"
            @click="viewMode = 'edit'">Edit</button>
          <div class="da-divider"></div>
          <button class="btn-action" @click="copyToClipboard" :class="{ success: copied }">
            {{ copied ? '✓ Copied' : '⎘ Copy' }}
          </button>
          <button class="btn-action" @click="downloadDocx">↓ Word</button>
          <button class="btn-action" @click="downloadTxt">↓ TXT</button>
          <button class="btn-action btn-save" @click="saveDraft" :disabled="saving">
            {{ saving ? 'Saving…' : '⊙ Save' }}
          </button>
          <button class="btn-action" @click="regenerate">↻ Regenerate</button>
        </div>
      </div>

      <!-- Preview mode -->
      <div v-if="viewMode === 'preview'"
        class="da-preview"
        v-html="renderedContent">
      </div>

      <!-- Edit mode -->
      <textarea v-else
        v-model="draft.content"
        class="da-editor"
        spellcheck="true">
      </textarea>

      <div class="da-output__footer dim sm">
        {{ wordCount }} words ·
        <span v-if="viewMode === 'preview'">Click <strong>Edit</strong> to make changes</span>
        <span v-else>Editing — click <strong>Preview</strong> to see formatted output</span>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else class="da-empty">
      <div class="da-empty__icon">{{ currentType.icon }}</div>
      <div class="da-empty__title">{{ currentType.label }}</div>
      <div class="da-empty__sub">{{ currentType.description }}</div>
      <button class="btn-generate sm" @click="generate">✦ Generate draft</button>
    </div>

    <!-- Saved drafts -->
    <div v-if="savedDrafts.length" class="da-saved">
      <div class="da-saved__title dim sm">Saved drafts</div>
      <div v-for="d in savedDrafts" :key="d.id" class="da-saved__item">
        <span class="da-saved__type">{{ d.doc_type }}</span>
        <span class="dim sm">{{ fmtDate(d.created_at) }}</span>
      </div>
    </div>

    <!-- Toast -->
    <Transition name="toast">
      <div v-if="toast" class="da-toast">{{ toast }}</div>
    </Transition>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import { marked } from 'marked'
import { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType } from 'docx'
import { saveAs } from 'file-saver'

const props = defineProps({
  caseId: { type: [Number, String], required: true },
})

const token   = () => localStorage.getItem('paraiq_token')
const authHdr = () => ({ Authorization: 'Bearer ' + token() })

const DOC_TYPES = [
  { key: 'brief',  label: 'Case Brief',    icon: '📋',
    description: 'AI-generated structured case brief with facts, legal issues, risk assessment and next steps.',
    placeholder: 'e.g. Focus on the employment law aspects and statute of limitations issues.' },
  { key: 'motion', label: 'Motion',         icon: '⚖️',
    description: 'Draft a motion for filing — dismiss, compel, summary judgment, or in limine.',
    placeholder: 'e.g. Emphasize lack of personal jurisdiction. Cite Twombly/Iqbal standards.' },
  { key: 'letter', label: 'Client Letter',  icon: '✉️',
    description: 'Professional client status update letter summarizing case progress and next steps.',
    placeholder: 'e.g. Keep it concise. Client is anxious about timeline. Emphasize our strong position.' },
  { key: 'demand', label: 'Demand Letter',  icon: '📨',
    description: 'Formal demand letter to opposing party with facts, damages, and response deadline.',
    placeholder: 'e.g. Demand $250,000 in damages. Give 30-day response window. Firm but professional tone.' },
]

const docType      = ref('brief')
const motionType   = ref('motion_to_dismiss')
const instructions = ref('')
const draft        = ref(null)
const generating   = ref(false)
const viewMode     = ref('preview')
const copied       = ref(false)
const saving       = ref(false)
const savedDrafts  = ref([])
const toast        = ref('')

const currentType = computed(() => DOC_TYPES.find(d => d.key === docType.value))

const wordCount = computed(() => {
  if (!draft.value?.content) return 0
  return draft.value.content.trim().split(/\s+/).length
})

const renderedContent = computed(() => {
  if (!draft.value?.content) return ''
  return marked.parse(draft.value.content)
})

function selectType(key) {
  docType.value = key
  draft.value   = null
}

async function generate() {
  generating.value = true
  draft.value      = null
  viewMode.value   = 'preview'
  try {
    const endpoint = `/draft/${docType.value}/${props.caseId}`
    const payload  = { instructions: instructions.value }
    if (docType.value === 'motion') payload.motion_type = motionType.value
    const { data } = await axios.post(endpoint, payload, { headers: authHdr() })
    draft.value = data
  } catch (e) {
    showToast('Generation failed — ' + (e?.response?.data?.detail || e.message))
  } finally {
    generating.value = false
  }
}

function regenerate() { draft.value = null; generate() }

async function copyToClipboard() {
  if (!draft.value?.content) return
  // Strip markdown for clean copy
  const clean = draft.value.content
    .replace(/#{1,6}\s+/g, '')
    .replace(/\*\*/g, '')
    .replace(/\*/g, '')
    .replace(/---/g, '---')
  await navigator.clipboard.writeText(clean)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

function downloadTxt() {
  if (!draft.value?.content) return
  const blob = new Blob([draft.value.content], { type: 'text/plain' })
  const a    = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${draft.value.doc_type}-${draft.value.case_number}.txt`
  a.click()
}

async function downloadDocx() {
  if (!draft.value?.content) return
  const lines    = draft.value.content.split('\n')
  const children = []

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) {
      children.push(new Paragraph({ text: '' }))
      continue
    }
    // Headings
    const h1 = trimmed.match(/^#\s+(.+)/)
    const h2 = trimmed.match(/^##\s+(.+)/)
    const h3 = trimmed.match(/^###\s+(.+)/)
    if (h1) {
      children.push(new Paragraph({ text: h1[1], heading: HeadingLevel.HEADING_1 }))
    } else if (h2) {
      children.push(new Paragraph({ text: h2[1], heading: HeadingLevel.HEADING_2 }))
    } else if (h3) {
      children.push(new Paragraph({ text: h3[1], heading: HeadingLevel.HEADING_3 }))
    } else if (trimmed === '---') {
      children.push(new Paragraph({ text: '─────────────────────────────────', alignment: AlignmentType.CENTER }))
    } else {
      // Parse inline bold
      const parts = trimmed.split(/(\*\*[^*]+\*\*)/)
      const runs  = parts.map(p => {
        if (p.startsWith('**') && p.endsWith('**')) {
          return new TextRun({ text: p.slice(2, -2), bold: true })
        }
        return new TextRun({ text: p.replace(/\*/g, '') })
      })
      children.push(new Paragraph({ children: runs }))
    }
  }

  const doc = new Document({
    creator: 'ParaIQ Legal Intelligence',
    title:   `${currentType.value.label} — ${draft.value.case_number}`,
    sections: [{
      properties: {},
      children,
    }],
  })

  const blob = await Packer.toBlob(doc)
  saveAs(blob, `${draft.value.doc_type}-${draft.value.case_number}.docx`)
  showToast('Downloaded as Word document')
}

async function saveDraft() {
  if (!draft.value?.content) return
  saving.value = true
  try {
    await axios.post(`/draft/save/${props.caseId}`, {
      doc_type:  draft.value.doc_type,
      doc_label: currentType.value.label,
      content:   draft.value.content,
    }, { headers: authHdr() })
    showToast('Draft saved')
    fetchSavedDrafts()
  } catch { showToast('Save failed') }
  finally { saving.value = false }
}

async function fetchSavedDrafts() {
  try {
    const { data } = await axios.get(`/draft/drafts/${props.caseId}`, { headers: authHdr() })
    savedDrafts.value = data.drafts || []
  } catch { savedDrafts.value = [] }
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function showToast(msg) {
  toast.value = msg
  setTimeout(() => { toast.value = '' }, 2500)
}

onMounted(fetchSavedDrafts)
</script>

<style scoped>
.da-root { padding: 0; display: flex; flex-direction: column; gap: 1.25rem; }

.da-selector { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.da-type-btn { display: flex; align-items: center; gap: 0.5rem; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; cursor: pointer; padding: 0.6rem 1rem; color: var(--text-muted); transition: all .15s; }
.da-type-btn:hover  { border-color: var(--gold); color: var(--text-primary); }
.da-type-btn.active { border-color: var(--gold); color: var(--gold); background: rgba(201,168,76,.06); }
.da-type-icon  { font-size: 1rem; }
.da-type-label { font-size: 0.82rem; font-weight: 500; }

.da-config { display: flex; gap: 1rem; align-items: flex-end; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }
.da-config__left  { flex: 1; display: flex; flex-direction: column; gap: 0.75rem; }
.da-config__right { flex-shrink: 0; }
.field-row    { display: flex; flex-direction: column; gap: 0.3rem; }
.field__label { color: var(--text-muted); font-size: 0.68rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.piq-input    { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-family: inherit; font-size: 0.875rem; outline: none; padding: 0.45rem 0.75rem; }
.piq-input:focus { border-color: var(--gold); }
.da-instructions { resize: vertical; width: 100%; box-sizing: border-box; }

.btn-generate { background: var(--gold); border: none; border-radius: 7px; color: #0a0a14; cursor: pointer; font-size: 0.85rem; font-weight: 700; padding: 0.65rem 1.4rem; display: flex; align-items: center; gap: 0.4rem; transition: opacity .15s; white-space: nowrap; }
.btn-generate:hover:not(:disabled) { opacity: 0.88; }
.btn-generate:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-generate.sm { font-size: 0.8rem; padding: 0.5rem 1.1rem; }
.spinner { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }

.da-generating { display: flex; flex-direction: column; align-items: center; gap: 1rem; padding: 3rem; }
.da-generating__pulse { font-size: 2rem; color: var(--gold); animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.4;transform:scale(0.85)} }
.da-generating__text { color: var(--text-muted); font-size: 0.9rem; }

.da-output { display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.da-output__toolbar { display: flex; align-items: center; justify-content: space-between; padding: 0.75rem 1rem; background: var(--bg-card); border-bottom: 1px solid var(--border); flex-wrap: wrap; gap: 0.5rem; }
.da-output__meta    { display: flex; align-items: center; gap: 0.75rem; }
.da-output__badge   { background: rgba(201,168,76,.12); border: 1px solid rgba(201,168,76,.3); border-radius: 4px; color: var(--gold); font-size: 0.7rem; font-weight: 700; padding: 0.15rem 0.5rem; text-transform: uppercase; }
.da-output__actions { display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center; }
.da-divider { width: 1px; height: 18px; background: var(--border); margin: 0 0.2rem; }
.btn-action { background: transparent; border: 1px solid var(--border); border-radius: 5px; color: var(--text-muted); cursor: pointer; font-size: 0.75rem; padding: 0.3rem 0.75rem; transition: all .15s; }
.btn-action:hover { border-color: var(--gold); color: var(--gold); }
.btn-action--active { border-color: var(--gold); color: var(--gold); background: rgba(201,168,76,.08); }
.btn-action.success { border-color: #48bb78; color: #48bb78; }
.btn-action:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-save { border-color: rgba(201,168,76,.4); color: var(--gold); }

/* Rendered preview */
.da-preview {
  background: white;
  color: #1a1a1a;
  font-family: 'Georgia', 'Times New Roman', serif;
  font-size: 0.95rem;
  line-height: 1.8;
  min-height: 500px;
  padding: 2.5rem 3rem;
  overflow-y: auto;
}
.da-preview :deep(h1) { font-size: 1.3rem; font-weight: 700; margin: 1.5rem 0 0.5rem; border-bottom: 2px solid #1a1a1a; padding-bottom: 0.25rem; }
.da-preview :deep(h2) { font-size: 1.1rem; font-weight: 700; margin: 1.25rem 0 0.4rem; }
.da-preview :deep(h3) { font-size: 1rem; font-weight: 700; margin: 1rem 0 0.3rem; }
.da-preview :deep(p)  { margin: 0.6rem 0; }
.da-preview :deep(ul), .da-preview :deep(ol) { margin: 0.5rem 0 0.5rem 1.5rem; }
.da-preview :deep(li) { margin: 0.3rem 0; }
.da-preview :deep(strong) { font-weight: 700; }
.da-preview :deep(hr) { border: none; border-top: 1px solid #ccc; margin: 1rem 0; }
.da-preview :deep(blockquote) { border-left: 3px solid #ccc; margin: 0.75rem 0; padding-left: 1rem; color: #555; }

.da-editor { width: 100%; box-sizing: border-box; background: var(--bg-raised); border: none; outline: none; color: var(--text-primary); font-family: var(--font-mono); font-size: 0.8rem; line-height: 1.7; min-height: 500px; padding: 1.25rem 1.5rem; resize: vertical; }
.da-output__footer { padding: 0.5rem 1rem; background: var(--bg-card); border-top: 1px solid var(--border); }

.da-empty { display: flex; flex-direction: column; align-items: center; gap: 0.75rem; padding: 3rem 2rem; text-align: center; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; }
.da-empty__icon  { font-size: 2rem; opacity: 0.35; }
.da-empty__title { color: var(--text-primary); font-size: 1rem; font-weight: 600; }
.da-empty__sub   { color: var(--text-muted); font-size: 0.82rem; max-width: 380px; line-height: 1.5; }

.da-saved { border-top: 1px solid var(--border); padding-top: 1rem; }
.da-saved__title { margin-bottom: 0.5rem; }
.da-saved__item  { display: flex; align-items: center; gap: 0.75rem; padding: 0.4rem 0; border-bottom: 1px solid var(--border); }
.da-saved__type  { font-size: 0.75rem; font-weight: 600; color: var(--text-muted); text-transform: capitalize; }

.da-toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: var(--bg-raised); border: 1px solid var(--border); color: var(--text-primary); font-size: 0.8rem; padding: 8px 16px; border-radius: 8px; z-index: 2000; }
.toast-enter-active, .toast-leave-active { transition: all 0.2s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(6px); }

.dim { color: var(--text-muted); }
.sm  { font-size: 0.78rem; }
</style>
