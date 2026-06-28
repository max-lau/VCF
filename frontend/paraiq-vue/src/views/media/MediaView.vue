<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'

const tab = ref('audio')
const fileInput = ref(null)
const file = ref(null)
const uploading = ref(false)
const uploadProgress = ref(0)
const error = ref(null)
const lastResult = ref(null)

const transcriptions = ref([])
const loadingList = ref(false)
const selectedId = ref(null)
const deleting = ref(null)

const selectedTranscription = computed(() =>
  transcriptions.value.find(t => (t.id || t.tid) === selectedId.value) || null
)

const ACCEPT = { audio: 'audio/*', video: 'video/*' }
const FORMATS = {
  audio: 'MP3 · WAV · M4A · OGG · FLAC',
  video: 'MP4 · MOV · AVI · MKV · WEBM',
}

function triggerUpload() { fileInput.value?.click() }
function onFileChange(e) { file.value = e.target.files[0] || null }
function onDrop(e) {
  const f = e.dataTransfer.files?.[0]
  if (f) file.value = f
}
function clearFile() {
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
}

async function transcribe() {
  if (!file.value || uploading.value) return
  uploading.value = true; uploadProgress.value = 0
  error.value = null; lastResult.value = null
  const endpoint = tab.value === 'audio' ? '/media/transcribe/audio' : '/media/transcribe/video'
  const fd = new FormData()
  fd.append('file', file.value)
  try {
    const { data } = await client.post(endpoint, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (ev) => {
        if (ev.total) uploadProgress.value = Math.round((ev.loaded / ev.total) * 100)
      },
    })
    lastResult.value = data
    uploadProgress.value = 100
    await fetchTranscriptions()
  } catch (e) {
    error.value = e.response?.data?.detail || 'Transcription failed'
  } finally {
    uploading.value = false
  }
}

async function fetchTranscriptions() {
  loadingList.value = true
  try {
    const { data } = await client.get('/media/transcriptions')
    transcriptions.value = Array.isArray(data) ? data : (data.transcriptions || data.items || [])
  } catch { transcriptions.value = [] }
  finally { loadingList.value = false }
}

async function deleteTranscription(t) {
  const tid = t.id || t.tid
  if (!tid || !confirm(`Delete transcription "${t.filename || t.file_name || tid}"?`)) return
  deleting.value = tid
  try {
    await client.delete(`/media/transcriptions/${tid}`)
    transcriptions.value = transcriptions.value.filter(x => (x.id || x.tid) !== tid)
    if (selectedId.value === tid) selectedId.value = null
  } catch (e) {
    error.value = e.response?.data?.detail || 'Delete failed'
  } finally { deleting.value = null }
}

function viewTranscription(t) {
  selectedId.value = (t.id || t.tid) === selectedId.value ? null : (t.id || t.tid)
}

function mediaUrl(t) {
  if (t.audio_url) return t.audio_url
  if (t.file_url) return t.file_url
  if (t.url) return t.url
  return null
}

function fmtDate(d) {
  return d ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'
}
function fmtDuration(d) {
  if (d == null) return '—'
  if (typeof d === 'string') return d
  const s = Math.round(Number(d))
  if (isNaN(s)) return '—'
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}
function statusClass(s) {
  const v = (s || '').toLowerCase()
  return { completed: 'st--done', done: 'st--done', processing: 'st--proc', pending: 'st--proc', failed: 'st--fail', error: 'st--fail' }[v] || 'st--proc'
}

onMounted(fetchTranscriptions)
</script>

