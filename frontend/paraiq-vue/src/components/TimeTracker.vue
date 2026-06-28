<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import client from '@/api/client'

const props = defineProps({
  caseId: { type: Number, default: null },
  activityType: { type: String, default: null },
  description: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})

const emit = defineEmits(['logged'])

const showLog   = ref(false)
const saving    = ref(false)
const summary   = ref(null)
const recent    = ref([])
const loading   = ref(false)

const form = ref({
  case_id: props.caseId,
  activity_type: props.activityType || 'document_review',
  description: props.description || '',
  hours: 0.1,
})

const ACTIVITY_TYPES = [
  { value: 'document_review', label: '📄 Document Review', default_hours: 0.3 },
  { value: 'analysis', label: '🔍 Analysis', default_hours: 0.2 },
  { value: 'drafting', label: '✍️ Drafting', default_hours: 0.5 },
  { value: 'research', label: '📚 Research', default_hours: 0.3 },
  { value: 'email', label: '📧 Email', default_hours: 0.1 },
  { value: 'call', label: '📞 Phone Call', default_hours: 0.2 },
  { value: 'meeting', label: '👥 Meeting', default_hours: 1.0 },
  { value: 'filing', label: '📁 Filing', default_hours: 0.2 },
  { value: 'discovery', label: '🔎 Discovery', default_hours: 0.5 },
  { value: 'other', label: '● Other', default_hours: 0.1 },
]

watch(() => props.caseId, v => form.value.case_id = v)
watch(() => props.activityType, v => { if (v) form.value.activity_type = v })
watch(() => props.description, v => form.value.description = v)

function onActivityChange() {
  const act = ACTIVITY_TYPES.find(a => a.value === form.value.activity_type)
  if (act && !form.value.description) {
    form.value.hours = act.default_hours
  }
}

async function quickLog() {
  saving.value = true
  try {
    const body = { ...form.value }
    if (!body.case_id) delete body.case_id
    const { data } = await client.post('/time-tracker/quick-log', body)
    emit('logged', data)
    showLog.value = false
    form.value.description = props.description || ''
    await fetchSummary()
  } catch (e) {
    // silent fail — don't disrupt the user's workflow
    console.error('[TimeTracker] Quick log failed:', e)
  } finally {
    saving.value = false
  }
}

async function fetchSummary() {
  loading.value = true
  try {
    const params = { days: 30 }
    if (props.caseId) params.case_id = props.caseId
    const { data } = await client.get('/time-tracker/summary', { params })
    summary.value = data
  } catch { summary.value = null }
  finally { loading.value = false }
}

onMounted(fetchSummary)

defineExpose({ fetchSummary })
</script>

