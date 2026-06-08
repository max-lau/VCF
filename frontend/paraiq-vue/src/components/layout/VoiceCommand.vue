<template>
  <div class="vc" ref="vcRef">
    <button class="vc__btn" :class="{'vc__btn--recording': state==='recording','vc__btn--loading':state==='loading'}"
      :title="btnTitle" :disabled="state==='loading'" @click="handleClick" aria-label="Voice command">
      <svg v-if="state!=='loading'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
        <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
        <line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/>
      </svg>
      <svg v-else class="vc__spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
      </svg>
      <span v-if="state==='recording'" class="vc__pulse"/>
    </button>
    <Transition name="vc-panel">
      <div v-if="panel.visible" class="vc__panel">
        <div class="vc__panel-header">
          <span class="vc__panel-icon">🎙</span>
          <span class="vc__panel-title">Voice Command</span>
          <div class="vc__panel-tabs">
            <button :class="['vc__tab', { active: activeTab === 'command' }]" @click="activeTab = 'command'">Command</button>
            <button :class="['vc__tab', { active: activeTab === 'history' }]" @click="switchHistory">History</button>
          </div>
          <button class="vc__panel-close" @click="closePanel">✕</button>
        </div>

        <!-- Command tab -->
        <template v-if="activeTab === 'command'">
          <div v-if="panel.transcript" class="vc__transcript">
            <span class="vc__transcript-label">You said</span>
            <span class="vc__transcript-text">"{{ panel.transcript }}"</span>
          </div>
          <div v-if="state==='recording'" class="vc__recording-row">
            <span class="vc__rec-dot"/><span class="vc__rec-label">Recording… click mic to stop</span>
            <span class="vc__rec-timer">{{ recordingTimer }}s</span>
          </div>
          <div v-if="panel.result" class="vc__result" v-html="panel.result"/>
          <div v-if="panel.error" class="vc__error">⚠️ {{ panel.error }}</div>
          <div v-if="matterContext" class="vc__matter-ctx">
            <span class="vc__matter-icon">⚖</span>
            <span>Scoped to matter <strong>{{ matterContext.case_id }}</strong></span>
            <span class="vc__matter-hint">Say "show kanban", "show timeline", "add a card"</span>
          </div>
          <div v-else-if="!panel.transcript && !panel.result && !panel.error && state === 'idle'" class="vc__hint">
            Click the mic and say a command.<br>
            <span class="vc__hint-examples">Try: "show upcoming deadlines" or "dashboard stats"</span>
          </div>
        </template>

        <!-- History tab -->
        <template v-else>
          <div class="vc__history">
            <div v-if="historyLoading" class="vc__history-empty">
              <span class="vc__spinner-sm">⟳</span> Loading…
            </div>
            <div v-else-if="!historyItems.length" class="vc__history-empty">
              No voice commands yet.
            </div>
            <div v-else>
              <div v-for="h in historyItems" :key="h.id"
                class="vc__history-item"
                :class="{ 'vc__history-item--fail': !h.success }">
                <div class="vc__history-top">
                  <span class="vc__history-action">{{ h.action || 'unknown' }}</span>
                  <span class="vc__history-time">{{ fmtHistoryTime(h.created_at) }}</span>
                  <span v-if="!h.success" class="vc__history-fail">✗</span>
                  <span v-else class="vc__history-ok">✓</span>
                </div>
                <div class="vc__history-transcript">"{{ h.transcript }}"</div>
                <div v-if="h.duration_ms" class="vc__history-meta">
                  {{ h.duration_ms }}ms · confidence {{ Math.round((h.confidence||0)*100) }}%
                </div>
                <div v-if="!h.success && h.error_message" class="vc__history-error">
                  {{ h.error_message }}
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from "vue"
import { useRoute } from "vue-router"
import client from "@/api/client"

const route = useRoute()
const state = ref("idle")

