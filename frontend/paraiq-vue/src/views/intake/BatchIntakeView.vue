<template>
  <div class="batch-intake-view">
    <h1>Batch OCR Intake</h1>
    <p class="subtitle">Upload multiple intake forms to queue for OCR extraction.</p>

    <div
      class="drop-zone"
      :class="{ dragging: isDragging, disabled: uploading }"
      @dragover.prevent="isDragging = true"
      @dragleave.prevent="isDragging = false"
      @drop.prevent="onDrop"
      @click="!uploading && $refs.fileInput.click()"
    >
      <input ref="fileInput" type="file" multiple accept="image/*,application/pdf" @change="onFilesSelected" hidden />
      <div class="drop-zone__icon">📁</div>
      <div v-if="uploading">Uploading…</div>
      <div v-else>Drop files here or click to browse</div>
      <div class="dim sm">Images and PDFs accepted (max 50)</div>
    </div>

    <div v-if="message" class="message" :class="messageType">{{ message }}</div>

    <div v-if="jobs.length" class="jobs">
      <div class="jobs-header">
        <h3>Queue ({{ jobs.length }})</h3>
        <button class="btn-gold sm" @click="refreshJobs" :disabled="refreshing">↻ Refresh</button>
      </div>
      <div v-for="job in jobs" :key="job.id" class="job-row">
        <span class="job-name">{{ job.filename }}</span>
        <span class="job-status" :class="job.status">{{ job.status }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const isDragging = ref(false)
const uploading = ref(false)
const jobs = ref([])
const message = ref('')
const messageType = ref('')
const refreshing = ref(false)
const fileInput = ref(null)

const authHdr = () => ({ Authorization: 'Bearer ' + localStorage.getItem('paraiq_token') })

async function loadJobs() {
  try {
    const { data } = await axios.get('/intake/jobs?limit=50', { headers: authHdr() })
    jobs.value = data.jobs || []
  } catch (e) {
    console.error('Failed to load jobs', e)
  }
}

async function refreshJobs() {
  refreshing.value = true
  await loadJobs()
  refreshing.value = false
}

async function uploadFiles(files) {
  if (!files.length) return
  if (files.length > 50) {
    message.value = 'Maximum 50 files per batch.'
    messageType.value = 'error'
    return
  }
  uploading.value = true
  message.value = ''
  const formData = new FormData()
  for (const f of files) formData.append('files', f)

  try {
    const { data } = await axios.post('/intake/batch', formData, {
      headers: { ...authHdr(), 'Content-Type': 'multipart/form-data' }
    })
    message.value = `${data.count} job(s) queued successfully.`
    messageType.value = 'success'
    await loadJobs()
  } catch (e) {
    message.value = e.response?.data?.detail || e.message
    messageType.value = 'error'
  } finally {
    uploading.value = false
  }
}

function onDrop(e) {
  isDragging.value = false
  uploadFiles([...e.dataTransfer.files])
}

function onFilesSelected(e) {
  uploadFiles([...e.target.files])
}

onMounted(loadJobs)
</script>

<style scoped>
.batch-intake-view { padding: 24px; }
h1 { margin: 0 0 4px; }
.subtitle { color: var(--text-muted); margin: 0 0 24px; }
.drop-zone { border: 2px dashed var(--border); border-radius: 12px; padding: 48px; text-align: center; cursor: pointer; transition: border-color 0.15s, background 0.15s; }
.drop-zone.dragging { border-color: var(--gold); background: rgba(201,168,76,.05); }
.drop-zone.disabled { opacity: 0.6; cursor: not-allowed; }
.drop-zone__icon { font-size: 2rem; margin-bottom: 12px; }
.message { margin-top: 16px; padding: 12px; border-radius: 8px; }
.message.success { background: rgba(72,187,120,.1); color: #48bb78; }
.message.error { background: rgba(224,85,85,.1); color: #e07070; }
.jobs { margin-top: 24px; }
.jobs-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.jobs-header h3 { margin: 0; }
.job-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; border-bottom: 1px solid var(--border); }
.job-status { font-size: 0.75rem; text-transform: uppercase; padding: 2px 8px; border-radius: 100px; background: var(--bg-raised); }
.job-status.pending { background: rgba(236,201,75,.15); color: #ecc94b; }
.job-status.completed { background: rgba(72,187,120,.15); color: #48bb78; }
.job-status.failed { background: rgba(224,85,85,.15); color: #e07070; }
</style>