<template>
  <div class="tt" :class="{ 'tt--compact': compact }">

    <!-- Quick log button -->
    <button class="tt-btn" @click="showLog = !showLog" :disabled="saving">
      <span v-if="saving" class="tt-spinner"></span>
      <span v-else>⏱</span>
      <span class="tt-btn__label">Log Time</span>
    </button>

    <!-- Summary badge (if data available) -->
    <div v-if="summary && !showLog" class="tt-summary">
      <span class="tt-summary__hours">{{ (summary.total_hours || 0).toFixed(1) }}h</span>
      <span class="tt-summary__label">logged (30d)</span>
    </div>

    <!-- Quick log panel -->
    <div v-if="showLog" class="tt-panel">
      <div class="tt-panel__header">
        <span>Log Billable Time</span>
        <button class="tt-close" @click="showLog = false">✕</button>
      </div>

      <div class="tt-panel__body">
        <div class="tt-field">
          <label>Activity</label>
          <select v-model="form.activity_type" @change="onActivityChange" class="tt-select">
            <option v-for="a in ACTIVITY_TYPES" :key="a.value" :value="a.value">{{ a.label }}</option>
          </select>
        </div>

        <div class="tt-field">
          <label>Description</label>
          <input v-model="form.description" placeholder="Brief description of work done…" class="tt-input" />
        </div>

        <div class="tt-field tt-field--row">
          <div class="tt-field">
            <label>Hours</label>
            <input type="number" v-model.number="form.hours" step="0.1" min="0.1" max="24" class="tt-input tt-input--sm" />
          </div>
          <div v-if="!compact" class="tt-quick-hours">
            <button class="tt-chip" @click="form.hours = 0.1">0.1h</button>
            <button class="tt-chip" @click="form.hours = 0.3">0.3h</button>
            <button class="tt-chip" @click="form.hours = 0.5">0.5h</button>
            <button class="tt-chip" @click="form.hours = 1.0">1h</button>
          </div>
        </div>
      </div>

      <div class="tt-panel__footer">
        <button class="tt-cancel" @click="showLog = false">Cancel</button>
        <button class="tt-save" @click="quickLog" :disabled="saving || !form.hours">
          {{ saving ? 'Saving…' : `Log ${form.hours}h` }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tt { display: inline-flex; align-items: center; gap: .5rem; position: relative; }

.tt-btn { display: inline-flex; align-items: center; gap: .35rem; background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: .75rem; padding: .3rem .6rem; transition: all .15s; }
.tt-btn:hover:not(:disabled) { border-color: var(--gold); color: var(--gold); }
.tt-btn:disabled { opacity: .5; cursor: not-allowed; }
.tt-btn__label { font-weight: 600; }

.tt-spinner { width: 12px; height: 12px; border: 2px solid var(--border); border-top-color: var(--gold); border-radius: 50%; animation: ttspin .6s linear infinite; }
@keyframes ttspin { to { transform: rotate(360deg); } }

.tt-summary { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.2; }
.tt-summary__hours { font-size: .85rem; font-weight: 700; color: var(--gold); }
.tt-summary__label { font-size: .65rem; color: var(--text-muted); }

.tt-panel { position: absolute; top: calc(100% + 6px); right: 0; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,.4); z-index: 50; min-width: 280px; }
.tt-panel__header { display: flex; justify-content: space-between; align-items: center; padding: .6rem .75rem; border-bottom: 1px solid var(--border); font-size: .78rem; font-weight: 600; color: var(--text-primary); }
.tt-close { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: .8rem; }
.tt-panel__body { padding: .6rem .75rem; display: flex; flex-direction: column; gap: .5rem; }
.tt-panel__footer { display: flex; justify-content: flex-end; gap: .5rem; padding: .5rem .75rem; border-top: 1px solid var(--border); }

.tt-field { display: flex; flex-direction: column; gap: .15rem; }
.tt-field--row { flex-direction: row; align-items: flex-end; gap: .5rem; }
.tt-field label { font-size: .65rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .04em; }
.tt-input, .tt-select { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 4px; color: var(--text-primary); font-size: .8rem; padding: .35rem .5rem; outline: none; font-family: inherit; }
.tt-input:focus, .tt-select:focus { border-color: var(--gold); }
.tt-input--sm { width: 70px; }

.tt-quick-hours { display: flex; gap: .2rem; }
.tt-chip { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); cursor: pointer; font-size: .68rem; padding: .2rem .4rem; transition: all .12s; }
.tt-chip:hover { border-color: var(--gold); color: var(--gold); }

.tt-cancel { background: transparent; border: 1px solid var(--border); border-radius: 5px; color: var(--text-muted); cursor: pointer; font-size: .75rem; padding: .3rem .6rem; }
.tt-save { background: var(--gold); border: none; border-radius: 5px; color: #0a0a14; cursor: pointer; font-size: .75rem; font-weight: 700; padding: .3rem .75rem; transition: opacity .15s; }
.tt-save:hover:not(:disabled) { opacity: .85; }
.tt-save:disabled { opacity: .4; cursor: not-allowed; }

.tt--compact .tt-panel { min-width: 240px; }
</style>
