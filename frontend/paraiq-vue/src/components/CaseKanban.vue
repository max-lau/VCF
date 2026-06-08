<template>
  <div class="kanban-root">
    <div class="kb-header">
      <div class="kb-actions">
        <button class="btn-hermes" :class="{ pulsing: hermesActive }" @click="triggerHermesDemo">
          🤖 Hermes auto-move
        </button>
        <button class="btn-add" @click="openAddCard(null)">+ Add card</button>
      </div>
    </div>

    <div class="kb-board" v-if="!loading">
      <div v-for="col in COLUMNS" :key="col.id" class="kb-col">
        <div class="kb-col-header">
          <span class="col-label">{{ col.label }}</span>
          <span class="col-count">{{ (cards[col.id] || []).length }}</span>
        </div>
        <div
          class="kb-col-body"
          :class="{ 'drag-over': dragOverCol === col.id }"
          @dragover.prevent="dragOverCol = col.id"
          @dragleave="dragOverCol = null"
          @drop="onDrop(col.id)"
        >
          <div
            v-for="card in (cards[col.id] || [])"
            :key="card.id"
            class="kb-card"
            :class="{ 'hermes-card': card.moved_by_hermes, 'dragging': draggingId === card.id }"
            draggable="true"
            @dragstart="onDragStart(card)"
            @dragend="onDragEnd"
          >
            <div class="card-top">
              <span class="card-badge" :class="`badge-${card.card_type}`">{{ card.card_type }}</span>
              <span v-if="card.moved_by_hermes" class="hermes-tag">🤖 hermes</span>
            </div>
            <p class="card-title">{{ card.title }}</p>
            <div class="card-footer">
              <span class="card-due" :class="{ urgent: isUrgent(card.due_date) }">
                📅 {{ formatDate(card.due_date) }}
              </span>
            </div>
          </div>
          <button class="add-to-col" @click="openAddCard(col.id)">+ add</button>
        </div>
      </div>
    </div>

    <div v-else class="kb-loading">Loading board…</div>

    <Teleport to="body">
      <div v-if="showModal" class="modal-backdrop" @click.self="showModal = false">
        <div class="kb-modal">
          <div class="mod-modal__header">
            <span>New card</span>
            <button class="mod-modal__close" @click="showModal = false">✕</button>
          </div>
          <div class="mod-modal__body">
            <div class="field"><label class="field__label">Title *</label><input v-model="newCard.title" class="piq-input w100" placeholder="e.g. Motion to compel" /></div>
            <div class="field"><label class="field__label">Type</label>
              <select v-model="newCard.card_type" class="piq-input w100">
                <option v-for="t in CARD_TYPES" :key="t" :value="t">{{ t }}</option>
              </select>
            </div>
            <div class="field"><label class="field__label">Column</label>
              <select v-model="newCard.column_id" class="piq-input w100">
                <option v-for="c in COLUMNS" :key="c.id" :value="c.id">{{ c.label }}</option>
              </select>
            </div>
            <div class="field"><label class="field__label">Due date</label><input type="date" v-model="newCard.due_date" class="piq-input w100" /></div>
          </div>
          <div class="mod-modal__footer">
            <button class="btn-secondary" @click="showModal = false">Cancel</button>
            <button class="btn-gold" @click="saveCard" :disabled="!newCard.title">Save card</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Transition name="toast">
      <div v-if="toast.show" class="kb-toast">{{ toast.message }}</div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import axios from 'axios'

const props = defineProps({
  caseId: { type: [Number, String], required: true },
})

const COLUMNS = [
  { id: 'intake',     label: 'Intake' },
  { id: 'research',   label: 'Research' },
  { id: 'discovery',  label: 'Discovery' },
  { id: 'motions',    label: 'Motions' },
  { id: 'trial_prep', label: 'Trial Prep' },
  { id: 'closed',     label: 'Closed' },
]
const CARD_TYPES = ['task', 'deadline', 'motion', 'depo', 'filing']

const loading      = ref(true)
const cards        = reactive({})
const draggingId   = ref(null)
const draggingCard = ref(null)
const dragOverCol  = ref(null)
const hermesActive = ref(false)
const showModal    = ref(false)
const newCard      = reactive({ title: '', card_type: 'task', column_id: 'intake', due_date: '' })
const toast        = reactive({ show: false, message: '' })

