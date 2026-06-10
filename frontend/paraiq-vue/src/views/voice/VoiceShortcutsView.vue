<template>
  <div class="vs-page">
    <div class="vs-header">
      <div>
        <h1 class="vs-title">🎙️ Voice Shortcuts</h1>
        <p class="vs-sub dim">Define custom phrases that trigger specific commands when you speak them.</p>
      </div>
      <button class="btn-gold" @click="openCreate">+ New Shortcut</button>
    </div>

    <!-- List -->
    <div v-if="loading" class="state-msg">Loading shortcuts…</div>
    <div v-else-if="!shortcuts.length" class="empty-state">
      <div class="empty-icon">🎙️</div>
      <div class="empty-title">No shortcuts yet</div>
      <div class="empty-sub dim">Create a shortcut to trigger any command with a custom phrase.</div>
      <button class="btn-gold" @click="openCreate">Create your first shortcut</button>
    </div>
    <div v-else class="table-wrap">
      <table class="piq-table">
        <thead>
          <tr>
            <th>Phrase</th>
            <th>Action</th>
            <th>Description</th>
            <th>Params</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in shortcuts" :key="s.id">
            <td><span class="phrase-pill">"{{ s.phrase }}"</span></td>
            <td><code class="action-code">{{ s.action }}</code></td>
            <td class="dim">{{ s.description || '—' }}</td>
            <td class="dim sm">{{ Object.keys(s.params || {}).length ? JSON.stringify(s.params) : '—' }}</td>
            <td class="actions-cell">
              <button class="icon-btn" @click="openEdit(s)" title="Edit">✎</button>
              <button class="icon-btn danger" @click="confirmDelete(s)" title="Delete">✕</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal -->
    <Teleport to="body">
      <div v-if="modal" class="mod-overlay" @click.self="modal=false">
        <div class="mod-modal">
          <div class="mod-modal__header">
            <span>{{ editingId ? 'Edit Shortcut' : 'New Shortcut' }}</span>
            <button class="mod-modal__close" @click="modal=false">✕</button>
          </div>
          <div class="mod-modal__body">
            <div class="field">
              <label class="field__label">Phrase *</label>
              <input v-model="form.phrase" class="piq-input w100"
                placeholder='e.g. "show my urgent cases"' />
              <div class="field__hint dim sm">Speak this phrase to trigger the action.</div>
            </div>
            <div class="field">
              <label class="field__label">Action *</label>
              <select v-model="form.action" class="piq-input w100">
                <option value="">— select action —</option>
                <option v-for="a in actions" :key="a" :value="a">{{ a }}</option>
              </select>
            </div>
            <div class="field">
              <label class="field__label">Description</label>
              <input v-model="form.description" class="piq-input w100"
                placeholder="Optional note about this shortcut" />
            </div>
            <div class="field">
              <label class="field__label">Params (JSON)</label>
              <textarea v-model="paramsRaw" class="piq-input w100" rows="2"
                placeholder='e.g. {"status": "active"}' />
              <div v-if="paramsError" class="field__hint" style="color:var(--danger,#fc8181)">{{ paramsError }}</div>
            </div>
            <div v-if="saveError" class="save-error">{{ saveError }}</div>
          </div>
          <div class="mod-modal__footer">
            <button class="btn-secondary" @click="modal=false">Cancel</button>
            <button class="btn-gold" :disabled="saving" @click="save">
              {{ saving ? 'Saving…' : (editingId ? 'Update' : 'Create') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Delete confirm -->
    <Teleport to="body">
      <div v-if="deleteTarget" class="mod-overlay" @click.self="deleteTarget=null">
        <div class="mod-modal mod-modal--sm">
          <div class="mod-modal__header">
            <span>Delete Shortcut</span>
            <button class="mod-modal__close" @click="deleteTarget=null">✕</button>
          </div>
          <div class="mod-modal__body">
            <p>Delete the shortcut <strong>"{{ deleteTarget.phrase }}"</strong>? This cannot be undone.</p>
          </div>
          <div class="mod-modal__footer">
            <button class="btn-secondary" @click="deleteTarget=null">Cancel</button>
            <button class="btn-danger" :disabled="deleting" @click="doDelete">
              {{ deleting ? 'Deleting…' : 'Delete' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const shortcuts   = ref([])
const actions     = ref([])
const loading     = ref(false)
const modal       = ref(false)
const saving      = ref(false)
const saveError   = ref('')
const editingId   = ref(null)
const deleteTarget = ref(null)
const deleting    = ref(false)

const form = ref({ phrase: '', action: '', description: '', })
const paramsRaw   = ref('{}')
const paramsError = ref('')

function authHdr() {
  return { Authorization: `Bearer ${localStorage.getItem('paraiq_token')}` }
}

async function load() {
  loading.value = true
  try {
    const [s, a] = await Promise.all([
      axios.get('/voice/shortcuts',         { headers: authHdr() }),
      axios.get('/voice/shortcuts/actions', { headers: authHdr() }),
    ])
    shortcuts.value = s.data.shortcuts || []
    actions.value   = a.data.actions   || []
  } catch { shortcuts.value = [] }
  finally { loading.value = false }
}

function openCreate() {
  editingId.value  = null
  form.value       = { phrase: '', action: '', description: '' }
  paramsRaw.value  = '{}'
  paramsError.value = ''
  saveError.value  = ''
  modal.value      = true
}

function openEdit(s) {
  editingId.value   = s.id
  form.value        = { phrase: s.phrase, action: s.action, description: s.description || '' }
  paramsRaw.value   = JSON.stringify(s.params || {}, null, 2)
  paramsError.value = ''
  saveError.value   = ''
  modal.value       = true
}

async function save() {
  paramsError.value = ''
  saveError.value   = ''
  let params = {}
  try { params = JSON.parse(paramsRaw.value || '{}') }
  catch { paramsError.value = 'Invalid JSON'; return }

  if (!form.value.phrase.trim()) { saveError.value = 'Phrase is required'; return }
  if (!form.value.action)        { saveError.value = 'Action is required';  return }

  saving.value = true
  try {
    const payload = { ...form.value, params }
    if (editingId.value) {
      await axios.put(`/voice/shortcuts/${editingId.value}`, payload, { headers: authHdr() })
    } else {
      await axios.post('/voice/shortcuts', payload, { headers: authHdr() })
    }
    modal.value = false
    await load()
  } catch (e) {
    saveError.value = e.response?.data?.detail || 'Save failed'
  } finally {
    saving.value = false
  }
}

function confirmDelete(s) { deleteTarget.value = s }

async function doDelete() {
  deleting.value = true
  try {
    await axios.delete(`/voice/shortcuts/${deleteTarget.value.id}`, { headers: authHdr() })
    deleteTarget.value = null
    await load()
  } catch { }
  finally { deleting.value = false }
}

onMounted(load)
</script>

<style scoped>
.vs-page  { max-width: 900px; margin: 0 auto; }
.vs-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 2rem; gap: 1rem; }
.vs-title  { font-size: 1.4rem; font-weight: 700; margin: 0 0 .25rem; }
.vs-sub    { margin: 0; font-size: .9rem; }

.empty-state { text-align: center; padding: 4rem 2rem; }
.empty-icon  { font-size: 3rem; margin-bottom: 1rem; }
.empty-title { font-size: 1.1rem; font-weight: 600; margin-bottom: .5rem; }
.empty-sub   { margin-bottom: 1.5rem; }

.phrase-pill  { background: rgba(201,168,76,0.12); color: var(--gold,#c9a84c); border-radius: 4px; padding: 2px 8px; font-size: .85rem; font-weight: 500; white-space: nowrap; }
.action-code  { background: rgba(255,255,255,0.06); color: var(--text-secondary,#a0aec0); border-radius: 4px; padding: 2px 6px; font-size: .8rem; }
.actions-cell { white-space: nowrap; text-align: right; }
.icon-btn     { background: none; border: none; cursor: pointer; color: var(--text-secondary,#a0aec0); font-size: 1rem; padding: 4px 6px; border-radius: 4px; transition: background .15s; }
.icon-btn:hover        { background: rgba(255,255,255,0.08); color: var(--text-primary,#e2e8f0); }
.icon-btn.danger:hover { background: rgba(252,129,129,0.12); color: #fc8181; }

.field        { margin-bottom: 1.1rem; }
.field__label { display: block; font-size: .8rem; font-weight: 600; margin-bottom: .4rem; color: var(--text-secondary,#a0aec0); text-transform: uppercase; letter-spacing: .04em; }
.field__hint  { margin-top: .3rem; font-size: .78rem; }
.w100         { width: 100%; box-sizing: border-box; }
.save-error   { color: #fc8181; font-size: .85rem; margin-top: .5rem; }

.mod-modal__footer { display: flex; justify-content: flex-end; gap: .75rem; padding: 1rem 1.5rem; border-top: 1px solid rgba(255,255,255,0.07); }
.mod-modal--sm .mod-modal__body { padding: 1.25rem 1.5rem; }

.btn-danger { background: #c53030; color: #fff; border: none; border-radius: 6px; padding: .5rem 1.2rem; font-weight: 600; cursor: pointer; transition: opacity .15s; }
.btn-danger:hover { opacity: .85; }
.btn-danger:disabled { opacity: .5; cursor: not-allowed; }
</style>
