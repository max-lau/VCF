<script setup>
import { ref, onMounted } from 'vue'
import client from '@/api/client'
const tab = ref('audio'); const fileInput = ref(null); const file = ref(null)
const msgText = ref(''); const msgType = ref('email')
const loading = ref(false); const error = ref(null); const result = ref(null)
const transcriptions = ref([]); const messages = ref([])

function onFile(e) { file.value = e.target.files[0] || null }

async function transcribe() {
  if (!file.value) return
  loading.value = true; error.value = null; result.value = null
  try {
    const fd = new FormData(); fd.append('file', file.value)
    const ep = tab.value === 'audio' ? '/media/transcribe/audio' : '/media/transcribe/video'
    const { data } = await client.post(ep, fd)
    result.value = data; await fetchTranscriptions()
  } catch(e) { error.value = e.response?.data?.detail || 'Transcription failed' }
  finally { loading.value = false }
}

async function parseMessage() {
  if (!msgText.value.trim()) return
  loading.value = true; error.value = null; result.value = null
  try {
    const { data } = await client.post(`/messages/parse/${msgType.value}`, { text: msgText.value })
    result.value = data; await fetchMessages()
  } catch(e) { error.value = e.response?.data?.detail || 'Parse failed' }
  finally { loading.value = false }
}

async function fetchTranscriptions() {
  try { const { data } = await client.get('/media/transcriptions?limit=20'); transcriptions.value = data.transcriptions || data || [] } catch {}
}
async function fetchMessages() {
  try { const { data } = await client.get('/messages/parsed?limit=20'); messages.value = data.messages || data || [] } catch {}
}

