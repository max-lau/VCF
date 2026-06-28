<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'

const firmId  = () => { try { return JSON.parse(localStorage.getItem('paraiq_user')||'{}').firm_id||'default' } catch { return 'default' } }

const events     = ref([])
const matters    = ref([])
const loading    = ref(false)
const showCreate = ref(false)
const saving     = ref(false)
const filterStatus = ref('upcoming')
const daysAhead    = ref(30)
const showSync    = ref(false)
const syncStatus  = ref(null)
const syncLoading = ref(false)
const icalUrl     = ref('')
const icalCopied  = ref(false)
const pushResult  = ref(null)

const form = ref(emptyForm())
function emptyForm() {
  return { title:'', event_type:'deadline', due_date:'', due_time:'', location:'', description:'', attendees:'', status:'upcoming', reminder_days:3, is_court_date:false, matter_id:null }
}

const EVENT_TYPES = ['deadline','hearing','deposition','meeting','filing','trial','conference','other']
const STATUSES    = ['upcoming','completed','cancelled','rescheduled']

async function fetchMatters() {
  try {
    const { data } = await client.get('/cases/search?q=&firm_id=' + firmId())
    matters.value = data.cases || []
  } catch {}
}

async function fetchEvents() {
  loading.value = true
  try {
    const { data } = await client.get(`/calendar/firm/${firmId()}?days_ahead=${daysAhead.value}${filterStatus.value ? '&status='+filterStatus.value : ''}`)
    events.value = data
  } catch { events.value = [] }
  finally { loading.value = false }
}

onMounted(() => { fetchMatters(); fetchEvents(); fetchSyncStatus() })

async function fetchSyncStatus() {
  try {
    const { data } = await client.get('/calendar/sync/status')
    syncStatus.value = data
    if (data.ical?.has_url) await fetchIcalUrl()
  } catch { syncStatus.value = null }
}

async function fetchIcalUrl() {
  try {
    const { data } = await client.get('/calendar/sync/ical-url')
    icalUrl.value = data.url
  } catch { icalUrl.value = '' }
}

function copyIcalUrl() {
  navigator.clipboard.writeText(icalUrl.value)
  icalCopied.value = true
  setTimeout(() => icalCopied.value = false, 2000)
}

async function startGoogleSync() {
  try {
    const { data } = await client.post('/calendar/sync/google/start')
    window.location.href = data.auth_url
  } catch (e) {
    pushResult.value = { error: e.response?.data?.detail || 'Failed to start Google sync' }
  }
}

async function startOutlookSync() {
  try {
    const { data } = await client.post('/calendar/sync/outlook/start')
    window.location.href = data.auth_url
  } catch (e) {
    pushResult.value = { error: e.response?.data?.detail || 'Failed to start Outlook sync' }
  }
}

async function pushToGoogle() {
  syncLoading.value = true
  pushResult.value = null
  try {
    const { data } = await client.post('/calendar/sync/google/push')
    pushResult.value = data
  } catch (e) {
    pushResult.value = { error: e.response?.data?.detail || 'Push failed' }
  } finally { syncLoading.value = false }
}

async function pushToOutlook() {
  syncLoading.value = true
  pushResult.value = null
  try {
    const { data } = await client.post('/calendar/sync/outlook/push')
    pushResult.value = data
  } catch (e) {
    pushResult.value = { error: e.response?.data?.detail || 'Push failed' }
  } finally { syncLoading.value = false }
}

async function disconnectProvider(provider) {
  if (!confirm(`Disconnect ${provider} calendar sync?`)) return
  try {
    await client.post('/calendar/sync/disconnect', { provider })
    await fetchSyncStatus()
    pushResult.value = null
  } catch {}
}

async function saveEvent() {
  if (!form.value.title.trim() || !form.value.due_date) return
  saving.value = true
  try {
    await client.post('/calendar/', { ...form.value, firm_id: firmId() }, { headers: authHdr() })
    showCreate.value = false
    form.value = emptyForm()
    fetchEvents()
  } catch {} finally { saving.value = false }
}

async function markDone(event) {
  await client.put(`/calendar/${event.id}`,  { status: 'completed' })
  fetchEvents()
}