const token   = () => localStorage.getItem('paraiq_token')
const authHdr = () => ({ Authorization: 'Bearer ' + token() })

async function fetchBoard() {
  loading.value = true
  try {
    const { data } = await axios.get(`/kanban/cases/${props.caseId}/board`, { headers: authHdr() })
    COLUMNS.forEach(col => { cards[col.id] = data.cards[col.id] || [] })
  } catch { showToast('Failed to load board') }
  finally { loading.value = false }
}

onMounted(fetchBoard)

function onDragStart(card) { draggingId.value = card.id; draggingCard.value = card }
function onDragEnd()       { draggingId.value = null; draggingCard.value = null; dragOverCol.value = null }

async function onDrop(targetCol) {
  dragOverCol.value = null
  const card = draggingCard.value
  if (!card || card.column_id === targetCol) return
  const oldCol = card.column_id
  cards[oldCol]    = cards[oldCol].filter(c => c.id !== card.id)
  card.column_id   = targetCol
  card.moved_by_hermes = false
  cards[targetCol] = [...(cards[targetCol] || []), card]
  try {
    await axios.patch(`/kanban/cases/${props.caseId}/cards/${card.id}/move`,
      { column_id: targetCol, moved_by_hermes: false }, { headers: authHdr() })
    showToast(`Moved to ${COLUMNS.find(c => c.id === targetCol)?.label}`)
  } catch {
    cards[targetCol] = cards[targetCol].filter(c => c.id !== card.id)
    card.column_id = oldCol
    cards[oldCol] = [...(cards[oldCol] || []), card]
    showToast('Move failed')
  }
}

function openAddCard(colId) {
  newCard.title = ''; newCard.card_type = 'task'
  newCard.column_id = colId || 'intake'; newCard.due_date = ''
  showModal.value = true
}

async function saveCard() {
  if (!newCard.title.trim()) return
  try {
    await axios.post(`/kanban/cases/${props.caseId}/cards`, {
      case_id: Number(props.caseId), title: newCard.title.trim(),
      card_type: newCard.card_type, column_id: newCard.column_id,
      due_date: newCard.due_date || null,
    }, { headers: authHdr() })
    showModal.value = false
    showToast('Card added')
    await fetchBoard()
  } catch { showToast('Failed to add card') }
}

async function triggerHermesDemo() {
  hermesActive.value = true
  const target = cards['discovery']?.[0]
  if (!target) { showToast('Hermes: no discovery card to advance'); hermesActive.value = false; return }
  try {
    const { data } = await axios.post('/kanban/hermes/signal', {
      case_id: Number(props.caseId), card_id: target.id,
      detected_event: 'document_production_complete',
      suggested_column: 'motions', confidence: 0.92,
    }, { headers: authHdr() })
    if (data.action === 'moved') { await fetchBoard(); showToast('Hermes moved card → Motions') }
  } catch { showToast('Hermes signal failed') }
  finally { hermesActive.value = false }
}

function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
function isUrgent(d) {
  if (!d) return false
  return new Date(d) <= new Date(Date.now() + 2 * 86400000)
}
function showToast(message) {
  Object.assign(toast, { show: true, message })
  setTimeout(() => { toast.show = false }, 2400)
}
</script>

