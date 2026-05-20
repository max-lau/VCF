<template>
  <!-- UPLOAD MODAL OVERLAY -->
  <Teleport to="body">
    <div v-if="show" class="modal-overlay" @click.self="close">
      <div class="upload-modal">

        <!-- HEADER -->
        <div class="modal-header">
          <div class="modal-title-group">
            <h2>Upload Documents</h2>
            <p class="modal-subtitle">Matter: <strong>{{ matterName || `#${matterId}` }}</strong></p>
          </div>
          <button class="close-btn" @click="close">✕</button>
        </div>

        <!-- DROP ZONE -->
        <div
          class="drop-zone"
          :class="{ dragging: isDragging, 'has-files': stagedFiles.length }"
          @dragenter.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @dragover.prevent
          @drop.prevent="onDrop"
          @click="triggerFilePicker"
        >
          <input
            ref="fileInput"
            type="file"
            multiple
            accept=".pdf,.docx,.doc,.txt,.csv,.xlsx,.mp3,.mp4,.wav,.m4a"
            style="display:none"
            @change="onFileSelect"
          />
          <div v-if="!stagedFiles.length" class="drop-prompt">
            <div class="drop-icon">📂</div>
            <p class="drop-main">Drop files here or <span class="link">browse</span></p>
            <p class="drop-sub">PDF · DOCX · TXT · XLSX · MP3 · MP4 · WAV</p>
          </div>
          <div v-else class="file-list">
            <div
              v-for="(f, i) in stagedFiles"
              :key="i"
              class="file-row"
              :class="fileStatusClass(f)"
              @click.stop
            >
              <span class="file-icon">{{ fileIcon(f.file.name) }}</span>
              <div class="file-info">
                <span class="file-name">{{ f.file.name }}</span>
                <span class="file-meta">{{ formatSize(f.file.size) }}</span>
              </div>

              <!-- Doc type selector -->
              <select v-if="!f.done && !f.error" v-model="f.docType" class="doc-type-select">
                <option value="pleading">Pleading</option>
                <option value="motion">Motion</option>
                <option value="contract">Contract</option>
                <option value="deposition">Deposition</option>
                <option value="correspondence">Correspondence</option>
                <option value="evidence">Evidence</option>
                <option value="financial">Financial</option>
                <option value="medical">Medical</option>
                <option value="other">Other</option>
              </select>

              <!-- Progress bar -->
              <div v-if="f.uploading" class="progress-wrap">
                <div class="progress-bar" :style="{ width: f.progress + '%' }"></div>
              </div>

              <!-- Status badges -->
              <span v-if="f.done" class="badge done">✓ Done</span>
              <span v-if="f.error" class="badge error" :title="f.error">✕ Failed</span>

              <button v-if="!f.uploading && !f.done" class="remove-btn" @click.stop="removeFile(i)">✕</button>
            </div>

            <!-- Add more -->
            <button class="add-more-btn" @click.stop="triggerFilePicker">+ Add more files</button>
          </div>
        </div>

        <!-- GLOBAL DOC TYPE -->
        <div v-if="stagedFiles.length" class="global-options">
          <label>Set all types to:</label>
          <select v-model="globalDocType" @change="applyGlobalType" class="global-select">
            <option value="">— individual —</option>
            <option value="pleading">Pleading</option>
            <option value="motion">Motion</option>
            <option value="contract">Contract</option>
            <option value="deposition">Deposition</option>
            <option value="correspondence">Correspondence</option>
            <option value="evidence">Evidence</option>
            <option value="financial">Financial</option>
            <option value="medical">Medical</option>
            <option value="other">Other</option>
          </select>

          <label class="checkbox-label">
            <input type="checkbox" v-model="runOCR" />
            Run OCR / transcription
          </label>
        </div>

        <!-- SUMMARY BAR -->
        <div v-if="stagedFiles.length" class="summary-bar">
          <span class="summary-item">{{ pendingCount }} pending</span>
          <span class="summary-item done-text">{{ doneCount }} uploaded</span>
          <span v-if="errorCount" class="summary-item error-text">{{ errorCount }} failed</span>
        </div>

        <!-- ACTIONS -->
        <div class="modal-actions">
          <button class="btn-secondary" @click="close" :disabled="uploading">
            {{ allDone ? 'Close' : 'Cancel' }}
          </button>
          <button
            class="btn-primary"
            :disabled="!pendingCount || uploading"
            @click="uploadAll"
          >
            <span v-if="uploading" class="spinner"></span>
            <span v-else>
              Upload {{ pendingCount }} {{ pendingCount === 1 ? 'File' : 'Files' }}
            </span>
          </button>
        </div>

      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  show:       { type: Boolean, default: false },
  matterId:   { type: [Number, String], default: 0 },
  matterName:   { type: String, default: '' },
  caseNumber:  { type: String, default: '' },
})

const emit = defineEmits(['close', 'uploaded'])