async function deleteEvent(id) {
  if (!confirm('Delete this event?')) return
  await client.delete(`/calendar/${id}`)
  fetchEvents()
}

function typeColor(t) {
  const m = { deadline:'#fc8181', hearing:'#9f7aea', deposition:'#4a7cf7', meeting:'#48bb78', filing:'#ecc94b', trial:'#fc8181', conference:'#48bb78', other:'#718096' }
  return m[t] || '#718096'
}
function typeIcon(t) {
  return { deadline:'⏰', hearing:'⚖', deposition:'📋', meeting:'👥', filing:'📁', trial:'🏛', conference:'📞', other:'◎' }[t] || '◎'
}

function daysUntil(d) {
  const diff = Math.ceil((new Date(d) - new Date()) / 86400000)
  if (diff < 0)  return { label: `${Math.abs(diff)}d ago`, color: '#718096' }
  if (diff === 0) return { label: 'Today', color: '#fc8181' }
  if (diff <= 3)  return { label: `${diff}d`, color: '#fc8181' }
  if (diff <= 7)  return { label: `${diff}d`, color: '#ecc94b' }
  return { label: `${diff}d`, color: '#48bb78' }
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { weekday:'short', month:'short', day:'numeric', year:'numeric' })
}

const grouped = computed(() => {
  const sorted = [...events.value].sort((a,b) => new Date(a.due_date) - new Date(b.due_date))
  const groups = {}
  for (const e of sorted) {
    const month = new Date(e.due_date).toLocaleDateString('en-US', { month:'long', year:'numeric' })
    if (!groups[month]) groups[month] = []
    groups[month].push(e)
  }
  return groups
})

const counts = computed(() => ({
  total: events.value.length,
  overdue: events.value.filter(e => e.status === 'upcoming' && new Date(e.due_date) < new Date()).length,
  courtDates: events.value.filter(e => e.is_court_date).length,
}))
</script>

