<template>
  <div class="shortcuts-page">
    <div class="piq-page-header">
      <h2 class="piq-page-title">🎙 Voice Shortcuts</h2>
      <p class="piq-page-subtitle">Map custom phrases to ParaIQ voice commands. Say your phrase and ParaIQ will execute the linked command.</p>
    </div>

    <!-- Add shortcut form -->
    <div class="shortcut-form">
      <div class="shortcut-form__title">Add New Shortcut</div>
      <div class="shortcut-form__row">
        <div class="field">
          <label class="field__label">Your Phrase</label>
          <input
            v-model="newPhrase"
            class="piq-input"
            placeholder='e.g. "morning briefing"'
            maxlength="100"
            @keydown.enter="addShortcut"
          />
        </div>
        <div class="field field--action">
          <label class="field__label">Maps To</label>
          <select v-model="newAction" class="piq-input">
            <option value="" disabled>Select a command…</option>
            <optgroup v-for="group in actionGroups" :key="group.label" :label="group.label">
              <option v-for="a in group.actions" :key="a" :value="a">{{ a }}</option>
            </optgroup>
          </select>
        </div>
        <div class="field field--desc">
          <label class="field__label">Note (optional)</label>
          <input v-model="newDesc" class="piq-input" placeholder="What does this do?" />
        </div>
        <button class="piq-btn piq-btn--gold" :disabled="!newPhrase || !newAction || saving" @click="addShortcut">
          {{ saving ? 'Adding…' : '+ Add' }}
        </button>
      </div>
      <div v-if="formError" class="shortcut-form__error">{{ formError }}</div>
    </div>

    <!-- Shortcuts list -->
    <div class="shortcut-list">
      <div v-if="loading" class="shortcut-list__empty">Loading…</div>
      <div v-else-if="!shortcuts.length" class="shortcut-list__empty">
        No shortcuts yet. Add one above to get started.
      </div>
      <div v-else>
        <div class="shortcut-list__header">
          <span>Phrase</span>
          <span>Command</span>
          <span>Note</span>
          <span>Added</span>
          <span></span>
        </div>
        <div v-for="s in shortcuts" :key="s.id" class="shortcut-row">
          <!-- View mode -->
          <template v-if="editingId !== s.id">
            <span class="shortcut-phrase">{{ s.phrase }}</span>
            <span class="shortcut-action">{{ s.action }}</span>
            <span class="shortcut-desc">{{ s.description || '—' }}</span>
            <span class="shortcut-date">{{ fmtDate(s.created_at) }}</span>
            <div class="shortcut-actions">
              <button class="shortcut-btn" @click="startEdit(s)">Edit</button>
              <button class="shortcut-btn shortcut-btn--danger" @click="deleteShortcut(s.id)">Delete</button>
            </div>
          </template>
          <!-- Edit mode -->
          <template v-else>
            <input v-model="editPhrase" class="piq-input piq-input--sm" />
            <select v-model="editAction" class="piq-input piq-input--sm">
              <optgroup v-for="group in actionGroups" :key="group.label" :label="group.label">
                <option v-for="a in group.actions" :key="a" :value="a">{{ a }}</option>
              </optgroup>
            </select>
            <input v-model="editDesc" class="piq-input piq-input--sm" placeholder="Note" />
            <span></span>
            <div class="shortcut-actions">
              <button class="shortcut-btn shortcut-btn--save" @click="saveEdit(s.id)">Save</button>
              <button class="shortcut-btn" @click="editingId = null">Cancel</button>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- How it works -->
    <div class="shortcuts-help">
      <div class="shortcuts-help__title">How it works</div>
      <div class="shortcuts-help__body">
        When you speak a command using the mic button or Telegram bot, ParaIQ checks your shortcuts first.
        If your phrase matches, the linked command runs immediately with 98%+ confidence.
        Shortcuts take priority over all other voice commands.
      </div>
      <div class="shortcuts-help__examples">
        <div class="example"><span class="example__phrase">"morning briefing"</span> → <span class="example__action">get_workload_today</span></div>
        <div class="example"><span class="example__phrase">"show my cases"</span> → <span class="example__action">search_cases</span></div>
        <div class="example"><span class="example__phrase">"any urgent emails"</span> → <span class="example__action">get_deadlines</span></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import client from '@/api/client'

const shortcuts = ref([])
const loading   = ref(true)
const saving    = ref(false)
const formError = ref('')

const newPhrase = ref('')
const newAction = ref('')
const newDesc   = ref('')

const editingId  = ref(null)
const editPhrase = ref('')
const editAction = ref('')
const editDesc   = ref('')

const actionGroups = [
  { label: 'Calendar & Deadlines', actions: ['get_deadlines', 'get_upcoming_calendar', 'get_calendar_types'] },
  { label: 'Cases & Matters',      actions: ['get_cases_stats', 'search_cases', 'get_case_intelligence', 'get_workload_today'] },
  { label: 'Matter-Scoped',        actions: ['get_matter_kanban', 'get_matter_timeline', 'get_matter_documents', 'get_matter_notes', 'get_matter_intel', 'add_matter_kanban_card'] },
  { label: 'Contacts',             actions: ['get_contacts'] },
  { label: 'Discovery',            actions: ['get_discovery_stats', 'get_discovery_queue', 'get_discovery_duplicates', 'get_discovery_catalog', 'screen_all_discovery'] },
  { label: 'AI & Analysis',        actions: ['get_risk_signals', 'get_legal_bert_status'] },
  { label: 'Privilege Log',        actions: ['get_privilege_stats', 'get_privilege_log'] },
  { label: 'Reports',              actions: ['get_reports_list', 'get_deposition_stats', 'get_depositions', 'get_motion_stats', 'get_motions', 'get_contract_stats', 'get_contracts'] },
  { label: 'Research',             actions: ['get_research'] },
  { label: 'System',               actions: ['get_dashboard_stats', 'get_audit_logs', 'get_audit_stats', 'get_health', 'get_api_stats', 'get_intake_history'] },
]

