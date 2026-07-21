<template>
  <div class="batch-intake-view">
    <h1>Batch OCR Intake</h1>
    <p class="subtitle">Upload multiple intake forms to queue for OCR extraction.</p>

    <div
      class="drop-zone"
      :class="{ dragging: isDragging }"
      @dragover.prevent="isDragging = true"
      @dragleave.prevent="isDragging = false"
      @drop.prevent="onDrop"
      @click="$refs.fileInput.click()"
    >
      <input ref="fileInput" type="file" multiple accept="image/*,application/pdf" @change="onFilesSelected" hidden />
      <div class="drop-zone__icon">📁</div>
      <div>Drop files here or click to browse</div>
      <div class="dim sm">Images and PDFs accepted</div>
    </div>

    <div v-if="jobs.length" class="jobs">
      <h3>Queue ({{ jobs.length }})</h3>
      <div v-for="job in jobs" :key="job.id" class="job-row">
        <span class="job-name">{{ job.filename }}</span>
        <span class="job-status" :class="job.status">{{ job.status }}</span>
      </div>
    </div>

    <div v-if="message" class="message">{{ message }}</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const isDragging = ref(false)
const jobs = ref([])
const message = ref('')
const fileInput = ref(null)

function addFiles(files) {
  for (const f of files) {
    jobs.value.push({ id: Date.now() + Math.random(), filename: f.name, status: 'queued' })
  }
  message.value = `${files.length} file(s) queued for OCR (async processing not yet wired).`
}

function onDrop(e) {
  isDragging.value = false
  addFiles([...e.dataTransfer.files])
}

function onFilesSelected(e) {
  addFiles([...e.target.files])
}
</script>

<style scoped>
.batch-intake-view { padding: 24px; }
h1 { margin: 0 0 4px; }
.subtitle { color: var(--text-muted); margin: 0 0 24px; }
.drop-zone { border: 2px dashed var(--border); border-radius: 12px; padding: 48px; text-align: center; cursor: pointer; transition: border-color 0.15s, background 0.15s; }
.drop-zone.dragging { border-color: var(--gold); background: rgba(201,168,76,.05); }
.drop-zone__icon { font-size: 2rem; margin-bottom: 12px; }
.jobs { margin-top: 24px; }
.job-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; border-bottom: 1px solid var(--border); }
.job-status { font-size: 0.75rem; text-transform: uppercase; padding: 2px 8px; border-radius: 100px; background: var(--bg-raised); }
.message { margin-top: 16px; color: var(--gold); }
</style>
