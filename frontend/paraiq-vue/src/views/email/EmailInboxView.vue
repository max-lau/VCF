<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'

const accounts     = ref([])
const logItems     = ref([])
const intakeItems  = ref([])
const loading      = ref(false)
const activeTab    = ref('intake')
const selectedItem = ref(null)
const showReply    = ref(false)
const replyContent = ref('')
const loadingDraft = ref(false)
const sendingReply = ref(false)
const replyToast   = ref('')
const replySent    = ref(false)
const logTotal     = ref(0)
const intakeTotal  = ref(0)
const filterFrom   = ref('')
const connectingGmail   = ref(false)
const connectingOutlook = ref(false)
const disconnecting     = ref(null)

const scoreColor = (score) => {
  if (score >= 70) return '#10B981'
  if (score >= 30) return '#F59E0B'
  return '#EF4444'
}
const priorityBadge = (p) => ({
  urgent: { label:'Urgent',  color:'#EF4444', bg:'#2A0A0A' },
  high:   { label:'High',    color:'#F59E0B', bg:'#2D1F06' },
  normal: { label:'Normal',  color:'#3B82F6', bg:'#1D3557' },
  review: { label:'Review',  color:'#8B5CF6', bg:'#1E1040' },
  low:    { label:'Low',     color:'#64748B', bg:'#1E293B' },
}[p] || { label: p, color:'#64748B', bg:'#1E293B' })

const decisionBadge = (d) => ({
  intake:  { label:'Intake',  color:'#10B981', bg:'#052E20' },
  review:  { label:'Review',  color:'#F59E0B', bg:'#2D1F06' },
  discard: { label:'Discard', color:'#EF4444', bg:'#2A0A0A' },
}[d] || { label: d, color:'#64748B', bg:'#1E293B' })

const providerColor = (p) => p === 'gmail' ? '#EA4335' : '#0078D4'
const providerBg    = (p) => p === 'gmail' ? '#2A0A0A' : '#0A1428'