// Detect if we are inside a matter page
const matterContext = computed(() => {
  const id = route.params?.id
  if (!id || !route.path.startsWith("/matters/")) return null
  return { case_id: String(id), case_name: route.query?.name || "" }
})
const vcRef = ref(null)
const panel = reactive({ visible: false, transcript: "", result: "", error: "" })
const activeTab = ref("command")
const historyItems = ref([])
const historyLoading = ref(false)

async function switchHistory() {
  activeTab.value = "history"
  historyLoading.value = true
  try {
    const { data } = await client.get("/voice/audit?limit=20", { _silent: true })
    historyItems.value = data.items || []
  } catch { historyItems.value = [] }
  finally { historyLoading.value = false }
}

function fmtHistoryTime(ts) {
  if (!ts) return ""
  const d = new Date(ts)
  const now = new Date()
  const diff = now - d
  const mins = Math.floor(diff / 60000)
  if (mins < 1)  return "just now"
  if (mins < 60) return mins + "m ago"
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)  return hrs + "h ago"
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" })
}
let mediaRecorder = null, audioChunks = [], timerInterval = null
const recordingTimer = ref(0)

const btnTitle = computed(() => ({idle:"Click to start voice command",recording:"Click to stop recording",loading:"Processing…"}[state.value]))

async function handleClick() {
  if (state.value === "idle") return startRecording()
  if (state.value === "recording") return stopRecording()
}

async function startRecording() {
  panel.visible = true; panel.transcript = ""; panel.result = ""; panel.error = ""; activeTab.value = "command"
  recordingTimer.value = 0
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    audioChunks = []
    const mimeType = ["audio/webm;codecs=opus","audio/webm","audio/ogg"].find(t => MediaRecorder.isTypeSupported(t)) || ""
    mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {})
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data) }
    mediaRecorder.onstop = handleRecordingStop
    mediaRecorder.start(100)
    state.value = "recording"
    timerInterval = setInterval(() => { recordingTimer.value++; if (recordingTimer.value >= 30) stopRecording() }, 1000)
  } catch {
    panel.error = "Microphone access denied. Allow mic permissions in your browser."
    state.value = "idle"
  }
}

function stopRecording() {
  clearInterval(timerInterval)
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop(); mediaRecorder.stream.getTracks().forEach(t => t.stop())
  }
  state.value = "loading"
}

async function handleRecordingStop() {
  const mimeType = mediaRecorder?.mimeType || "audio/webm"
  const ext = mimeType.includes("ogg") ? "ogg" : "webm"
  const blob = new Blob(audioChunks, { type: mimeType })
  const formData = new FormData()
  formData.append("audio", blob, `voice.${ext}`)
  if (matterContext.value) {
    formData.append("case_id", matterContext.value.case_id)
    formData.append("case_name", matterContext.value.case_name || "")
  }
  try {
    const { data } = await client.post("/voice/run", formData, { timeout: 30000 })
    panel.transcript = data.transcript || ""
    panel.result = formatResult(data)
    panel.error = ""
  } catch (err) {
    panel.error = err.response?.data?.detail || "Something went wrong. Please try again."
    panel.result = ""
  } finally { state.value = "idle" }
}