<style scoped>
.kanban-root { padding: 0; }
.kb-header { display: flex; justify-content: flex-end; margin-bottom: 1rem; }
.kb-actions { display: flex; gap: 8px; }
.btn-hermes { display: flex; align-items: center; gap: 5px; font-size: 0.78rem; padding: 0.4rem 0.9rem; border-radius: 6px; border: 1px solid #7F77DD; background: rgba(127,119,221,0.12); color: #AFA9EC; cursor: pointer; transition: background 0.15s; }
.btn-hermes:hover { background: rgba(127,119,221,0.22); }
.btn-hermes.pulsing { animation: pulse 0.8s ease-in-out infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
.btn-add { font-size: 0.78rem; padding: 0.4rem 0.9rem; border-radius: 6px; border: 1px solid var(--border); background: transparent; color: var(--text-muted); cursor: pointer; }
.btn-add:hover { background: var(--bg-raised); color: var(--text-primary); }

.kb-board { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 8px; }
.kb-col { flex: 0 0 175px; display: flex; flex-direction: column; }
.kb-col-header { display: flex; align-items: center; justify-content: space-between; padding: 7px 10px; border-radius: 8px 8px 0 0; border: 1px solid var(--border); border-bottom: none; background: var(--bg-card); }
.col-label { font-size: 0.65rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
.col-count { font-size: 0.65rem; color: var(--text-muted); background: var(--bg-raised); border: 1px solid var(--border); border-radius: 10px; padding: 1px 7px; }
.kb-col-body { flex: 1; padding: 8px; border: 1px solid var(--border); border-top: none; border-radius: 0 0 8px 8px; background: var(--bg-card); min-height: 420px; display: flex; flex-direction: column; gap: 7px; transition: background 0.15s; }
.kb-col-body.drag-over { background: rgba(127,119,221,0.08); border-color: #7F77DD; }

.kb-card { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 7px; padding: 9px 10px; cursor: grab; transition: border-color 0.12s, opacity 0.1s; user-select: none; }
.kb-card:hover { border-color: var(--gold); }
.kb-card.dragging { opacity: 0.4; }
.kb-card.hermes-card { border-left: 2.5px solid #7F77DD; }
.card-top { display: flex; align-items: center; gap: 4px; margin-bottom: 6px; flex-wrap: wrap; }
.card-badge { font-size: 0.62rem; font-weight: 700; padding: 2px 6px; border-radius: 10px; text-transform: uppercase; letter-spacing: 0.03em; }
.badge-task     { background: rgba(72,187,120,.15);  color: #48bb78; }
.badge-deadline { background: rgba(252,129,129,.15); color: #fc8181; }
.badge-motion   { background: rgba(127,119,221,.15); color: #AFA9EC; }
.badge-depo     { background: rgba(236,201,75,.15);  color: #ecc94b; }
.badge-filing   { background: rgba(74,124,247,.15);  color: #4a7cf7; }
.hermes-tag { font-size: 0.6rem; color: #AFA9EC; background: rgba(127,119,221,.12); border-radius: 8px; padding: 1px 5px; margin-left: auto; }
.card-title { font-size: 0.78rem; font-weight: 500; color: var(--text-primary); line-height: 1.4; margin-bottom: 7px; }
.card-footer { display: flex; align-items: center; }
.card-due { font-size: 0.68rem; color: var(--text-muted); }
.card-due.urgent { color: #fc8181; font-weight: 600; }
.add-to-col { border: 1px dashed var(--border); border-radius: 6px; padding: 6px; font-size: 0.72rem; color: var(--text-muted); background: none; cursor: pointer; margin-top: auto; }
.add-to-col:hover { background: var(--bg-raised); color: var(--text-primary); }
.kb-loading { color: var(--text-muted); padding: 3rem; text-align: center; }

.modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.65); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.kb-modal { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 10px; width: 400px; display: flex; flex-direction: column; }
.kb-toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: var(--bg-raised); border: 1px solid var(--border); color: var(--text-primary); font-size: 0.8rem; padding: 8px 16px; border-radius: 8px; z-index: 2000; }
.toast-enter-active, .toast-leave-active { transition: all 0.2s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(6px); }

/* Reuse existing ParaIQ styles from parent */
.mod-modal__header { align-items: center; border-bottom: 1px solid var(--border); color: var(--text-primary); display: flex; font-size: 0.95rem; font-weight: 600; justify-content: space-between; padding: 1rem 1.25rem; }
.mod-modal__close  { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1rem; padding: 0.2rem; }
.mod-modal__body   { display: flex; flex-direction: column; gap: 0.85rem; padding: 1.25rem; }
.mod-modal__footer { border-top: 1px solid var(--border); display: flex; gap: 0.5rem; justify-content: flex-end; padding: 1rem 1.25rem; }
.field { display: flex; flex-direction: column; gap: 0.3rem; }
.field__label { color: var(--text-muted); font-size: 0.68rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.piq-input { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-family: inherit; font-size: 0.875rem; outline: none; padding: 0.5rem 0.75rem; }
.piq-input:focus { border-color: var(--gold); }
.w100 { width: 100%; box-sizing: border-box; }
.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1.1rem; }
.btn-gold:disabled { opacity: .45; cursor: not-allowed; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; }
</style>