const fmtDate  = (d) => d ? new Date(d).toLocaleString('en-US', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' }) : '—'
const fromName = (addr) => addr?.replace(/<.*>/, '').replace(/"/g, '').trim() || addr

const displayItems = computed(() => {
  if (activeTab.value === 'intake')  return intakeItems.value
  if (activeTab.value === 'review')  return logItems.value.filter(i => i.routing_decision === 'review')
  if (activeTab.value === 'discard') return logItems.value.filter(i => i.routing_decision === 'discard')
  return logItems.value
})

async function fetchAccounts() {
  try { const { data } = await client.get('/email/accounts'); accounts.value = data }
  catch { accounts.value = [] }
}
async function fetchIntake() {
  loading.value = true
  try {
    const params = filterFrom.value ? `?from_address=${filterFrom.value}` : ''
    const { data } = await client.get(`/email/intake${params}`)
    intakeItems.value = data.items || []; intakeTotal.value = data.total || 0
  } catch { intakeItems.value = [] }
  finally { loading.value = false }
}
async function fetchLog() {
  try {
    const { data } = await client.get('/email/log?limit=100')
    logItems.value = data.items || []; logTotal.value = data.total || 0
  } catch { logItems.value = [] }
}
async function connectGmail() {
  connectingGmail.value = true
  try { const { data } = await client.post('/email/accounts/gmail/connect'); if (data.auth_url) window.open(data.auth_url, '_blank') }
  catch {} finally { connectingGmail.value = false }
}
async function connectOutlook() {
  connectingOutlook.value = true
  try { const { data } = await client.post('/email/accounts/outlook/connect'); if (data.auth_url) window.open(data.auth_url, '_blank') }
  catch {} finally { connectingOutlook.value = false }
}
async function disconnectAccount(id) {
  disconnecting.value = id
  try { await client.delete(`/email/accounts/${id}`); await fetchAccounts() }
  catch {} finally { disconnecting.value = null }
}
async function reprocess(logId) {
  try { await client.post(`/email/log/${logId}/reprocess`); await fetchLog() }
  catch {}
}
async function fetchDetail(id) {
  try { const { data } = await client.get(`/email/intake/${id}`); selectedItem.value = data }
  catch {}
}
function selectItem(item) {
  // Intake tab items: use item.id directly
  // Log tab items: use item.intake_id if available
  const idToFetch = item.intake_id || (activeTab.value === 'intake' ? item.id : null)
  if (idToFetch) fetchDetail(idToFetch)
  else selectedItem.value = item
}

async function loadAIDraft() {
  if (!selectedItem.value?.id) return
  loadingDraft.value = true
  replyContent.value = ''
  showReply.value    = true
  replySent.value    = false
  try {
    const { data } = await client.get(`/email/intake/${selectedItem.value.id}/draft-reply`)
    replyContent.value = data.draft
  } catch { replyContent.value = 'Unable to generate draft. Please type your reply.' }
  finally { loadingDraft.value = false }
}

async function sendReply() {
  if (!replyContent.value.trim() || !selectedItem.value?.id) return
  sendingReply.value = true
  try {
    await client.post(`/email/intake/${selectedItem.value.id}/send-reply`, {
      content: replyContent.value
    })
    replySent.value    = true
    showReply.value    = false
    replyToast.value   = 'Reply sent successfully'
    setTimeout(() => { replyToast.value = '' }, 3000)
  } catch (e) {
    replyToast.value = 'Failed to send: ' + (e?.response?.data?.detail || e.message)
    setTimeout(() => { replyToast.value = '' }, 4000)
  } finally { sendingReply.value = false }
}

function cancelReply() {
  showReply.value    = false
  replyContent.value = ''
}

onMounted(async () => {
  await fetchAccounts()
  await Promise.all([fetchIntake(), fetchLog()])
})

const tabs = [
  { id:'intake',  label:'Intake',    count: computed(() => intakeTotal.value) },
  { id:'review',  label:'Review',    count: computed(() => logItems.value.filter(i=>i.routing_decision==='review').length) },
  { id:'discard', label:'Discarded', count: computed(() => logItems.value.filter(i=>i.routing_decision==='discard').length) },
  { id:'log',     label:'All Log',   count: computed(() => logTotal.value) },
]
</script>

<template>
  <div class="email-inbox">

    <!-- Header -->
    <div class="inbox-header">
      <div>
        <h1 class="inbox-title">Email Intake</h1>
        <p class="inbox-sub">AI-filtered email feed — inbox untouched</p>
      </div>
      <div class="inbox-actions">
        <!-- Connected accounts -->
        <div class="account-chips">
          <div v-for="acc in accounts" :key="acc.id" class="account-chip">
            <span class="chip-dot" :style="{ background: acc.is_active ? '#10B981' : '#EF4444' }" />
            <span class="chip-email">{{ acc.email_address }}</span>
            <span class="chip-provider" :style="{ color: providerColor(acc.provider), background: providerBg(acc.provider) }">{{ acc.provider }}</span>
            <button
              class="btn-disconnect"
              :disabled="disconnecting === acc.id"
              @click="disconnectAccount(acc.id)"
              title="Disconnect"
            >✕</button>
          </div>
          <span v-if="!accounts.length" class="no-account">No email connected</span>
        </div>
        <!-- Connect buttons -->
        <div class="connect-btns">
          <button class="btn-connect gmail" @click="connectGmail" :disabled="connectingGmail">
            {{ connectingGmail ? 'Opening…' : '+ Gmail' }}
          </button>
          <button class="btn-connect outlook" @click="connectOutlook" :disabled="connectingOutlook">
            {{ connectingOutlook ? 'Opening…' : '+ Outlook' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Stat cards -->
    <div class="stat-row">
      <div class="stat-card green"><div class="stat-val">{{ intakeTotal }}</div><div class="stat-label">Intake</div></div>
      <div class="stat-card amber"><div class="stat-val">{{ logItems.filter(i=>i.routing_decision==='review').length }}</div><div class="stat-label">Review</div></div>
      <div class="stat-card red"><div class="stat-val">{{ logItems.filter(i=>i.routing_decision==='discard').length }}</div><div class="stat-label">Discarded</div></div>
      <div class="stat-card blue"><div class="stat-val">{{ logTotal }}</div><div class="stat-label">Total Processed</div></div>
    </div>

    <!-- Tabs + filter -->
    <div class="tab-bar">
      <div class="tabs">
        <button v-for="tab in tabs" :key="tab.id" class="tab-btn" :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id; selectedItem = null">
          {{ tab.label }}<span class="tab-count">{{ tab.count.value }}</span>
        </button>
      </div>
      <input v-model="filterFrom" class="filter-input" placeholder="Filter by sender…" @keyup.enter="fetchIntake" />
    </div>

    <!-- Main content -->
    <div class="inbox-body" :class="{ split: selectedItem }">

      <!-- Email list -->
      <div class="email-list">
        <div v-if="loading" class="empty">Loading…</div>
        <div v-else-if="!displayItems.length" class="empty">No emails in this category.</div>
        <div v-for="item in displayItems" :key="item.id"
          class="email-row"
          :class="{ selected: selectedItem?.id === item.id || selectedItem?.id === item.intake_id,
                    intake: item.routing_decision==='intake' || (!item.routing_decision && item.priority),
                    review: item.routing_decision==='review' || item.priority==='review',
                    discard: item.routing_decision==='discard' }"
          @click="selectItem(item)"
        >
          <div class="email-row-top">
            <span class="email-from">{{ fromName(item.from_address) }}</span>
            <div class="row-right">
              <span class="provider-dot" :style="{ background: providerColor(item.provider) }" :title="item.provider" />
              <span class="email-date">{{ fmtDate(item.received_at) }}</span>
            </div>
          </div>
          <div class="email-subject">{{ item.subject }}</div>
          <div class="email-meta">
            <span v-if="item.routing_decision" class="badge"
              :style="{ color: decisionBadge(item.routing_decision).color, background: decisionBadge(item.routing_decision).bg }">
              {{ decisionBadge(item.routing_decision).label }}</span>
            <span v-if="item.priority && !item.routing_decision" class="badge"
              :style="{ color: priorityBadge(item.priority).color, background: priorityBadge(item.priority).bg }">
              {{ priorityBadge(item.priority).label }}</span>
            <div v-if="item.stage4_final_score !== undefined" class="score-bar">
              <div class="score-fill" :style="{ width: item.stage4_final_score+'%', background: scoreColor(item.stage4_final_score) }" />
              <span class="score-val">{{ item.stage4_final_score }}</span>
            </div>
            <span v-if="item.case_id || item.case_id_matched" class="badge case-badge">Case matched</span>
            <span v-if="item.discard_reason" class="discard-reason">{{ item.discard_reason }}</span>
            <button v-if="item.routing_decision === 'discard'" class="btn-reprocess" @click.stop="reprocess(item.id)">↺ Reprocess</button>
          </div>
        </div>
      </div>

      <!-- Detail panel -->
      <div v-if="selectedItem" class="detail-panel">
        <div class="detail-header">
          <div style="flex:1;min-width:0">
            <div class="detail-subject">{{ selectedItem.subject }}</div>
            <div class="detail-from">{{ selectedItem.from_address }}</div>
            <div class="detail-meta-row">
              <span class="detail-date">{{ fmtDate(selectedItem.received_at) }}</span>
              <span class="provider-badge" :style="{ color: providerColor(selectedItem.provider), background: providerBg(selectedItem.provider) }">
                {{ selectedItem.provider }}
              </span>
            </div>
          </div>
          <div style="display:flex;gap:6px;align-items:center;flex-shrink:0">
            <button v-if="!replySent" class="btn-reply" @click="loadAIDraft" :disabled="loadingDraft">
              {{ loadingDraft ? '⟳ Drafting…' : '✉ Reply' }}
            </button>
            <span v-else class="reply-sent-badge">✓ Replied</span>
            <button class="btn-close" @click="selectedItem = null">✕</button>
          </div>
        </div>

        <!-- Score breakdown — shown for both log items and intake items -->
        <div class="score-breakdown">
          <div class="breakdown-title">Filter Score Breakdown</div>
          <div class="score-row">
            <span>Stage 1 — Domain Trust</span>
            <span :style="{ color: (selectedItem.stage1_domain_score||0) >= 0 ? '#10B981' : '#EF4444' }">
              {{ (selectedItem.stage1_domain_score||0) > 0 ? '+' : '' }}{{ selectedItem.stage1_domain_score || 0 }}
            </span>
          </div>
          <div class="score-row">
            <span>Stage 2 — NLP Case Match</span>
            <span :style="{ color: (selectedItem.stage2_nlp_score||0) > 0 ? '#10B981' : '#64748B' }">
              +{{ selectedItem.stage2_nlp_score || 0 }}
            </span>
          </div>
          <div class="score-row">
            <span>Stage 3 — Spam Penalty</span>
            <span :style="{ color: (selectedItem.stage3_spam_penalty||0) < 0 ? '#EF4444' : '#64748B' }">
              {{ selectedItem.stage3_spam_penalty || 0 }}
            </span>
          </div>
          <div class="score-row total">
            <span>Final Score</span>
            <span :style="{ color: scoreColor(selectedItem.stage4_final_score || 50) }">
              {{ selectedItem.stage4_final_score || 50 }}/100
            </span>
          </div>
          <div class="score-row">
            <span>Decision</span>
            <span class="badge" :style="decisionBadge(selectedItem.routing_decision || (selectedItem.priority === 'review' ? 'review' : 'intake'))">
              {{ selectedItem.routing_decision || 'intake' }}
            </span>
          </div>
        </div>

        <!-- Entities -->
        <div v-if="selectedItem.extracted_entities && (selectedItem.extracted_entities.case_refs?.length || selectedItem.extracted_entities.legal_keywords?.length || selectedItem.extracted_entities.dates?.length)" class="detail-section">
          <div class="section-label">Extracted Entities</div>
          <div v-if="selectedItem.extracted_entities.case_refs?.length" class="entity-chips">
            <span v-for="r in selectedItem.extracted_entities.case_refs" :key="r" class="entity-chip case">📁 {{ r }}</span>
          </div>
          <div v-if="selectedItem.extracted_entities.legal_keywords?.length" class="entity-chips">
            <span v-for="k in selectedItem.extracted_entities.legal_keywords" :key="k" class="entity-chip kw">⚖️ {{ k }}</span>
          </div>
          <div v-if="selectedItem.extracted_entities.dates?.length" class="entity-chips">
            <span v-for="d in selectedItem.extracted_entities.dates" :key="d" class="entity-chip date">📅 {{ d }}</span>
          </div>
        </div>
        <div v-else-if="selectedItem.extracted_entities" class="detail-section">
          <div class="section-label">Extracted Entities</div>
          <div class="muted">No legal entities detected in this email.</div>
        </div>

        <!-- Body -->
        <div v-if="selectedItem.body_text" class="detail-section">
          <div class="section-label">Message Body</div>
          <div class="body-text">{{ selectedItem.body_text }}</div>
        </div>
        <div v-else class="detail-section">
          <div class="muted">Raw body visible only for authorised attorney on intake items.</div>
        </div>

        <!-- Attachments -->
        <div v-if="selectedItem.attachment_names?.length" class="detail-section">
          <div class="section-label">Attachments ({{ selectedItem.attachment_names.length }})</div>
          <div class="entity-chips">
            <span v-for="name in selectedItem.attachment_names" :key="name" class="entity-chip case" title="Saved to case documents">
              📎 {{ name }}
            </span>
          </div>
          <router-link
            v-if="selectedItem.case_id"
            :to="`/matters/${selectedItem.case_id}`"
            class="bl-link"
            style="margin-top:8px;display:inline-block;"
          >
            View in case binder →
          </router-link>
        </div>

        <!-- Reply compose panel -->
        <div v-if="showReply" class="reply-panel">
          <div class="reply-panel__header">
            <span class="reply-panel__title">✉ Reply to {{ selectedItem.from_address }}</span>
            <button class="btn-close" @click="cancelReply">✕</button>
          </div>
          <div v-if="loadingDraft" class="reply-panel__loading">
            <span class="reply-spinner">⟳</span> Claude is drafting your reply…
          </div>
          <template v-else>
            <div class="reply-panel__label">AI-suggested reply — edit before sending</div>
            <textarea
              v-model="replyContent"
              class="reply-textarea"
              rows="8"
              placeholder="Your reply…"
            ></textarea>
            <div class="reply-panel__actions">
              <button class="btn-cancel-reply" @click="cancelReply">Cancel</button>
              <button class="btn-send-reply" @click="sendReply"
                :disabled="sendingReply || !replyContent.trim()">
                {{ sendingReply ? 'Sending…' : '↗ Send Reply' }}
              </button>
            </div>
          </template>
        </div>

        <!-- Toast -->
        <Transition name="toast">
          <div v-if="replyToast" class="reply-toast">{{ replyToast }}</div>
        </Transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.email-inbox { padding: 24px; max-width: 1400px; margin: 0 auto; font-family: 'IBM Plex Mono', monospace; }

.inbox-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; flex-wrap:wrap; gap:12px; }
.inbox-title  { font-size:22px; font-weight:700; color:var(--color-text-primary,#E2E8F0); margin:0; }
.inbox-sub    { font-size:11px; color:#64748B; margin:4px 0 0; }
.inbox-actions{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.account-chips{ display:flex; gap:8px; flex-wrap:wrap; }
.account-chip { display:flex; align-items:center; gap:5px; background:#12151D; border:1px solid #1E2530; border-radius:6px; padding:4px 8px; font-size:11px; }
.chip-dot     { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.chip-email   { color:#94A3B8; }
.chip-provider{ font-size:9px; font-weight:700; padding:1px 5px; border-radius:3px; letter-spacing:.05em; }
.btn-disconnect{ background:none; border:none; color:#475569; cursor:pointer; font-size:11px; padding:0 2px; line-height:1; }
.btn-disconnect:hover{ color:#EF4444; }
.no-account   { font-size:11px; color:#64748B; }
.connect-btns { display:flex; gap:6px; }
.btn-connect  { border:none; border-radius:6px; padding:7px 12px; font-size:11px; cursor:pointer; font-family:inherit; font-weight:700; }
.btn-connect.gmail  { background:#EA4335; color:#fff; }
.btn-connect.outlook{ background:#0078D4; color:#fff; }
.btn-connect:hover  { opacity:.85; }
.btn-connect:disabled{ opacity:.5; cursor:not-allowed; }

.stat-row  { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px; }
.stat-card { background:#12151D; border:1px solid #1E2530; border-radius:8px; padding:14px 16px; }
.stat-val  { font-size:24px; font-weight:700; margin-bottom:4px; }
.stat-label{ font-size:11px; color:#64748B; letter-spacing:.05em; }
.stat-card.green .stat-val { color:#10B981; }
.stat-card.amber .stat-val { color:#F59E0B; }
.stat-card.red   .stat-val { color:#EF4444; }
.stat-card.blue  .stat-val { color:#3B82F6; }

.tab-bar  { display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #1E2530; margin-bottom:16px; }
.tabs     { display:flex; }
.tab-btn  { background:none; border:none; border-bottom:2px solid transparent; padding:8px 14px; font-size:12px; color:#64748B; cursor:pointer; font-family:inherit; letter-spacing:.04em; display:flex; align-items:center; gap:6px; }
.tab-btn.active{ color:#3B82F6; border-bottom-color:#3B82F6; }
.tab-count{ background:#1E2530; border-radius:10px; padding:1px 7px; font-size:10px; }
.filter-input{ background:#12151D; border:1px solid #1E2530; border-radius:6px; padding:6px 12px; font-size:12px; color:#E2E8F0; font-family:inherit; width:200px; }
.filter-input:focus{ outline:none; border-color:#3B82F6; }

.inbox-body      { display:grid; grid-template-columns:1fr; gap:16px; }
.inbox-body.split{ grid-template-columns:1fr 440px; }

.email-list { display:flex; flex-direction:column; gap:4px; }
.empty      { padding:24px; text-align:center; color:#64748B; font-size:13px; }
.email-row  { background:#12151D; border:1px solid #1E2530; border-left:3px solid #1E2530; border-radius:8px; padding:12px 14px; cursor:pointer; transition:all .15s; }
.email-row:hover   { border-color:#334155; }
.email-row.selected{ border-color:#3B82F6 !important; background:#0E1420; }
.email-row.intake  { border-left-color:#10B981; }
.email-row.review  { border-left-color:#F59E0B; }
.email-row.discard { border-left-color:#EF4444; }
.email-row-top { display:flex; justify-content:space-between; margin-bottom:4px; align-items:center; }
.email-from    { font-size:12px; font-weight:700; color:#CBD5E1; }
.row-right     { display:flex; align-items:center; gap:6px; }
.provider-dot  { width:6px; height:6px; border-radius:50%; }
.email-date    { font-size:10px; color:#475569; }
.email-subject { font-size:12px; color:#94A3B8; margin-bottom:8px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.email-meta    { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.badge         { font-size:9px; font-weight:700; letter-spacing:.06em; padding:2px 7px; border-radius:4px; text-transform:uppercase; }
.case-badge    { color:#8B5CF6; background:#1E1040; }
.score-bar     { display:flex; align-items:center; gap:6px; flex:1; max-width:120px; }
.score-fill    { height:4px; border-radius:2px; min-width:2px; transition:width .3s; }
.score-val     { font-size:10px; color:#64748B; }
.discard-reason{ font-size:10px; color:#EF4444; }
.btn-reprocess { background:none; border:1px solid #334155; border-radius:4px; padding:2px 8px; font-size:10px; color:#64748B; cursor:pointer; font-family:inherit; }
.btn-reprocess:hover{ color:#E2E8F0; border-color:#94A3B8; }

.detail-panel  { background:#12151D; border:1px solid #1E2530; border-radius:8px; padding:16px; position:sticky; top:20px; max-height:80vh; overflow-y:auto; }
.detail-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:14px; gap:12px; }
.detail-subject{ font-size:14px; font-weight:700; color:#E2E8F0; margin-bottom:4px; word-break:break-word; }
.detail-from   { font-size:11px; color:#64748B; margin-bottom:4px; }
.detail-meta-row{ display:flex; align-items:center; gap:8px; }
.detail-date   { font-size:10px; color:#475569; }
.provider-badge{ font-size:9px; font-weight:700; padding:1px 6px; border-radius:3px; letter-spacing:.05em; }
.btn-close     { background:none; border:1px solid #334155; border-radius:4px; padding:3px 8px; color:#64748B; cursor:pointer; font-size:12px; flex-shrink:0; }

.score-breakdown  { background:#0B0E14; border-radius:6px; padding:12px 14px; margin-bottom:14px; border:1px solid #1E2530; }
.breakdown-title  { font-size:10px; color:#64748B; letter-spacing:.08em; text-transform:uppercase; margin-bottom:8px; }
.score-row        { display:flex; justify-content:space-between; font-size:11px; color:#64748B; padding:3px 0; }
.score-row.total  { border-top:1px solid #1E2530; margin-top:6px; padding-top:8px; color:#E2E8F0; font-weight:700; }

.detail-section { margin-bottom:14px; }
.section-label  { font-size:10px; color:#64748B; letter-spacing:.08em; text-transform:uppercase; margin-bottom:6px; }
.entity-chips   { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:4px; }
.entity-chip    { font-size:10px; padding:3px 8px; border-radius:4px; }
.entity-chip.case{ color:#8B5CF6; background:#1E1040; }
.entity-chip.kw  { color:#3B82F6; background:#1D3557; }
.entity-chip.date{ color:#10B981; background:#052E20; }
.body-text      { font-size:11px; color:#94A3B8; line-height:1.7; white-space:pre-wrap; max-height:300px; overflow-y:auto; background:#0B0E14; border-radius:6px; padding:10px 12px; border:1px solid #1E2530; }
.muted          { font-size:11px; color:#475569; font-style:italic; }

@media(max-width:900px){
  .stat-row { grid-template-columns:repeat(2,1fr); }
  .inbox-body.split { grid-template-columns:1fr; }
}
.btn-reply { background: rgba(99,102,241,0.15); border: 1px solid #6366F1; border-radius: 5px; color: #818CF8; cursor: pointer; font-size: 11px; font-family: inherit; padding: 4px 10px; transition: all .15s; white-space: nowrap; }
.btn-reply:hover:not(:disabled) { background: rgba(99,102,241,0.25); }
.btn-reply:disabled { opacity: 0.5; cursor: not-allowed; }
.reply-sent-badge { background: rgba(16,185,129,0.15); border: 1px solid #10B981; border-radius: 5px; color: #10B981; font-size: 10px; padding: 3px 8px; }

.reply-panel { margin-top: 16px; border: 1px solid #6366F1; border-radius: 8px; overflow: hidden; background: #0D1117; }
.reply-panel__header { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: rgba(99,102,241,0.1); border-bottom: 1px solid #6366F1; }
.reply-panel__title  { font-size: 11px; color: #818CF8; font-weight: 600; }
.reply-panel__label  { font-size: 10px; color: #475569; padding: 8px 14px 4px; }
.reply-panel__loading { display: flex; align-items: center; gap: 8px; padding: 20px 14px; color: #64748B; font-size: 12px; }
.reply-spinner { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
.reply-textarea { width: 100%; box-sizing: border-box; background: #0D1117; border: none; border-top: 1px solid #1E2530; color: #E2E8F0; font-family: inherit; font-size: 12px; line-height: 1.6; outline: none; padding: 12px 14px; resize: vertical; }
.reply-textarea:focus { background: #12151D; }
.reply-panel__actions { display: flex; justify-content: flex-end; gap: 8px; padding: 10px 14px; border-top: 1px solid #1E2530; }
.btn-cancel-reply { background: transparent; border: 1px solid #1E2530; border-radius: 5px; color: #64748B; cursor: pointer; font-family: inherit; font-size: 11px; padding: 5px 12px; }
.btn-cancel-reply:hover { border-color: #475569; color: #94A3B8; }
.btn-send-reply { background: #6366F1; border: none; border-radius: 5px; color: white; cursor: pointer; font-family: inherit; font-size: 11px; font-weight: 600; padding: 5px 14px; transition: opacity .15s; }
.btn-send-reply:hover:not(:disabled) { opacity: 0.85; }
.btn-send-reply:disabled { opacity: 0.45; cursor: not-allowed; }
.reply-toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #1E2530; border: 1px solid #6366F1; color: #E2E8F0; font-size: 11px; padding: 8px 16px; border-radius: 8px; z-index: 2000; }
.toast-enter-active, .toast-leave-active { transition: all 0.2s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(6px); }
.bl-link { color: var(--gold, #d4af37); font-size: .8rem; text-decoration: none; }
.bl-link:hover { text-decoration: underline; }
</style>