function esc(str) { return String(str??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;") }

function formatResult(data) {
  if (data.error) return `<div class="vc__res-error">❓ ${esc(data.error)}</div>`
  const r = data.result
  if (!r) return `<div class="vc__res-text">✅ Done.</div>`

  if (r.workload) {
    const w = r.workload
    const dl = w.deadlines?.deadlines || []
    const cal = Array.isArray(w.calendar) ? w.calendar : []
    const st = w.stats || {}
    let html = `<div class="vc__res-label">☀️ Your Workload Today</div>`
    html += `<div class="vc__res-label" style="margin-top:8px">📅 Deadlines (${dl.length})</div>`
    if (dl.length) dl.slice(0,3).forEach(d => {
      const dot = d.days_away<=3?"🔴":d.days_away<=7?"🟡":"🟢"
      html += `<div class="vc__res-item">${dot} <strong>${esc(d.event)}</strong><br><small>${esc(d.case_title||d.case_number)} · ${d.days_away}d away</small></div>`
    })
    else html += `<div class="vc__res-item" style="color:var(--text-secondary)">No upcoming deadlines</div>`
    html += `<div class="vc__res-label" style="margin-top:8px">📆 Calendar</div>`
    html += `<div class="vc__res-item" style="color:var(--text-secondary)">${cal.length?cal.length+" events":"No upcoming events"}</div>`
    if (st.open_cases!==undefined) html += `<div class="vc__res-grid" style="margin-top:8px">
      <div class="vc__res-stat"><span>${st.open_cases}</span>Open Cases</div>
      <div class="vc__res-stat"><span>${st.high_risk_cases>0?"🔴":"🟢"} ${st.high_risk_cases}</span>High Risk</div>
      <div class="vc__res-stat"><span>${st.total_analyses}</span>Analyses</div>
      <div class="vc__res-stat"><span>${st.requests_today||0}</span>Today</div>
    </div>`
    return html
  }

  if (r.intelligence) {
    const i = r.intelligence
    let html = `<div class="vc__res-label">🧠 Case Intelligence</div>`
    html += `<div class="vc__res-item"><strong>${esc(i._case_title||"Case")}</strong> · <small>${esc(i._case_number||"")}</small></div>`
    const sigs = i.signals||[]
    sigs.slice(0,3).forEach(s => {
      html += `<div class="vc__res-item">⚠️ <strong>${esc(s.title||s.severity||"")}</strong><br><small>${esc(s.description||"")}</small></div>`
    })
    if (i.summary) html += `<div class="vc__res-item">📋 ${esc(String(i.summary).slice(0,300))}</div>`
    return html
  }

  if (r.deadlines) {
    let html = `<div class="vc__res-label">📅 Deadlines (${r.count??r.deadlines.length})</div>`
    r.deadlines.slice(0,5).forEach(d => {
      const dot = d.days_away<=3?"🔴":d.days_away<=7?"🟡":"🟢"
      html += `<div class="vc__res-item">${dot} <strong>${esc(d.event)}</strong><br><small>${esc(d.case_title||d.case_number)} · Due ${esc(d.date)} (${d.days_away}d)</small></div>`
    })
    return html
  }

  if (r.total_cases!==undefined) return `<div class="vc__res-grid">
    <div class="vc__res-stat"><span>${r.total_cases}</span>Total Cases</div>
    <div class="vc__res-stat"><span>${r.open_cases}</span>Open</div>
    <div class="vc__res-stat"><span>${r.high_risk_cases>0?"🔴":"🟢"} ${r.high_risk_cases}</span>High Risk</div>
    <div class="vc__res-stat"><span>${r.total_analyses}</span>Analyses</div>
  </div>`

  if (r.cases) {
    let html = `<div class="vc__res-label">📁 Cases (${r.cases.length})</div>`
    r.cases.slice(0,5).forEach(c => {
      html += `<div class="vc__res-item">📁 <strong>${esc(c.case_title||c.case_number)}</strong><br><small>${esc(c.client_name||"")} · ${esc(c.status||"")}</small></div>`
    })
    return html
  }

  if (r.contacts) {
    let html = `<div class="vc__res-label">👥 Contacts (${r.contacts.length})</div>`
    r.contacts.slice(0,6).forEach(c => {
      html += `<div class="vc__res-item"><strong>${esc(c.name||c.full_name||"?")}</strong> — ${esc(c.role||"")}<br><small>${esc(c.email||"")}</small></div>`
    })
    return html
  }

  if (r.motions) {
    let html = `<div class="vc__res-label">⚖️ Motions (${r.motions.length})</div>`
    r.motions.slice(0,5).forEach(m => {
      html += `<div class="vc__res-item"><strong>${esc(m.title||m.motion_type||"?")}</strong> — ${esc(m.status||"")}</div>`
    })
    return html
  }

  if (r.depositions) {
    let html = `<div class="vc__res-label">📋 Depositions (${r.depositions.length})</div>`
    r.depositions.slice(0,5).forEach(d => {
      html += `<div class="vc__res-item"><strong>${esc(d.witness_name||d.title||"?")}</strong> — ${esc(d.date||"?")} · ${esc(d.status||"")}</div>`
    })
    return html
  }

  if (r.status) return `<div class="vc__res-text">${r.status==="ok"?"🟢":"🔴"} System <strong>${r.status.toUpperCase()}</strong><br><small>Model: ${esc(r.model||"—")}</small></div>`

  if (r.total!==undefined||r.count!==undefined) return `<div class="vc__res-grid">
    <div class="vc__res-stat"><span>${r.total??r.count}</span>Total</div>
    <div class="vc__res-stat"><span>${r.pending??r.scheduled??"—"}</span>Pending</div>
    <div class="vc__res-stat"><span>${r.completed??r.granted??"—"}</span>Done</div>
    <div class="vc__res-stat"><span>${r.failed??r.denied??"—"}</span>Other</div>
  </div>`

  // Matter-scoped: Kanban board
  if (r.columns && r.cards) {
    const cols = r.columns || []
    const cards = r.cards || {}
    const totalCards = cols.reduce((sum, col) => sum + (cards[col]?.length || 0), 0)
    let html = `<div class="vc__res-label">⚖ Kanban Board (${totalCards} cards)</div>`
    cols.forEach(col => {
      const colCards = cards[col] || []
      if (!colCards.length) return
      html += `<div class="vc__res-label" style="margin-top:6px;font-size:10px">${col.replace("_"," ").toUpperCase()} (${colCards.length})</div>`
      colCards.slice(0, 2).forEach(c => {
        const badge = c.moved_by_hermes ? "🤖 " : ""
        html += `<div class="vc__res-item">${badge}<strong>${esc((c.title||"").slice(0,50))}</strong><br><small>${esc(c.card_type||"")} · ${c.due_date ? "Due "+esc(c.due_date) : "No due date"}</small></div>`
      })
      if (colCards.length > 2) html += `<div class="vc__res-item" style="color:var(--text-tertiary);font-size:10px">+${colCards.length-2} more</div>`
    })
    return html
  }
  // Matter-scoped: Timeline
  if (r.timeline) {
    const tl = r.timeline || []
    let html = `<div class="vc__res-label">📅 Timeline (${tl.length} events)</div>`
    tl.slice(0, 4).forEach(ev => {
      const dot = ev.significance==="high"?"🔴":ev.significance==="medium"?"🟡":"🟢"
      html += `<div class="vc__res-item">${dot} <strong>${esc((ev.event||"").slice(0,60))}</strong><br><small>${esc(ev.date||"")} · ${esc(ev.source_doc||"")}</small></div>`
    })
    return html
  }
  // Matter-scoped: Documents
  if (r.documents || r.docs) {
    const docs = r.documents || r.docs || []
    let html = `<div class="vc__res-label">📄 Documents (${docs.length})</div>`
    docs.slice(0, 5).forEach(d => {
      html += `<div class="vc__res-item"><strong>${esc((d.document_name||d.filename||"?").slice(0,50))}</strong><br><small>${esc(d.doc_type||d.status||"")}</small></div>`
    })
    return html
  }
  // Matter-scoped: Notes
  if (r.notes) {
    const notes = r.notes || []
    let html = `<div class="vc__res-label">📝 Notes (${notes.length})</div>`
    notes.slice(0, 3).forEach(n => {
      html += `<div class="vc__res-item">${esc((n.content||n.note||"").slice(0,100))}<br><small>${esc(n.author||"")} · ${esc(n.created_at||"").slice(0,10)}</small></div>`
    })
    return html
  }
  return `<pre class="vc__res-json">${esc(JSON.stringify(r,null,2)).slice(0,600)}</pre>`
}

function closePanel() { if (state.value==="recording") stopRecording(); panel.visible=false }
function onClickOutside(e) { if (vcRef.value&&!vcRef.value.contains(e.target)&&state.value==="idle") panel.visible=false }
onMounted(() => document.addEventListener("mousedown", onClickOutside))
onBeforeUnmount(() => document.removeEventListener("mousedown", onClickOutside))
</script>

<style scoped>
.vc { position:relative; display:flex; align-items:center; }
.vc__btn { display:flex; align-items:center; justify-content:center; width:34px; height:34px; border-radius:8px; border:1px solid var(--border-dim); background:var(--bg-raised,#1a2235); color:var(--text-secondary); cursor:pointer; position:relative; transition:all 0.18s ease; }
.vc__btn:hover { background:var(--bg-hover); color:var(--text-primary); border-color:var(--accent,#00d4ff); }
.vc__btn:disabled { opacity:0.5; cursor:not-allowed; }
.vc__btn--recording { background:rgba(239,68,68,0.12); border-color:rgba(239,68,68,0.5); color:#f87171; }
.vc__btn--loading { background:rgba(0,212,255,0.08); border-color:rgba(0,212,255,0.3); color:var(--accent,#00d4ff); }
.vc__pulse { position:absolute; inset:-4px; border-radius:12px; border:2px solid rgba(239,68,68,0.5); animation:vc-pulse 1.2s ease-out infinite; pointer-events:none; }
@keyframes vc-pulse { 0%{opacity:1;transform:scale(1)} 100%{opacity:0;transform:scale(1.6)} }
.vc__spinner { animation:vc-spin 0.9s linear infinite; }
@keyframes vc-spin { to{transform:rotate(360deg)} }
.vc__panel { position:absolute; top:calc(100% + 10px); right:0; width:340px; background:var(--bg-raised,#111827); border:1px solid var(--border-dim); border-radius:10px; box-shadow:0 8px 32px rgba(0,0,0,0.4); z-index:999; overflow:hidden; }
.vc__panel-header { display:flex; align-items:center; gap:8px; padding:12px 14px; border-bottom:1px solid var(--border-dim); background:var(--bg-base); }
.vc__panel-icon { font-size:14px; }
.vc__panel-title { font-size:12px; font-weight:600; color:var(--text-primary); flex:1; letter-spacing:0.04em; text-transform:uppercase; }
.vc__panel-close { background:none; border:none; cursor:pointer; color:var(--text-tertiary); font-size:14px; padding:2px 4px; border-radius:4px; }
.vc__panel-close:hover { color:var(--text-primary); background:var(--bg-hover); }
.vc__transcript { display:flex; flex-direction:column; gap:2px; padding:10px 14px; border-bottom:1px solid var(--border-dim); background:rgba(0,212,255,0.03); }
.vc__transcript-label { font-size:9px; letter-spacing:0.12em; text-transform:uppercase; color:var(--accent,#00d4ff); }
.vc__transcript-text { font-size:13px; color:var(--text-primary); font-style:italic; }
.vc__recording-row { display:flex; align-items:center; gap:8px; padding:12px 14px; font-size:12px; color:var(--text-secondary); }
.vc__rec-dot { width:8px; height:8px; border-radius:50%; background:#ef4444; animation:vc-blink 1s ease-in-out infinite; flex-shrink:0; }
@keyframes vc-blink { 0%,100%{opacity:1} 50%{opacity:0.2} }
.vc__rec-label { flex:1; }
.vc__rec-timer { font-family:monospace; color:#f87171; }
.vc__result { padding:12px 14px; font-size:13px; color:var(--text-primary); }
.vc__error { padding:12px 14px; font-size:13px; color:#f87171; }
:deep(.vc__res-text) { color:var(--text-primary); line-height:1.6; }
:deep(.vc__res-error) { color:#f87171; }
:deep(.vc__res-label) { font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.08em; color:var(--text-secondary); margin-bottom:8px; }
:deep(.vc__res-item) { padding:6px 0; border-bottom:1px solid var(--border-dim); line-height:1.5; }
:deep(.vc__res-item:last-child) { border-bottom:none; }
:deep(.vc__res-item small) { color:var(--text-secondary); font-size:11px; }
:deep(.vc__res-grid) { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
:deep(.vc__res-stat) { background:var(--bg-base); border:1px solid var(--border-dim); border-radius:6px; padding:8px 10px; font-size:11px; color:var(--text-secondary); line-height:1.4; }
:deep(.vc__res-stat span) { display:block; font-size:18px; font-weight:700; color:var(--text-primary); margin-bottom:2px; }
:deep(.vc__res-json) { font-size:10px; color:var(--text-secondary); overflow-x:auto; white-space:pre-wrap; word-break:break-all; }
.vc-panel-enter-active,.vc-panel-leave-active { transition:opacity 0.18s ease,transform 0.18s ease; }
.vc-panel-enter-from,.vc-panel-leave-to { opacity:0; transform:translateY(-6px); }
.vc__matter-ctx {
  margin: 10px 14px;
  padding: 8px 10px;
  background: rgba(201,168,76,0.08);
  border: 1px solid rgba(201,168,76,0.25);
  border-radius: 6px;
  font-size: 11px;
  color: var(--gold, #c89b3c);
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.vc__matter-icon { font-size: 14px; }
.vc__matter-hint { font-size: 10px; opacity: 0.7; color: var(--text-tertiary, #64748b); }
.vc__panel-tabs { display: flex; gap: 4px; margin-left: auto; margin-right: 8px; }
.vc__tab { background: none; border: 1px solid transparent; border-radius: 4px; color: var(--text-tertiary, #64748b); cursor: pointer; font-size: 11px; padding: 2px 8px; transition: all .12s; }
.vc__tab:hover { color: var(--text-primary, #e2e8f0); }
.vc__tab.active { border-color: var(--gold, #c89b3c); color: var(--gold, #c89b3c); }

.vc__hint { padding: 16px; text-align: center; color: var(--text-tertiary, #64748b); font-size: 12px; line-height: 1.6; }
.vc__hint-examples { font-size: 11px; opacity: 0.7; }

.vc__history { max-height: 320px; overflow-y: auto; }
.vc__history-empty { padding: 24px; text-align: center; color: var(--text-tertiary, #64748b); font-size: 12px; display: flex; align-items: center; justify-content: center; gap: 6px; }
.vc__spinner-sm { display: inline-block; animation: spin 1s linear infinite; }

.vc__history-item { padding: 10px 14px; border-bottom: 1px solid var(--border-dim, #1e2530); transition: background .12s; }
.vc__history-item:hover { background: rgba(255,255,255,0.03); }
.vc__history-item--fail { opacity: 0.7; }
.vc__history-top { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
.vc__history-action { font-size: 11px; font-weight: 600; color: var(--gold, #c89b3c); flex: 1; }
.vc__history-time { font-size: 10px; color: var(--text-tertiary, #64748b); }
.vc__history-ok   { color: #2f9e44; font-size: 11px; }
.vc__history-fail { color: #e03131; font-size: 11px; }
.vc__history-transcript { font-size: 11px; color: var(--text-secondary, #94a3b8); font-style: italic; margin-bottom: 2px; }
.vc__history-meta  { font-size: 10px; color: var(--text-tertiary, #64748b); }
.vc__history-error { font-size: 10px; color: #fc8181; margin-top: 2px; }
</style>