async function load() {
  loading.value = true
  try {
    const { data } = await client.get('/voice/shortcuts')
    shortcuts.value = data.items || []
  } catch { shortcuts.value = [] }
  finally { loading.value = false }
}

async function addShortcut() {
  formError.value = ''
  if (!newPhrase.value.trim() || !newAction.value) return
  saving.value = true
  try {
    const { data } = await client.post('/voice/shortcuts', {
      phrase: newPhrase.value.trim(),
      action: newAction.value,
      description: newDesc.value.trim() || null,
    })
    shortcuts.value.unshift(data)
    newPhrase.value = ''
    newAction.value = ''
    newDesc.value   = ''
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Could not add shortcut.'
  } finally { saving.value = false }
}

function startEdit(s) {
  editingId.value  = s.id
  editPhrase.value = s.phrase
  editAction.value = s.action
  editDesc.value   = s.description || ''
}

async function saveEdit(id) {
  try {
    const { data } = await client.put(`/voice/shortcuts/${id}`, {
      phrase: editPhrase.value.trim(),
      action: editAction.value,
      description: editDesc.value.trim() || null,
    })
    const idx = shortcuts.value.findIndex(s => s.id === id)
    if (idx !== -1) shortcuts.value[idx] = data
    editingId.value = null
  } catch (e) {
    alert(e.response?.data?.detail || 'Could not save.')
  }
}

async function deleteShortcut(id) {
  if (!confirm('Delete this shortcut?')) return
  try {
    await client.delete(`/voice/shortcuts/${id}`)
    shortcuts.value = shortcuts.value.filter(s => s.id !== id)
  } catch { alert('Could not delete.') }
}

function fmtDate(ts) {
  if (!ts) return '—'
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

onMounted(load)
</script>

<style scoped>
.shortcuts-page { max-width: 900px; }

.shortcut-form {
  background: var(--bg-raised);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 20px 22px;
  margin-bottom: 24px;
}
.shortcut-form__title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 14px; }
.shortcut-form__row   { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
.shortcut-form__error { color: var(--red); font-size: 12px; margin-top: 8px; }

.field { display: flex; flex-direction: column; gap: 5px; }
.field--action { flex: 1.2; }
.field--desc   { flex: 1.5; }
.field__label  { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-tertiary); }

.piq-input {
  background: var(--bg-overlay);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  padding: 8px 10px;
  outline: none;
  min-width: 160px;
}
.piq-input:focus { border-color: var(--gold); }
.piq-input--sm  { padding: 5px 8px; font-size: 12px; min-width: 0; width: 100%; }

.shortcut-list {
  background: var(--bg-raised);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  margin-bottom: 24px;
  overflow: hidden;
}
.shortcut-list__empty  { padding: 24px; font-size: 13px; color: var(--text-tertiary); text-align: center; }
.shortcut-list__header {
  display: grid;
  grid-template-columns: 2fr 2fr 2fr 1fr 120px;
  gap: 12px;
  padding: 10px 16px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-overlay);
}
.shortcut-row {
  display: grid;
  grid-template-columns: 2fr 2fr 2fr 1fr 120px;
  gap: 12px;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 13px;
}
.shortcut-row:last-child { border-bottom: none; }
.shortcut-phrase { color: var(--gold); font-style: italic; }
.shortcut-action { font-family: var(--font-mono); font-size: 11px; color: #AFA9EC; }
.shortcut-desc   { color: var(--text-tertiary); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.shortcut-date   { color: var(--text-tertiary); font-size: 11px; }
.shortcut-actions { display: flex; gap: 6px; }
.shortcut-btn    { font-size: 11px; padding: 3px 10px; border-radius: 4px; border: 1px solid var(--border-subtle); background: transparent; color: var(--text-secondary); cursor: pointer; }
.shortcut-btn:hover { border-color: var(--gold); color: var(--gold); }
.shortcut-btn--danger:hover { border-color: var(--red); color: var(--red); }
.shortcut-btn--save { border-color: var(--gold); color: var(--gold); }

.shortcuts-help {
  background: var(--bg-raised);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 18px 22px;
}
.shortcuts-help__title { font-size: 12px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.shortcuts-help__body  { font-size: 12px; color: var(--text-tertiary); line-height: 1.6; margin-bottom: 12px; }
.shortcuts-help__examples { display: flex; flex-direction: column; gap: 6px; }
.example        { font-size: 12px; display: flex; align-items: center; gap: 8px; }
.example__phrase { color: var(--gold); font-style: italic; }
.example__action { font-family: var(--font-mono); font-size: 11px; color: #AFA9EC; }

.piq-btn { padding: 8px 18px; border-radius: var(--radius-sm); border: none; cursor: pointer; font-size: 13px; font-weight: 500; align-self: flex-end; }
.piq-btn--gold { background: var(--gold); color: #1a1a2e; }
.piq-btn--gold:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