const fileInput    = ref(null)
const stagedFiles  = ref([])
const isDragging   = ref(false)
const uploading    = ref(false)
const globalDocType = ref('')
const runOCR       = ref(true)

// ── Computed ───────────────────────────────────────────────────────────────

const pendingCount = computed(() => stagedFiles.value.filter(f => !f.done && !f.error).length)
const doneCount    = computed(() => stagedFiles.value.filter(f => f.done).length)
const errorCount   = computed(() => stagedFiles.value.filter(f => f.error).length)
const allDone      = computed(() => stagedFiles.value.length > 0 && pendingCount.value === 0)

// ── File helpers ───────────────────────────────────────────────────────────

function fileIcon(name) {
  const ext = name.split('.').pop().toLowerCase()
  const map = { pdf:'📄', docx:'📝', doc:'📝', txt:'📃', xlsx:'📊', csv:'📊',
                mp3:'🎵', mp4:'🎬', wav:'🎵', m4a:'🎵' }
  return map[ext] || '📁'
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024**2) return `${(bytes/1024).toFixed(1)} KB`
  return `${(bytes/1024**2).toFixed(1)} MB`
}

function fileStatusClass(f) {
  if (f.done) return 'status-done'
  if (f.error) return 'status-error'
  if (f.uploading) return 'status-uploading'
  return ''
}

// ── Drag & drop ────────────────────────────────────────────────────────────

function onDrop(e) {
  isDragging.value = false
  addFiles(Array.from(e.dataTransfer.files))
}

function onFileSelect(e) {
  addFiles(Array.from(e.target.files))
  e.target.value = ''
}

function addFiles(files) {
  const allowed = ['pdf','docx','doc','txt','csv','xlsx','mp3','mp4','wav','m4a']
  for (const file of files) {
    const ext = file.name.split('.').pop().toLowerCase()
    if (!allowed.includes(ext)) continue
    // Avoid duplicates by name+size
    if (stagedFiles.value.find(f => f.file.name === file.name && f.file.size === file.size)) continue
    stagedFiles.value.push({
      file,
      docType:   guessDocType(file.name),
      progress:  0,
      uploading: false,
      done:      false,
      error:     null,
    })
  }
}

function guessDocType(name) {
  const n = name.toLowerCase()
  if (n.includes('depo')) return 'deposition'
  if (n.includes('contract') || n.includes('agreement')) return 'contract'
  if (n.includes('motion') || n.includes('brief')) return 'motion'
  if (n.includes('complaint') || n.includes('answer') || n.includes('pleading')) return 'pleading'
  if (/\.(mp3|mp4|wav|m4a)$/.test(n)) return 'deposition'
  return 'other'
}

function triggerFilePicker() {
  fileInput.value?.click()
}

function removeFile(i) {
  stagedFiles.value.splice(i, 1)
}

function applyGlobalType() {
  if (!globalDocType.value) return
  stagedFiles.value.forEach(f => { if (!f.done) f.docType = globalDocType.value })
}

// ── Upload ─────────────────────────────────────────────────────────────────

async function uploadAll() {
  uploading.value = true
  const token = localStorage.getItem('paraiq_token')
  const pending = stagedFiles.value.filter(f => !f.done && !f.error)

  for (const staged of pending) {
    staged.uploading = true
    staged.progress  = 0
    staged.error     = null

    try {
      const fd = new FormData()
      fd.append('files', staged.file)
      fd.append('case_id', String(props.matterId))
      fd.append('doc_type', staged.docType)
      fd.append('case_number', props.caseNumber)
      fd.append('run_ocr', runOCR.value ? '1' : '0')

      // XHR for real progress
      await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('POST', '/api/discovery/upload')
        xhr.setRequestHeader('Authorization', `Bearer ${token}`)

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            staged.progress = Math.round((e.loaded / e.total) * 90)
          }
        }

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            staged.progress = 100
            staged.done     = true
            staged.uploading = false
            resolve(JSON.parse(xhr.responseText))
          } else {
            let msg = `HTTP ${xhr.status}`
            try { msg = JSON.parse(xhr.responseText).detail || msg } catch {}
            reject(new Error(msg))
          }
        }

        xhr.onerror = () => reject(new Error('Network error'))
        xhr.send(fd)
      })

      emit('uploaded', { file: staged.file.name, docType: staged.docType })

    } catch (e) {
      staged.error     = e.message
      staged.uploading = false
    }
  }

  uploading.value = false
}

// ── Close ──────────────────────────────────────────────────────────────────