<template>
  <div class="mod">
    <div class="mod__header">
      <div>
        <h1 class="mod__title">Media Transcription</h1>
        <p class="mod__sub">Transcribe audio and video files automatically</p>
      </div>
      <button class="btn-secondary" @click="fetchTranscriptions">↻ Refresh</button>
    </div>

    <div v-if="error" class="err-msg">{{ error }} <button class="err-close" @click="error = null">×</button></div>

    <!-- Tabs -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: tab === 'audio' }" @click="tab = 'audio'">Audio</button>
      <button class="tab-btn" :class="{ active: tab === 'video' }" @click="tab = 'video'">Video</button>
    </div>

    <!-- Upload panel -->
    <div class="panel">
      <div
        class="drop-zone"
        :class="{ 'has-file': file }"
        @dragover.prevent
        @drop.prevent="onDrop"
        @click="triggerUpload"
      >
        <input ref="fileInput" type="file" :accept="ACCEPT[tab]" style="display:none" @change="onFileChange" />
        <div class="drop-zone__icon">↑</div>
        <div class="drop-zone__title">
          {{ file ? file.name : `Drop ${tab} file or click to upload` }}
        </div>
        <div class="drop-zone__sub">{{ FORMATS[tab] }}</div>
      </div>

      <!-- Progress -->
      <div v-if="uploading" class="progress-block">
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: uploadProgress + '%' }"></div>
        </div>
        <span class="progress-label">{{ uploadProgress < 100 ? `Uploading… ${uploadProgress}%` : 'Processing…' }}</span>
      </div>

      <div class="actions-row">
        <button class="btn-ghost" :disabled="uploading || !file" @click="clearFile">Clear</button>
        <button class="btn-gold" :disabled="uploading || !file" @click="transcribe">
          {{ uploading ? 'Working…' : 'Transcribe' }}
        </button>
      </div>

      <!-- Last result inline preview -->
      <div v-if="lastResult" class="result-card">
        <div class="result-card__title">Latest Transcript</div>
        <pre class="result-pre">{{ lastResult.transcript || lastResult.text || JSON.stringify(lastResult, null, 2) }}</pre>
      </div>
    </div>

    <!-- Transcription list -->
    <div class="panel">
      <div class="panel__header">
        <div class="panel__title">Transcriptions</div>
        <div class="panel__count">{{ transcriptions.length }}</div>
      </div>

      <div v-if="loadingList" class="state-msg">Loading…</div>

      <div v-else-if="!transcriptions.length" class="empty">
        <div class="empty__icon">🎙</div>
        <div class="empty__title">No transcriptions yet</div>
        <div class="empty__sub">Upload a file above to get started.</div>
      </div>

      <div v-else class="list">
        <div
          v-for="t in transcriptions"
          :key="t.id || t.tid"
          class="list-item"
          :class="{ 'list-item--open': selectedId === (t.id || t.tid) }"
        >
          <div class="list-item__row" @click="viewTranscription(t)">
            <div class="list-item__main">
              <span class="list-item__name">{{ t.filename || t.file_name || 'Untitled' }}</span>
              <span class="status-pill" :class="statusClass(t.status)">{{ t.status || 'pending' }}</span>
            </div>
            <div class="list-item__meta">
              <span class="dim">⏱ {{ fmtDuration(t.duration) }}</span>
              <span class="dim">{{ fmtDate(t.created_at || t.created) }}</span>
              <button
                class="del-btn"
                :disabled="deleting === (t.id || t.tid)"
                @click.stop="deleteTranscription(t)"
                title="Delete"
              >{{ deleting === (t.id || t.tid) ? '…' : '🗑' }}</button>
            </div>
          </div>

          <div v-if="selectedId === (t.id || t.tid)" class="list-item__detail">
            <!-- Audio player -->
            <audio
              v-if="tab === 'audio' || t.type === 'audio'"
              :src="mediaUrl(t)"
              controls
              class="audio-player"
            />
            <div class="transcript-block">
              <div class="transcript-label">Full Transcript</div>
              <pre class="transcript-pre">{{ t.transcript || t.text || 'No transcript available.' }}</pre>
            </div>
            <div v-if="t.language" class="dim" style="font-size:.78rem;margin-top:.5rem">Language: {{ t.language }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mod { padding: 2rem; max-width: 1000px; }
.mod__header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.25rem; }
.mod__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.mod__sub { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.err-msg { align-items: center; background: rgba(252,129,129,.1); border: 1px solid rgba(252,129,129,.3); border-radius: 6px; color: #fc8181; display: flex; font-size: 0.85rem; gap: 0.75rem; justify-content: space-between; margin-bottom: 1rem; padding: 0.6rem 0.85rem; }
.err-close { background: none; border: none; color: inherit; cursor: pointer; font-size: 1.1rem; line-height: 1; }
.tab-bar { display: flex; gap: 0.5rem; margin-bottom: 1.25rem; border-bottom: 1px solid var(--border); padding-bottom: 0.75rem; }
.tab-btn { background: none; border: 1px solid transparent; border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.875rem; padding: 0.4rem 0.9rem; transition: all 0.15s; }
.tab-btn:hover { color: var(--text-primary); }
.tab-btn.active { border-color: var(--gold); color: var(--gold); }
.panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem; }
.drop-zone { background: var(--bg-raised); border: 2px dashed var(--border); border-radius: 10px; cursor: pointer; padding: 2rem; text-align: center; transition: border-color 0.15s; }
.drop-zone:hover, .drop-zone.has-file { border-color: var(--gold); }
.drop-zone__icon { color: var(--gold); font-size: 1.5rem; margin-bottom: 0.4rem; opacity: 0.6; }
.drop-zone__title { color: var(--text-primary); font-size: 0.9rem; font-weight: 500; margin-bottom: 0.2rem; word-break: break-all; }
.drop-zone__sub { color: var(--text-muted); font-size: 0.75rem; }
.progress-block { align-items: center; display: flex; gap: 0.75rem; margin: 1rem 0 0.5rem; }
.progress-track { background: rgba(255,255,255,.07); border-radius: 3px; flex: 1; height: 6px; overflow: hidden; }
.progress-fill { background: var(--gold); height: 100%; transition: width 0.25s ease; }
.progress-label { color: var(--text-muted); font-size: 0.78rem; white-space: nowrap; }
.actions-row { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 0.75rem; }
.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #000; cursor: pointer; font-size: 0.85rem; font-weight: 600; padding: 0.55rem 1.4rem; transition: opacity 0.2s; }
.btn-gold:hover:not(:disabled) { opacity: 0.85; }
.btn-gold:disabled { cursor: not-allowed; opacity: 0.4; }
.btn-ghost { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.55rem 1rem; transition: all 0.15s; }
.btn-ghost:hover:not(:disabled) { background: var(--bg-raised); color: var(--text-primary); }
.btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }
.result-card { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; margin-top: 1rem; overflow: hidden; }
.result-card__title { color: var(--text-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: 0.05em; padding: 0.55rem 0.85rem; text-transform: uppercase; border-bottom: 1px solid var(--border); }
.result-pre { color: var(--text-primary); font-family: var(--font-mono); font-size: 0.8rem; line-height: 1.6; margin: 0; overflow-x: auto; padding: 0.85rem; white-space: pre-wrap; word-break: break-word; }
.panel__header { align-items: center; display: flex; gap: 0.6rem; margin-bottom: 0.85rem; }
.panel__title { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }
.panel__count { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); font-size: 0.72rem; padding: 0.1rem 0.45rem; }
.state-msg { color: var(--text-muted); padding: 1.5rem; text-align: center; }
.empty { padding: 3rem 2rem; text-align: center; }
.empty__icon { font-size: 2.5rem; opacity: 0.3; margin-bottom: 1rem; }
.empty__title { color: var(--text-primary); font-size: 1.05rem; font-weight: 600; }
.empty__sub { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.4rem; }
.list { display: flex; flex-direction: column; gap: 0.5rem; }
.list-item { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; transition: border-color 0.15s; }
.list-item--open { border-color: var(--gold); }
.list-item__row { align-items: center; cursor: pointer; display: flex; gap: 0.75rem; justify-content: space-between; padding: 0.7rem 0.85rem; }
.list-item__row:hover { background: rgba(255,255,255,.02); }
.list-item__main { align-items: center; display: flex; gap: 0.6rem; min-width: 0; }
.list-item__name { color: var(--text-primary); font-size: 0.88rem; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.list-item__meta { align-items: center; display: flex; gap: 0.85rem; }
.status-pill { border-radius: 4px; font-size: 0.68rem; font-weight: 600; padding: 0.15rem 0.45rem; text-transform: capitalize; }
.st--done { background: rgba(76,175,121,.18); color: #4caf79; }
.st--proc { background: rgba(255,183,77,.18); color: #ffb74d; }
.st--fail { background: rgba(252,129,129,.18); color: #fc8181; }
.del-btn { background: none; border: 1px solid transparent; border-radius: 4px; color: var(--text-muted); cursor: pointer; font-size: 0.9rem; padding: 0.15rem 0.35rem; transition: all 0.15s; }
.del-btn:hover:not(:disabled) { border-color: #fc8181; color: #fc8181; }
.del-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.list-item__detail { border-top: 1px solid var(--border); padding: 0.85rem; }
.audio-player { margin-bottom: 0.75rem; width: 100%; }
.transcript-block { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.transcript-label { color: var(--text-muted); font-size: 0.68rem; font-weight: 600; letter-spacing: 0.05em; padding: 0.4rem 0.7rem; text-transform: uppercase; border-bottom: 1px solid var(--border); }
.transcript-pre { color: var(--text-primary); font-family: var(--font-mono); font-size: 0.8rem; line-height: 1.6; margin: 0; max-height: 320px; overflow-y: auto; padding: 0.75rem 0.85rem; white-space: pre-wrap; word-break: break-word; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; transition: all 0.15s; }
.btn-secondary:hover { background: var(--bg-raised); color: var(--text-primary); }
.dim { color: var(--text-muted); font-size: 0.78rem; }
</style>