<template>
  <div class="cal">
    <!-- Header -->
    <div class="cal__header">
      <div>
        <h1 class="cal__title">Calendar</h1>
        <p class="cal__sub">Deadlines · hearings · filings · meetings</p>
      </div>
      <div class="cal__header-actions">
        <button class="btn-secondary" @click="showSync = true">📅 Sync</button>
        <button class="btn-gold" @click="showCreate = true; form = emptyForm()">+ New Event</button>
      </div>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <select class="bar-select" v-model="filterStatus" @change="fetchEvents">
        <option value="">All statuses</option>
        <option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
      </select>
      <select class="bar-select sm" v-model="daysAhead" @change="fetchEvents">
        <option :value="7">Next 7 days</option>
        <option :value="14">Next 14 days</option>
        <option :value="30">Next 30 days</option>
        <option :value="60">Next 60 days</option>
        <option :value="90">Next 90 days</option>
        <option :value="365">Next 365 days</option>
      </select>
      <button class="btn-secondary sm" @click="fetchEvents">↻ Refresh</button>
    </div>

    <!-- Stats -->
    <div class="stats-row" v-if="events.length">
      <div class="stat"><span class="stat__n">{{ counts.total }}</span><span class="stat__l">Events</span></div>
      <div class="stat"><span class="stat__n" style="color:#fc8181">{{ counts.overdue }}</span><span class="stat__l">Overdue</span></div>
      <div class="stat"><span class="stat__n" style="color:#9f7aea">{{ counts.courtDates }}</span><span class="stat__l">Court Dates</span></div>
    </div>

    <div v-if="loading" class="state-msg">Loading…</div>

    <div v-else-if="!events.length" class="empty">
      <div class="empty__icon">📅</div>
      <div class="empty__title">No events in this window</div>
      <div class="empty__sub">Add deadlines, hearings, and meetings to stay on track.</div>
      <button class="btn-gold mt" @click="showCreate = true; form = emptyForm()">+ Add Event</button>
    </div>

    <!-- Grouped list -->
    <div v-else>
      <div v-for="(evts, month) in grouped" :key="month" class="month-group">
        <div class="month-label">{{ month }}</div>
        <div class="event-card" v-for="ev in evts" :key="ev.id" :class="{ 'event-card--done': ev.status === 'completed', 'event-card--court': ev.is_court_date }">
          <div class="event-card__left">
            <span class="type-icon">{{ typeIcon(ev.event_type) }}</span>
          </div>
          <div class="event-card__body">
            <div class="event-card__top">
              <span class="event-title" :class="{ done: ev.status === 'completed' }">{{ ev.title }}</span>
              <span v-if="ev.is_court_date" class="court-badge">⚖ Court</span>
              <span class="type-pill" :style="{ background: typeColor(ev.event_type)+'22', color: typeColor(ev.event_type) }">{{ ev.event_type }}</span>
            </div>
            <div class="event-card__meta">
              <span class="dim">{{ fmtDate(ev.due_date) }}{{ ev.due_time ? ' · ' + ev.due_time : '' }}</span>
              <span v-if="ev.location" class="dim">📍 {{ ev.location }}</span>
              <span v-if="ev.description" class="dim">{{ ev.description }}</span>
            </div>
          </div>
          <div class="event-card__right">
            <template v-if="ev.status === 'upcoming'">
              <div class="countdown" :style="{ color: daysUntil(ev.due_date).color }">{{ daysUntil(ev.due_date).label }}</div>
              <button class="done-btn" @click="markDone(ev)" title="Mark complete">✓</button>
            </template>
            <span v-else class="status-pill done-pill">{{ ev.status }}</span>
            <button class="del-btn" @click="deleteEvent(ev.id)">✕</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create modal -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <div class="modal__header">
          <h2>New Calendar Event</h2>
          <button class="close-btn" @click="showCreate = false">✕</button>
        </div>
        <div class="modal__body">
          <div class="field-row">
            <div class="field f2"><label>Title *</label><input v-model="form.title" placeholder="Event title" /></div>
            <div class="field">
              <label>Type</label>
              <select v-model="form.event_type">
                <option v-for="t in EVENT_TYPES" :key="t" :value="t">{{ t }}</option>
              </select>
            </div>
          </div>
          <div class="field-row">
            <div class="field"><label>Due Date *</label><input type="date" v-model="form.due_date" /></div>
            <div class="field"><label>Time</label><input type="time" v-model="form.due_time" /></div>
            <div class="field"><label>Reminder (days)</label><input type="number" v-model="form.reminder_days" min="0" max="90" /></div>
          </div>
          <div class="field-row">
            <div class="field f2"><label>Matter</label>
              <select v-model="form.matter_id">
                <option :value="null">— Firm-wide —</option>
                <option v-for="m in matters" :key="m.id" :value="m.id">{{ m.case_number }} — {{ m.client_name }}</option>
              </select>
            </div>
            <div class="field"><label>Location</label><input v-model="form.location" placeholder="Courtroom 4B" /></div>
          </div>
          <div class="field"><label>Description</label><textarea v-model="form.description" rows="3" placeholder="Notes or details…"></textarea></div>
          <div class="field"><label>Attendees</label><input v-model="form.attendees" placeholder="Comma-separated names or emails" /></div>
          <label class="check-label"><input type="checkbox" v-model="form.is_court_date" /> Court date</label>
        </div>
        <div class="modal__footer">
          <button class="btn-secondary" @click="showCreate = false">Cancel</button>
          <button class="btn-gold" @click="saveEvent" :disabled="saving || !form.title.trim() || !form.due_date">
            {{ saving ? 'Saving…' : 'Save Event' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Sync modal -->
    <div v-if="showSync" class="modal-overlay" @click.self="showSync = false">
      <div class="modal">
        <div class="modal__header">
          <h2>Calendar Sync</h2>
          <button class="close-btn" @click="showSync = false">✕</button>
        </div>
        <div class="modal__body">

          <!-- iCal Feed -->
          <div class="sync-section">
            <div class="sync-section__title">📋 iCal Feed (Universal)</div>
            <div class="sync-section__sub">Works with Apple Calendar, Google Calendar, Outlook, and any app that supports .ics subscriptions.</div>
            <div v-if="icalUrl" class="ical-url-box">
              <input :value="icalUrl" readonly class="ical-input" @click="$event.target.select()" />
              <button class="btn-gold sm" @click="copyIcalUrl">{{ icalCopied ? '✓ Copied' : 'Copy' }}</button>
            </div>
            <button v-else class="btn-gold sm" @click="fetchIcalUrl">Generate iCal URL</button>
            <div class="sync-section__hint">Add this URL as a calendar subscription in your calendar app.</div>
          </div>

          <!-- Google Calendar -->
          <div class="sync-section">
            <div class="sync-section__title">📅 Google Calendar</div>
            <div class="sync-section__sub">Two-way push of deadlines and court dates to your Google Calendar.</div>
            <div v-if="syncStatus?.google?.connected" class="sync-connected">
              <span class="sync-badge sync-badge--on">● Connected</span>
              <button class="btn-gold sm" @click="pushToGoogle" :disabled="syncLoading">{{ syncLoading ? 'Pushing…' : 'Push Events Now' }}</button>
              <button class="btn-secondary sm" @click="disconnectProvider('google')">Disconnect</button>
            </div>
            <button v-else class="btn-secondary sm" @click="startGoogleSync">Connect Google Calendar</button>
          </div>

          <!-- Outlook Calendar -->
          <div class="sync-section">
            <div class="sync-section__title">📧 Outlook Calendar</div>
            <div class="sync-section__sub">Two-way push of deadlines and court dates to your Outlook Calendar.</div>
            <div v-if="syncStatus?.outlook?.connected" class="sync-connected">
              <span class="sync-badge sync-badge--on">● Connected</span>
              <button class="btn-gold sm" @click="pushToOutlook" :disabled="syncLoading">{{ syncLoading ? 'Pushing…' : 'Push Events Now' }}</button>
              <button class="btn-secondary sm" @click="disconnectProvider('outlook')">Disconnect</button>
            </div>
            <button v-else class="btn-secondary sm" @click="startOutlookSync">Connect Outlook Calendar</button>
          </div>

          <!-- Push result -->
          <div v-if="pushResult" class="push-result" :class="{ 'push-result--error': pushResult.error }">
            <template v-if="pushResult.error">{{ pushResult.error }}</template>
            <template v-else>
              ✓ Pushed {{ pushResult.pushed }} of {{ pushResult.total }} events to {{ pushResult.provider }}
              <span v-if="pushResult.errors > 0" class="push-errors">({{ pushResult.errors }} errors)</span>
            </template>
          </div>

        </div>
        <div class="modal__footer">
          <button class="btn-secondary" @click="showSync = false">Done</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cal { padding: 2rem; max-width: 900px; }
.cal__header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.25rem; }
.cal__title  { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.cal__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }

.filter-bar { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.25rem; flex-wrap: wrap; }
.bar-select { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; padding: 0.4rem 0.75rem; }
.bar-select.sm { max-width: 150px; }

.stats-row { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
.stat { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem 1.25rem; display: flex; flex-direction: column; }
.stat__n { font-size: 1.4rem; font-weight: 700; color: var(--text-primary); }
.stat__l { font-size: 0.72rem; color: var(--text-muted); margin-top: 0.1rem; }

.month-group { margin-bottom: 1.5rem; }
.month-label { color: var(--text-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 0.6rem; padding: 0 0.25rem; }

.event-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; display: flex; align-items: center; gap: 1rem; margin-bottom: 0.5rem; padding: 0.9rem 1rem; transition: border-color .15s; }
.event-card:hover { border-color: var(--gold); }
.event-card--done  { opacity: 0.55; }
.event-card--court { border-left: 3px solid #9f7aea; }
.event-card__left  { font-size: 1.4rem; width: 36px; text-align: center; flex-shrink: 0; }
.event-card__body  { flex: 1; min-width: 0; }
.event-card__top   { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem; }
.event-card__meta  { display: flex; gap: 1rem; font-size: 0.78rem; flex-wrap: wrap; }
.event-card__right { display: flex; align-items: center; gap: 0.5rem; flex-shrink: 0; }
.event-title { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }
.event-title.done { text-decoration: line-through; color: var(--text-muted); }
.court-badge  { background: rgba(159,122,234,.15); border-radius: 4px; color: #9f7aea; font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.4rem; }
.type-pill    { border-radius: 4px; font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.4rem; text-transform: capitalize; }
.countdown    { font-size: 0.8rem; font-weight: 700; min-width: 40px; text-align: right; }
.done-btn     { background: rgba(72,187,120,.15); border: none; border-radius: 4px; color: #48bb78; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.2rem 0.5rem; transition: background .15s; }
.done-btn:hover { background: rgba(72,187,120,.3); }
.del-btn      { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.8rem; padding: 0.2rem 0.4rem; border-radius: 4px; }
.del-btn:hover { color: #fc8181; }
.status-pill.done-pill { background: rgba(113,128,150,.15); border-radius: 4px; color: #718096; font-size: 0.72rem; font-weight: 600; padding: 0.2rem 0.5rem; text-transform: capitalize; }

.check-label { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; color: var(--text-muted); cursor: pointer; }
.check-label input { accent-color: var(--gold); cursor: pointer; }

.empty { text-align: center; padding: 4rem 2rem; }
.empty__icon  { font-size: 2.5rem; opacity: .3; margin-bottom: 1rem; }
.empty__title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; }
.empty__sub   { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.4rem; }
.mt { margin-top: 1.25rem; }

.btn-gold     { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1.1rem; transition: opacity .15s; }
.btn-gold:hover:not(:disabled) { opacity: .85; }
.btn-gold:disabled { opacity: .45; cursor: not-allowed; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; transition: all .15s; }
.btn-secondary:hover { background: var(--bg-raised); color: var(--text-primary); }
.btn-secondary.sm { padding: 0.4rem 0.75rem; font-size: 0.8rem; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.65); backdrop-filter: blur(4px); z-index: 100; display: flex; align-items: center; justify-content: center; padding: 1rem; }
.modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; width: 100%; max-width: 580px; max-height: 90vh; overflow-y: auto; }
.modal__header { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border); }
.modal__header h2 { font-size: 1.1rem; color: var(--text-primary); margin: 0; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1rem; }
.modal__body { padding: 1.25rem 1.5rem; display: flex; flex-direction: column; gap: 0.85rem; }
.modal__footer { display: flex; justify-content: flex-end; gap: 0.75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--border); }

.field { display: flex; flex-direction: column; gap: 0.35rem; }
.field.f2 { flex: 2; }
.field label { font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; }
.field input, .field select, .field textarea {
  background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-primary); font-size: 0.875rem; padding: 0.5rem 0.75rem; outline: none; font-family: inherit;
}
.field input:focus, .field select:focus, .field textarea:focus { border-color: var(--gold); }
.field textarea { resize: vertical; }
.field-row { display: flex; gap: 0.75rem; }

.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
.dim { color: var(--text-muted); }

.cal__header-actions { display: flex; gap: 0.5rem; align-items: center; }

.sync-section { padding: 1rem 0; border-bottom: 1px solid var(--border); }
.sync-section:last-child { border-bottom: none; }
.sync-section__title { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.25rem; }
.sync-section__sub { font-size: 0.78rem; color: var(--text-muted); margin-bottom: 0.6rem; }
.sync-section__hint { font-size: 0.72rem; color: var(--text-muted); margin-top: 0.4rem; font-style: italic; }

.ical-url-box { display: flex; gap: 0.5rem; align-items: center; }
.ical-input { flex: 1; background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); font-size: 0.75rem; font-family: var(--font-mono); padding: 0.4rem 0.5rem; }

.sync-connected { display: flex; align-items: center; gap: 0.75rem; }
.sync-badge { font-size: 0.75rem; font-weight: 600; padding: 0.15rem 0.5rem; border-radius: 4px; }
.sync-badge--on { background: rgba(72,187,120,.15); color: #48bb78; }

.btn-gold.sm { padding: 0.35rem 0.75rem; font-size: 0.75rem; }
.btn-secondary.sm { padding: 0.35rem 0.75rem; font-size: 0.75rem; }

.push-result { background: rgba(72,187,120,.1); border: 1px solid rgba(72,187,120,.3); border-radius: 6px; color: #48bb78; font-size: 0.82rem; padding: 0.6rem 0.75rem; margin-top: 0.5rem; }
.push-result--error { background: rgba(252,129,129,.1); border-color: rgba(252,129,129,.3); color: #fc8181; }
.push-errors { color: var(--text-muted); font-size: 0.75rem; }
</style>