function close() {
  if (uploading.value) return
  stagedFiles.value = []
  globalDocType.value = ''
  emit('close')
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.7);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.upload-modal {
  background: var(--surface, #111122);
  border: 1px solid var(--border-color, #2a2a3a);
  border-radius: 14px;
  width: 100%;
  max-width: 620px;
  max-height: 90vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(0,0,0,0.6);
}

/* Header */
.modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 24px 24px 0;
}
.modal-title-group h2 {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary, #e0e0e0);
  margin: 0 0 4px;
}
.modal-subtitle {
  font-size: 12px;
  color: var(--text-muted, #888);
  margin: 0;
}
.modal-subtitle strong { color: var(--text-primary, #ccc); }

.close-btn {
  background: none;
  border: none;
  color: var(--text-muted, #888);
  font-size: 16px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: color 0.15s;
  line-height: 1;
}
.close-btn:hover { color: var(--text-primary, #e0e0e0); }

/* Drop zone */
.drop-zone {
  margin: 20px 24px 0;
  border: 2px dashed var(--border-color, #2a2a3a);
  border-radius: 10px;
  min-height: 140px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
}
.drop-zone.dragging,
.drop-zone:hover {
  border-color: var(--accent, #7b6ff0);
  background: rgba(123,111,240,0.05);
}
.drop-zone.has-files {
  cursor: default;
  align-items: flex-start;
  min-height: unset;
}

.drop-prompt { text-align: center; padding: 32px 20px; }
.drop-icon { font-size: 36px; margin-bottom: 12px; }
.drop-main { font-size: 14px; color: var(--text-muted, #aaa); margin: 0 0 6px; }
.drop-main .link { color: var(--accent, #7b6ff0); }
.drop-sub { font-size: 11px; color: var(--text-muted, #555); margin: 0; }

/* File list */
.file-list { width: 100%; padding: 12px; }

.file-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  margin-bottom: 6px;
  background: var(--input-bg, #0d0d1a);
  border: 1px solid var(--border-color, #1e1e30);
  transition: border-color 0.15s;
  position: relative;
}
.file-row.status-done   { border-color: rgba(80, 200, 120, 0.4); }
.file-row.status-error  { border-color: rgba(224, 85, 85, 0.4); }
.file-row.status-uploading { border-color: var(--accent, #7b6ff0); }

.file-icon { font-size: 18px; flex-shrink: 0; }
.file-info { flex: 1; min-width: 0; }
.file-name {
  font-size: 13px;
  color: var(--text-primary, #e0e0e0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}
.file-meta { font-size: 11px; color: var(--text-muted, #666); }

.doc-type-select {
  background: var(--surface, #111122);
  border: 1px solid var(--border-color, #2a2a3a);
  color: var(--text-primary, #e0e0e0);
  border-radius: 6px;
  font-size: 11px;
  padding: 4px 8px;
  cursor: pointer;
  flex-shrink: 0;
}

.progress-wrap {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: rgba(123,111,240,0.2);
  border-radius: 0 0 8px 8px;
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: var(--accent, #7b6ff0);
  transition: width 0.2s;
}

.badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 20px;
  flex-shrink: 0;
}
.badge.done  { background: rgba(80,200,120,0.15); color: #50c878; }
.badge.error { background: rgba(224,85,85,0.15);  color: #e05555; }

.remove-btn {
  background: none;
  border: none;
  color: var(--text-muted, #666);
  cursor: pointer;
  font-size: 13px;
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
  transition: color 0.15s;
}
.remove-btn:hover { color: #e05555; }

.add-more-btn {
  width: 100%;
  background: transparent;
  border: 1px dashed var(--border-color, #2a2a3a);
  color: var(--text-muted, #888);
  border-radius: 8px;
  padding: 8px;
  font-size: 12px;
  cursor: pointer;
  margin-top: 4px;
  transition: all 0.15s;
}
.add-more-btn:hover {
  border-color: var(--accent, #7b6ff0);
  color: var(--accent, #7b6ff0);
}

/* Global options */
.global-options {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 24px 0;
  flex-wrap: wrap;
}
.global-options label {
  font-size: 12px;
  color: var(--text-muted, #888);
}
.global-select {
  background: var(--input-bg, #0d0d1a);
  border: 1px solid var(--border-color, #2a2a3a);
  color: var(--text-primary, #e0e0e0);
  border-radius: 6px;
  font-size: 12px;
  padding: 4px 10px;
}
.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted, #aaa);
  cursor: pointer;
}
.checkbox-label input { cursor: pointer; accent-color: var(--accent, #7b6ff0); }

/* Summary bar */
.summary-bar {
  display: flex;
  gap: 16px;
  padding: 10px 24px 0;
}
.summary-item {
  font-size: 12px;
  color: var(--text-muted, #888);
}
.done-text  { color: #50c878; }
.error-text { color: #e05555; }

/* Actions */
.modal-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 24px 24px;
}

.btn-secondary {
  background: transparent;
  border: 1px solid var(--border-color, #2a2a3a);
  color: var(--text-muted, #aaa);
  padding: 9px 20px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-secondary:hover:not(:disabled) {
  background: var(--surface-hover, #1a1a2e);
  color: var(--text-primary, #e0e0e0);
}
.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-primary {
  background: var(--accent, #7b6ff0);
  border: none;
  color: #fff;
  padding: 9px 28px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 130px;
  justify-content: center;
}
.btn-primary:hover:not(:disabled) {
  background: #9088f5;
  box-shadow: 0 4px 16px rgba(123,111,240,0.35);
}
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