function fmtDate(d) { return d ? new Date(d).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : '—' }
onMounted(() => { fetchTranscriptions(); fetchMessages() })
</script>
<template>
  <div class="mod">
    <div class="mod__header"><h1 class="mod__title">Media & Messages</h1><p class="mod__sub">Audio/video transcription and message parsing</p></div>
    <div class="tab-bar">
      <button class="tab-btn" :class="{active:tab==='audio'}" @click="tab='audio'">Audio</button>
      <button class="tab-btn" :class="{active:tab==='video'}" @click="tab='video'">Video</button>
      <button class="tab-btn" :class="{active:tab==='messages'}" @click="tab='messages'">Messages</button>
    </div>
    <div v-if="error" class="err-msg">{{ error }}</div>

    <!-- Audio / Video -->
    <div v-if="tab==='audio'||tab==='video'" class="panel">
      <div class="drop-zone" :class="{'has-file':file}" @dragover.prevent @drop.prevent="e=>file=e.dataTransfer.files[0]" @click="fileInput.click()">
        <input ref="fileInput" type="file" :accept="tab==='audio'?'audio/*':'video/*'" style="display:none" @change="onFile"/>
        <div class="drop-zone__icon">↑</div>
        <div class="drop-zone__title">{{ file?file.name:`Drop ${tab} file or click to upload` }}</div>
        <div class="drop-zone__sub">{{ tab==='audio'?'MP3 · WAV · M4A · OGG':'MP4 · MOV · AVI · MKV' }}</div>
      </div>
      <div class="submit-row"><button class="piq-btn-gold" :disabled="loading||!file" @click="transcribe">{{ loading?'Transcribing…':'Transcribe' }}</button></div>
      <div v-if="result" class="result-card"><div class="result-card__title">Transcript</div><pre class="result-pre">{{ result.transcript || result.text || JSON.stringify(result,null,2) }}</pre></div>
      <div v-if="transcriptions.length" class="history-section">
        <div class="field-label" style="margin-bottom:.6rem">Recent transcriptions</div>
        <div class="piq-table-wrap"><table class="piq-table"><thead><tr><th>File</th><th>Date</th><th>Duration</th></tr></thead>
          <tbody><tr v-for="t in transcriptions" :key="t.id"><td class="bold">{{ t.filename||t.file_name||'—' }}</td><td class="dim">{{ fmtDate(t.created_at) }}</td><td class="dim">{{ t.duration||'—' }}</td></tr></tbody>
        </table></div>
      </div>
    </div>

    <!-- Messages -->
    <div v-if="tab==='messages'" class="panel">
      <div class="type-bar">
        <button v-for="t in ['email','chat','sms']" :key="t" class="type-btn" :class="{active:msgType===t}" @click="msgType=t">{{ t }}</button>
      </div>
      <div class="input-card">
        <label class="field-label">{{ msgType }} content</label>
        <textarea v-model="msgText" class="piq-textarea" rows="8" :placeholder="`Paste ${msgType} content…`"/>
        <div class="input-actions"><button class="piq-btn-gold" :disabled="loading||!msgText.trim()" @click="parseMessage">{{ loading?'Parsing…':'Parse' }}</button></div>
      </div>
      <div v-if="result" class="result-card"><div class="result-card__title">Parsed Result</div><pre class="result-pre">{{ JSON.stringify(result,null,2) }}</pre></div>
      <div v-if="messages.length" class="history-section">
        <div class="field-label" style="margin-bottom:.6rem">Recent parses</div>
        <div class="piq-table-wrap"><table class="piq-table"><thead><tr><th>Type</th><th>Date</th><th>Entities</th></tr></thead>
          <tbody><tr v-for="m in messages" :key="m.id"><td class="bold">{{ m.type||'—' }}</td><td class="dim">{{ fmtDate(m.created_at) }}</td><td class="dim">{{ m.entity_count||'—' }}</td></tr></tbody>
        </table></div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.mod{padding:2rem;max-width:950px}.mod__header{margin-bottom:1.25rem}.mod__title{font-family:var(--font-display);font-size:1.6rem;color:var(--gold);margin:0}.mod__sub{color:var(--text-muted);font-size:.85rem;margin:.25rem 0 0}.tab-bar{display:flex;gap:.5rem;margin-bottom:1.25rem;border-bottom:1px solid var(--border);padding-bottom:.75rem}.tab-btn{background:none;border:1px solid transparent;border-radius:6px;color:var(--text-muted);cursor:pointer;font-size:.875rem;padding:.4rem .9rem;transition:all .15s}.tab-btn:hover{color:var(--text-primary)}.tab-btn.active{border-color:var(--gold);color:var(--gold)}.err-msg{color:#fc8181;font-size:.875rem;margin-bottom:1rem}.drop-zone{background:var(--bg-card);border:2px dashed var(--border);border-radius:10px;cursor:pointer;padding:2rem;text-align:center;transition:border-color .15s;margin-bottom:.75rem}.drop-zone:hover,.drop-zone.has-file{border-color:var(--gold)}.drop-zone__icon{color:var(--gold);font-size:1.5rem;margin-bottom:.4rem;opacity:.6}.drop-zone__title{color:var(--text-primary);font-size:.9rem;font-weight:500;margin-bottom:.2rem}.drop-zone__sub{color:var(--text-muted);font-size:.75rem}.submit-row{display:flex;justify-content:flex-end;margin-bottom:1rem}.piq-btn-gold{background:var(--gold);border:none;border-radius:6px;color:#000;cursor:pointer;font-size:.875rem;font-weight:600;padding:.55rem 1.4rem;transition:opacity .2s}.piq-btn-gold:hover:not(:disabled){opacity:.85}.piq-btn-gold:disabled{cursor:not-allowed;opacity:.4}.type-bar{display:flex;gap:.5rem;margin-bottom:1rem}.type-btn{background:var(--bg-card);border:1px solid var(--border);border-radius:6px;color:var(--text-muted);cursor:pointer;font-size:.8rem;padding:.35rem .75rem;transition:all .15s;text-transform:uppercase}.type-btn.active{border-color:var(--gold);color:var(--gold)}.input-card{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:1.25rem;margin-bottom:1rem}.field-label{font-size:.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;display:block;margin-bottom:.5rem}.piq-textarea{background:var(--bg-raised,#0d0d1a);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-family:inherit;font-size:.875rem;line-height:1.6;padding:.75rem;resize:vertical;width:100%;box-sizing:border-box}.piq-textarea:focus{border-color:var(--gold);outline:none}.input-actions{display:flex;justify-content:flex-end;margin-top:.75rem}.result-card{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:1.25rem;margin-bottom:1rem}.result-card__title{font-size:.72rem;color:var(--text-muted);font-weight:600;letter-spacing:.05em;margin-bottom:.75rem;text-transform:uppercase}.result-pre{background:var(--bg-raised,#0d0d1a);border-radius:6px;color:var(--text-muted);font-family:var(--font-mono);font-size:.75rem;line-height:1.5;margin:0;overflow-x:auto;padding:.75rem;white-space:pre-wrap;word-break:break-word}.history-section{margin-top:1rem}.piq-table-wrap{border:1px solid var(--border);border-radius:8px;overflow-x:auto}.piq-table{border-collapse:collapse;font-size:.875rem;width:100%}.piq-table th{background:var(--bg-card);border-bottom:1px solid var(--border);color:var(--text-muted);font-size:.72rem;font-weight:600;letter-spacing:.05em;padding:.65rem .9rem;text-align:left;text-transform:uppercase}.piq-table td{border-bottom:1px solid var(--border);padding:.7rem .9rem;vertical-align:middle}.piq-table tr:last-child td{border-bottom:none}.bold{color:var(--text-primary);font-weight:500}.dim{color:var(--text-muted)}
</style>
